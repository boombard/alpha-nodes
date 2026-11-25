"""DuckDB point-in-time source store (layer 1 cache).

`DuckDBSourceStore` implements `SourceStore` (base.py): it composes coverage planning
(coverage.py) and the provider scheduler (scheduler.py) over one DuckDB file for
records and facts, and a `BlobStore` for the verbatim raw payloads. See
documentation/design/core.md, Source store (all of it), and lessons.md (caching lessons).

Tables (all in the one DuckDB file; `params` is canonical JSON of the request params,
timestamps are naive UTC, intervals are stored as `*_start`/`*_end` DATE columns):

- `raw_responses`: one row per `ok` provider response: `raw_id`, provider, dataset, entity,
  params, interval, `settled_through`, `payload_hash` (key into the BlobStore), `fetched_at`,
  `library_version`. Immutable; `renormalise` reads these. Rows come back oldest first.
- `attempts`: the fetch-attempt log, one row per final outcome, plus an `unsettled` row for
  the tail a provider reported as not yet settled.
- `coverage`: one `CoverageState` (JSON) per (dataset, entity, provider, params).
- `renormalisations`: one row per `renormalise` run (see `RenormalisationRecord`).
- `facts_<dataset>`: one table per dataset, created from `Dataset.frame_schema` with typed
  columns (floats `DOUBLE`, ints `BIGINT`, datetimes `TIMESTAMP`, strings `VARCHAR`), followed
  by `entity`, `provider`, `params` and the fact meta columns (`fetch_id`, `first_seen_at`,
  `known_at`, `normaliser_version`, `repairs`/`quality_reasons` as `VARCHAR[]`, `quality`).
  Append-only: a changed row is a new version of its key; the latest version is the one with
  the greatest `version_seq` (bookkeeping, filled from the store-wide sequence
  `fact_version_seq`; never compared when deciding whether a row is a new version). The log
  tables carry a `seq` from `log_seq` for ordering. No DuckDB-only row
  identifier is used, so the SQL ports to other databases.

All DuckDB access happens on the calling (event-loop) thread: providers run in worker
threads but only ever see work items and return outcomes.
"""

import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict

from ..store.base import BlobStore
from .base import Clock, Provider, SourceStore, SourceUnavailable
from .clock import SystemClock
from .coverage import CoverageState, apply_outcome, plan_gaps
from .models import (
    FACT_META_COLUMNS,
    AttemptKind,
    Dataset,
    DateInterval,
    FetchAttempt,
    FetchOutcome,
    IntervalSet,
    ProviderCapabilities,
    RateLimitPolicy,
    RawResponse,
    SourceSlice,
    WorkItem,
)
from .scheduler import ProviderLimiter, run_items

_ONE_DAY = timedelta(days=1)
_LABELS = ("repairs", "quality", "quality_reasons")  # compared, with canonical values, for versions
_MAX_PASSES = 2  # a restatement replans once: the first pass plus one more
_SCHEMA = [
    "CREATE SEQUENCE IF NOT EXISTS fact_version_seq",
    "CREATE SEQUENCE IF NOT EXISTS log_seq",
    """CREATE TABLE IF NOT EXISTS raw_responses (
        raw_id VARCHAR PRIMARY KEY, provider VARCHAR, dataset VARCHAR, entity VARCHAR,
        params VARCHAR, interval_start DATE, interval_end DATE, settled_through DATE,
        payload_hash VARCHAR, fetched_at TIMESTAMP, library_version VARCHAR,
        seq BIGINT DEFAULT nextval('log_seq'))""",
    """CREATE TABLE IF NOT EXISTS attempts (
        provider VARCHAR, dataset VARCHAR, entity VARCHAR, params VARCHAR,
        interval_start DATE, interval_end DATE, kind VARCHAR, attempted_at TIMESTAMP, message VARCHAR,
        seq BIGINT DEFAULT nextval('log_seq'))""",
    """CREATE TABLE IF NOT EXISTS coverage (
        dataset VARCHAR, entity VARCHAR, provider VARCHAR, params VARCHAR, state VARCHAR,
        PRIMARY KEY (dataset, entity, provider, params))""",
    """CREATE TABLE IF NOT EXISTS renormalisations (
        dataset VARCHAR, provider VARCHAR, normaliser_version VARCHAR, started_at TIMESTAMP,
        finished_at TIMESTAMP, raw_responses_read BIGINT, rows_written BIGINT,
        seq BIGINT DEFAULT nextval('log_seq'))""",
]


class RenormalisationRecord(BaseModel):
    """One logged `renormalise` run (store-internal; not part of the `SourceStore` protocol)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: str
    provider: str
    normaliser_version: str  # the provider's version stamped on the rows this run wrote
    started_at: datetime
    finished_at: datetime
    raw_responses_read: int
    rows_written: int  # new versions appended (rows whose values and labels were unchanged add none)


class _PolicyOverride:
    """A `Provider` that delegates to another but declares a replacement rate-limit policy.

    The scheduler reads `capabilities.rate_limit` for retries and backoff as well as for the
    limiter, so the override has to be visible on the provider itself.
    """

    def __init__(self, inner: Provider, policy: RateLimitPolicy) -> None:
        self._inner = inner
        self.name = inner.name
        self.library_version = inner.library_version
        self.capabilities: ProviderCapabilities = inner.capabilities.model_copy(
            update={"rate_limit": policy}
        )

    def normaliser_version(self, dataset: str) -> str:
        return self._inner.normaliser_version(dataset)

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        return self._inner.fetch(dataset, items)

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        return self._inner.normalise(dataset, raw, payload)


def _q(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def _params_key(params: Mapping[str, str]) -> str:
    return json.dumps(dict(sorted(params.items())))


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)


def _duckdb_type(dtype: Any) -> str:
    """DuckDB column type for a canonical column's declared dtype."""
    if dtype is date:
        return "DATE"
    pandas_dtype = pd.api.types.pandas_dtype(dtype)
    if isinstance(pandas_dtype, pd.DatetimeTZDtype):
        return "TIMESTAMPTZ"
    return {"M": "TIMESTAMP", "b": "BOOLEAN", "i": "BIGINT", "u": "BIGINT", "f": "DOUBLE"}.get(
        pandas_dtype.kind, "VARCHAR"
    )


def _interval_cut(interval: DateInterval) -> tuple[datetime, datetime]:
    """Half-open datetime bounds [start, end + 1 day) of a closed day interval."""
    return (
        datetime.combine(interval.start, datetime.min.time()),
        datetime.combine(interval.end + _ONE_DAY, datetime.min.time()),
    )


class DuckDBSourceStore(SourceStore):
    """Point-in-time source store over DuckDB (records, facts, coverage, attempts) and a `BlobStore`.

    Implements the `SourceStore` protocol; see the module docstring for the table layouts and
    documentation/design/core.md, Source store, for the semantics. Holds one connection:
    use it from the event-loop thread only, and `close()` it before another store opens the file.

    Args:
        path: DuckDB file, or ":memory:".
        blobs: where verbatim provider payloads go (content-addressed).
        datasets: every dataset the store serves, by name.
        providers: per dataset, the fallback chain, primary first. A provider name must refer
            to one provider object across datasets (it shares one rate limiter).
        clock: time source for TTLs, backoff and `first_seen_at`; default `SystemClock`.
        offline: never call a provider; a gap (or due snapshot) raises `SourceUnavailable`.
        policy_overrides: provider name -> `RateLimitPolicy` replacing the declared one.
    """

    def __init__(
        self,
        path: Path | str,
        blobs: BlobStore,
        datasets: Mapping[str, Dataset],
        providers: Mapping[str, Sequence[Provider]],
        *,
        clock: Clock | None = None,
        offline: bool = False,
        policy_overrides: Mapping[str, RateLimitPolicy] = {},
    ) -> None:
        self._blobs = blobs
        self._datasets = dict(datasets)
        self._clock: Clock = clock or SystemClock()
        self._offline = offline
        self._providers: dict[str, Provider] = {}
        self._chains: dict[str, list[Provider]] = {}
        for name in self._datasets:
            chain = list(providers.get(name, ()))
            if not chain:
                raise ValueError(f"dataset {name!r} has no providers")
            self._chains[name] = [self._register(p, policy_overrides) for p in chain]
        self._limiters = {
            n: ProviderLimiter(n, p.capabilities.rate_limit, self._clock)
            for n, p in self._providers.items()
        }
        self._columns = {n: self._canonical_types(ds) for n, ds in self._datasets.items()}
        self._con = duckdb.connect(str(path))
        for stmt in _SCHEMA:
            self._con.execute(stmt)
        for name in self._datasets:
            self._create_facts_table(name)

    @property
    def clock(self) -> Clock:
        """The store's clock; fetch nodes take "today" from it."""
        return self._clock

    def close(self) -> None:
        """Close the connection (flushes to disk and releases the file lock)."""
        self._con.close()

    # -- setup ---------------------------------------------------------------------------

    def _register(self, provider: Provider, overrides: Mapping[str, RateLimitPolicy]) -> Provider:
        known = self._providers.get(provider.name)
        if known is not None:
            inner = getattr(known, "_inner", known)
            if inner is not provider:
                raise ValueError(f"two different providers are named {provider.name!r}")
            return known
        wrapped: Provider = (
            _PolicyOverride(provider, overrides[provider.name])
            if provider.name in overrides
            else provider
        )
        self._providers[provider.name] = wrapped
        return wrapped

    @staticmethod
    def _canonical_types(ds: Dataset) -> dict[str, str]:
        """Canonical column name -> DuckDB type, from the dataset's pandera schema."""
        columns = {
            name: _duckdb_type(col.dtype.type if col.dtype is not None else str)
            for name, col in ds.frame_schema.to_schema().columns.items()
        }
        clash = set(columns) & {*FACT_META_COLUMNS, "params"}
        if clash:
            raise ValueError(f"dataset {ds.name!r}: canonical columns clash with meta: {sorted(clash)}")
        return columns

    def _facts(self, dataset: str) -> str:
        return _q(f"facts_{dataset}")

    def _create_facts_table(self, dataset: str) -> None:
        canonical = ", ".join(f"{_q(c)} {t}" for c, t in self._columns[dataset].items())
        self._con.execute(
            f"""CREATE TABLE IF NOT EXISTS {self._facts(dataset)} (
                {canonical}, entity VARCHAR, provider VARCHAR, params VARCHAR, fetch_id VARCHAR,
                first_seen_at TIMESTAMP, known_at TIMESTAMP, normaliser_version VARCHAR,
                repairs VARCHAR[], quality VARCHAR, quality_reasons VARCHAR[],
                version_seq BIGINT DEFAULT nextval('fact_version_seq'))"""
        )

    def _dataset(self, name: str) -> Dataset:
        try:
            return self._datasets[name]
        except KeyError:
            raise ValueError(f"unknown dataset {name!r}") from None

    @contextmanager
    def _txn(self) -> Iterator[None]:
        """One DuckDB transaction: commit on success, roll back and re-raise on any error."""
        self._con.execute("BEGIN TRANSACTION")
        try:
            yield
        except BaseException:
            self._con.execute("ROLLBACK")
            raise
        self._con.execute("COMMIT")

    # -- coverage and logs -----------------------------------------------------------------

    def _state(self, dataset: str, entity: str, provider: str, params_key: str) -> CoverageState:
        row = self._con.execute(
            "SELECT state FROM coverage WHERE dataset=? AND entity=? AND provider=? AND params=?",
            [dataset, entity, provider, params_key],
        ).fetchone()
        return CoverageState.model_validate_json(row[0]) if row else CoverageState()

    def coverage(
        self, dataset: str, entity: str, provider: str, params: Mapping[str, str] = {}
    ) -> IntervalSet:
        """Requested ranges successfully fetched (settled) for this (entity, dataset, provider, params)."""
        return self._state(dataset, entity, provider, _params_key(params)).settled

    def attempts(self, dataset: str | None = None, entity: str | None = None) -> list[FetchAttempt]:
        """The fetch-attempt log in the order attempts finished, optionally filtered."""
        where, args = [], []
        for column, value in (("dataset", dataset), ("entity", entity)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._con.execute(
            "SELECT provider, dataset, entity, params, interval_start, interval_end, kind, attempted_at, message "
            f"FROM attempts {clause} ORDER BY seq",
            args,
        ).fetchall()
        return [
            FetchAttempt(
                provider=p,
                dataset=d,
                entity=e,
                interval=DateInterval(start=s, end=en) if s else None,
                params=json.loads(pk),
                kind=k,
                at=_aware(at),
                message=m,
            )
            for p, d, e, pk, s, en, k, at, m in rows
        ]

    def raw_responses(self, dataset: str, provider: str) -> list[RawResponse]:
        """Stored raw responses for a (dataset, provider), oldest first."""
        rows = self._con.execute(
            "SELECT raw_id, entity, params, interval_start, interval_end, payload_hash, fetched_at, "
            "library_version FROM raw_responses WHERE dataset=? AND provider=? ORDER BY seq",
            [dataset, provider],
        ).fetchall()
        return [
            RawResponse(
                raw_id=rid,
                provider=provider,
                dataset=dataset,
                entity=e,
                interval=DateInterval(start=s, end=en) if s else None,
                params=json.loads(pk),
                payload_hash=h,
                fetched_at=_aware(fa),
                library_version=lv,
            )
            for rid, e, pk, s, en, h, fa, lv in rows
        ]

    def renormalisations(self) -> list[RenormalisationRecord]:
        """The `renormalise` run log, oldest first."""
        rows = self._con.execute(
            "SELECT dataset, provider, normaliser_version, started_at, finished_at, "
            "raw_responses_read, rows_written FROM renormalisations ORDER BY seq"
        ).fetchall()
        return [
            RenormalisationRecord(
                dataset=d,
                provider=p,
                normaliser_version=nv,
                started_at=_aware(sa),
                finished_at=_aware(fa),
                raw_responses_read=n,
                rows_written=w,
            )
            for d, p, nv, sa, fa, n, w in rows
        ]

    # -- reading -----------------------------------------------------------------------------

    def _read(
        self,
        ds: Dataset,
        entity: str,
        provider: str,
        params_key: str,
        interval: DateInterval | None,
        as_of: date | None,
        include_rejected: bool,
    ) -> pd.DataFrame:
        """Latest version per key of one provider's facts, canonical + meta columns."""
        where = ["entity = ?", "provider = ?", "params = ?"]
        args: list[Any] = [entity, provider, params_key]
        if as_of is not None:
            where.append("known_at < ?")
            args.append(datetime.combine(as_of + _ONE_DAY, datetime.min.time()))
        if interval is not None and ds.axis_column:
            start, end = _interval_cut(interval)
            axis = _q(ds.axis_column)
            where.append(f"{axis} >= ? AND {axis} < ?")
            args += [start, end]
        keys = ", ".join(_q(k) for k in ds.key_columns)
        select = ", ".join(_q(c) for c in [*self._columns[ds.name], *FACT_META_COLUMNS])
        rejected = "" if include_rejected else "AND quality <> 'rejected'"
        frame = self._con.execute(
            f"""SELECT {select} FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        {"PARTITION BY " + keys if keys else ""} ORDER BY version_seq DESC
                    ) AS rn FROM {self._facts(ds.name)} WHERE {" AND ".join(where)}
                ) WHERE rn = 1 {rejected} ORDER BY {keys or "entity"}""",
            args,
        ).df()
        for column in ("repairs", "quality_reasons"):
            frame[column] = pd.Series([list(v) for v in frame[column]], index=frame.index, dtype=object)
        for column in ("first_seen_at", "known_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True).astype("datetime64[ns, UTC]")
        schema = ds.frame_schema.to_schema().columns
        for name in self._columns[ds.name]:
            dtype = schema[name].dtype
            if dtype is not None and pd.api.types.pandas_dtype(dtype.type).kind == "M":
                frame[name] = frame[name].astype(pd.api.types.pandas_dtype(dtype.type))
        return frame

    def _has_facts(
        self, ds: Dataset, entity: str, provider: str, params_key: str, interval: DateInterval | None
    ) -> bool:
        """True when `provider` holds any fact version for the entity in the interval."""
        where = ["entity = ?", "provider = ?", "params = ?"]
        args: list[Any] = [entity, provider, params_key]
        if interval is not None and ds.axis_column:
            start, end = _interval_cut(interval)
            axis = _q(ds.axis_column)
            where.append(f"{axis} >= ? AND {axis} < ?")
            args += [start, end]
        row = self._con.execute(
            f"SELECT 1 FROM {self._facts(ds.name)} WHERE {' AND '.join(where)} LIMIT 1", args
        ).fetchone()
        return row is not None

    def query(
        self,
        dataset: str,
        entity: str,
        interval: DateInterval | None = None,
        *,
        as_of: date | None = None,
        params: Mapping[str, str] = {},
        include_rejected: bool = False,
    ) -> SourceSlice:
        """Read what is stored, never fetching.

        Serves the first provider in the dataset's chain that holds any fact for the entity
        and interval (one provider only, no mixing), whatever `as_of` or the quality filter
        then leave of it: a filtered-out primary yields an empty frame, never the fallback's
        rows. Per key the latest version known before the end of the
        `as_of` day (UTC) wins; `as_of=None` means the latest. `rejected` rows are left out
        unless `include_rejected`; `suspect` rows are served with their reasons.
        """
        ds = self._dataset(dataset)
        params_key = _params_key(params)
        for provider in self._chains[dataset]:
            if self._has_facts(ds, entity, provider.name, params_key, interval):
                frame = self._read(
                    ds, entity, provider.name, params_key, interval, as_of, include_rejected
                )
                return SourceSlice(
                    dataset=dataset,
                    entity=entity,
                    provider=provider.name,
                    frame=frame,
                    pit_reliable=provider.capabilities.pit_reliable.get(dataset, False),
                    empty=False,
                )
        frame = self._read(
            ds, entity, self._chains[dataset][0].name, params_key, interval, as_of, include_rejected
        )
        return SourceSlice(
            dataset=dataset, entity=entity, provider=None, frame=frame, pit_reliable=False, empty=True
        )

    # -- writing -----------------------------------------------------------------------------

    def _append_versions(
        self,
        ds: Dataset,
        provider: str,
        entity: str,
        params_key: str,
        frame: pd.DataFrame,
        fetch_id: str,
        normaliser_version: str,
        now: datetime,
    ) -> int:
        """Append a version for each row that is new, or differs in value or labels from its key's latest.

        Bookkeeping columns (`fetch_id`, `first_seen_at`, `normaliser_version`) are not compared.
        Must run inside a transaction. Returns the number of rows written.
        """
        canonical = list(self._columns[ds.name])
        missing = [c for c in (*canonical, *_LABELS) if c not in frame.columns]
        if missing:
            raise ValueError(f"{provider}.normalise({ds.name}) lacks columns {missing}")
        if frame.empty:
            return 0
        frame = frame.reset_index(drop=True)
        if ds.key_columns:
            dupes = pd.DataFrame(frame.loc[frame.duplicated(list(ds.key_columns), keep=False)])
            if not dupes.empty:
                keys = sorted({tuple(str(dupes[k].iloc[i]) for k in ds.key_columns) for i in range(len(dupes))})
                raise ValueError(
                    f"{provider}.normalise({ds.name}) returned duplicate keys "
                    f"{list(ds.key_columns)}: {keys[:5]}"
                )
        elif len(frame) > 1:
            raise ValueError(f"{ds.name} is a keyless snapshot: normalise must return one row, got {len(frame)}")
        seen = _naive_utc(now)
        known = pd.Series(seen, index=frame.index)
        if "known_at" in frame.columns:
            given = pd.to_datetime(frame["known_at"], utc=True).dt.tz_localize(None)
            known = given.fillna(pd.Timestamp(seen)).astype("datetime64[us]")
        incoming = frame[canonical].copy()
        incoming["entity"], incoming["provider"], incoming["params"] = entity, provider, params_key
        incoming["fetch_id"] = frame["fetch_id"] if "fetch_id" in frame.columns else fetch_id
        incoming["normaliser_version"] = normaliser_version
        incoming["first_seen_at"], incoming["known_at"] = pd.Timestamp(seen), known
        incoming["quality"] = frame["quality"].astype(str)
        for label in ("repairs", "quality_reasons"):
            incoming[label] = pd.Series([list(v) for v in frame[label]], index=frame.index, dtype=object)
        names = [*canonical, "entity", "provider", "params", "fetch_id", "first_seen_at", "known_at",
                 "normaliser_version", "repairs", "quality", "quality_reasons"]  # fmt: skip
        projection = ", ".join(
            f"CAST({_q(n)} AS VARCHAR[]) AS {_q(n)}" if n in ("repairs", "quality_reasons") else _q(n)
            for n in names
        )
        compared = [c for c in canonical if c not in ds.key_columns] + list(_LABELS)
        keys = ", ".join(_q(k) for k in ds.key_columns)
        join = " AND ".join(f"i.{_q(k)} IS NOT DISTINCT FROM l.{_q(k)}" for k in ds.key_columns) or "true"
        changed = " OR ".join(f"i.{_q(c)} IS DISTINCT FROM l.{_q(c)}" for c in compared)
        table = self._facts(ds.name)
        self._con.register("incoming_frame", incoming)
        try:
            row = self._con.execute(
                f"""INSERT INTO {table} ({", ".join(_q(n) for n in names)})
                    WITH i AS (SELECT {projection} FROM incoming_frame),
                    l AS (
                        SELECT * FROM (
                            SELECT *, ROW_NUMBER() OVER (
                                {"PARTITION BY " + keys if keys else ""}
                                ORDER BY version_seq DESC
                            ) AS rn FROM {table} WHERE entity = ? AND provider = ? AND params = ?
                        ) WHERE rn = 1
                    )
                    SELECT i.* FROM i LEFT JOIN l ON {join}
                    WHERE l.entity IS NULL OR {changed}""",
                [entity, provider, params_key],
            ).fetchone()
        finally:
            self._con.unregister("incoming_frame")
        return int(row[0]) if row else 0

    @staticmethod
    def _settled_only(ds: Dataset, frame: pd.DataFrame, settled_through: date | None) -> pd.DataFrame:
        """Drop rows after `settled_through` (date axis): a live tail is never a fact."""
        if ds.axis != "date" or settled_through is None or ds.axis_column not in frame.columns:
            return frame
        days = pd.to_datetime(frame[ds.axis_column]).dt.date
        return pd.DataFrame(frame.loc[days <= settled_through])

    def _persist(self, provider: Provider, ds: Dataset, outcome: FetchOutcome) -> str | None:
        """Persist one final outcome atomically: raw response, attempt(s), coverage, facts.

        An `ok` outcome whose normalisation (or settled cut, or version append) raises is not
        a crash: nothing is cached for it (no raw-response row, coverage or facts; the blob
        may stay), an `error` attempt `normalise: <type>: <message> (payload <hash>)` is
        logged, and that message is returned so `_pass` can raise `SourceUnavailable` once the
        provider level is done. Returns None otherwise.
        """
        item, now = outcome.item, self._clock.now()
        params_key = _params_key(item.params)
        state = self._state(ds.name, item.entity, provider.name, params_key)
        new_state = apply_outcome(ds, state, outcome, now)
        payload_hash = ""
        try:
            raw: RawResponse | None = None
            frame: pd.DataFrame | None = None
            if outcome.kind == "ok":
                payload_hash = self._blobs.put(outcome.payload)
                raw = RawResponse(
                    raw_id=uuid.uuid4().hex,
                    provider=provider.name,
                    dataset=ds.name,
                    entity=item.entity,
                    interval=item.interval,
                    params=item.params,
                    payload_hash=payload_hash,
                    fetched_at=now,
                    library_version=provider.library_version,
                )
                frame = self._settled_only(
                    ds, provider.normalise(ds, raw, outcome.payload), outcome.settled_through
                )
            with self._txn():
                attempts: list[tuple[AttemptKind, DateInterval | None, str]] = [
                    (outcome.kind, item.interval, outcome.message)
                ]
                interval, through = item.interval, outcome.settled_through
                if raw and frame is not None:
                    self._insert_raw(raw, through)
                    self._append_versions(
                        ds, provider.name, item.entity, params_key, frame, raw.raw_id,
                        provider.normaliser_version(ds.name), now,
                    )  # fmt: skip
                    if interval and through and interval.end > through:
                        tail = DateInterval(start=max(interval.start, through + _ONE_DAY), end=interval.end)
                        attempts.append(("unsettled", tail, "after settled_through"))
                for kind, span, message in attempts:
                    self._log_attempt(provider.name, ds.name, item, kind, span, now, message)
                if new_state != state:
                    self._con.execute(
                        "INSERT OR REPLACE INTO coverage VALUES (?, ?, ?, ?, ?)",
                        [ds.name, item.entity, provider.name, params_key, new_state.model_dump_json()],
                    )
        except Exception as exc:
            if outcome.kind != "ok":
                raise
            message = f"normalise: {type(exc).__name__}: {exc} (payload {payload_hash or 'unstored'})"
            self._log_attempt(provider.name, ds.name, item, "error", item.interval, now, message)
            return message
        return None

    def _log_tripped_empties(self, provider: Provider, ds: Dataset, held: list[FetchOutcome]) -> None:
        """Log the `empty` attempts of a tripped streak without caching them (entities stay unknown)."""
        now = self._clock.now()
        for outcome in held:
            self._log_attempt(
                provider.name, ds.name, outcome.item, "empty", outcome.item.interval, now,
                "not cached: empty-streak circuit breaker tripped",
            )  # fmt: skip

    def _insert_raw(self, raw: RawResponse, settled_through: date | None) -> None:
        iv = raw.interval
        self._con.execute(
            "INSERT INTO raw_responses (raw_id, provider, dataset, entity, params, interval_start, interval_end, settled_through, payload_hash, fetched_at, library_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                raw.raw_id, raw.provider, raw.dataset, raw.entity, _params_key(raw.params),
                iv.start if iv else None, iv.end if iv else None, settled_through,
                raw.payload_hash, _naive_utc(raw.fetched_at), raw.library_version,
            ],
        )  # fmt: skip

    def _log_attempt(
        self,
        provider: str,
        dataset: str,
        item: WorkItem,
        kind: AttemptKind,
        span: DateInterval | None,
        at: datetime,
        message: str,
    ) -> None:
        self._con.execute(
            "INSERT INTO attempts (provider, dataset, entity, params, interval_start, interval_end, kind, attempted_at, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                provider, dataset, item.entity, _params_key(item.params),
                span.start if span else None, span.end if span else None, kind,
                _naive_utc(at), message,
            ],
        )  # fmt: skip

    # -- fetching ----------------------------------------------------------------------------

    @staticmethod
    def _items(dataset: str, entity: str, params: Mapping[str, str], gaps: Sequence[DateInterval | None]):
        return [WorkItem(dataset=dataset, entity=entity, interval=g, params=dict(params)) for g in gaps]

    async def ensure(
        self,
        dataset: str,
        entities: Sequence[str],
        interval: DateInterval | None = None,
        *,
        params: Mapping[str, str] = {},
    ) -> None:
        """Fill gaps for many entities at once, batched per provider and persisted per outcome.

        Each entity walks the dataset's provider chain: a provider that is `known_empty` or
        answers `empty` passes the entity on, unless it already holds facts for the requested
        range (then those are served and nothing is fetched). When an outcome reports
        `restated_before`, the plan is made once more so the restated history is refetched in
        this same call.

        Raises:
            SourceUnavailable: an offline gap, an `error` outcome after retries, or a `normalise`
                failure (nothing cached; the other entities are persisted).
            GlobalFailure: from the provider's limiter (incl. the error/empty circuit breakers) or
                `fetch`; finished items stay persisted. A tripped empty streak is logged, not cached.
        """
        ds = self._dataset(dataset)
        for _ in range(_MAX_PASSES):
            if not await self._pass(ds, list(dict.fromkeys(entities)), interval, params):
                return

    async def _pass(
        self, ds: Dataset, entities: list[str], interval: DateInterval | None, params: Mapping[str, str]
    ) -> bool:
        """One planning pass down the provider chain; True when a restatement dropped coverage."""
        params_key = _params_key(params)
        restated = False
        pending = entities
        for provider in self._chains[ds.name]:
            if not pending:
                break
            work: list[WorkItem] = []
            passed: list[str] = []
            for entity in pending:
                state = self._state(ds.name, entity, provider.name, params_key)
                plan = plan_gaps(ds, state, interval, self._clock.now())
                if plan.known_empty:
                    if not self._has_facts(ds, entity, provider.name, params_key, interval):
                        passed.append(entity)
                elif plan.snapshot_due:
                    work += self._items(ds.name, entity, params, [None])
                else:
                    work += self._items(ds.name, entity, params, plan.gaps)
            if work:
                if self._offline:
                    gap = work[0]
                    raise SourceUnavailable(
                        f"offline: {ds.name} for {gap.entity} is not stored by {provider.name} "
                        f"(requested {interval})"
                    )

                normalise_failures: list[tuple[str, str]] = []

                async def persist(
                    outcome: FetchOutcome,
                    provider: Provider = provider,
                    failures: list[tuple[str, str]] = normalise_failures,
                ) -> None:
                    if failed := self._persist(provider, ds, outcome):
                        failures.append((outcome.item.entity, failed))

                async def tripped(held: list[FetchOutcome], provider: Provider = provider) -> None:
                    self._log_tripped_empties(provider, ds, held)

                outcomes = await run_items(
                    provider, ds, work, self._limiters[provider.name], persist, tripped
                )
                if normalise_failures:
                    entity, message = normalise_failures[0]
                    raise SourceUnavailable(
                        f"{ds.name} for {entity} from {provider.name} failed: {message}"
                        + (f" (+{len(normalise_failures) - 1} more)" if len(normalise_failures) > 1 else "")
                    )
                for outcome in outcomes:
                    if outcome.kind == "error":
                        raise SourceUnavailable(
                            f"{ds.name} for {outcome.item.entity} from {provider.name} failed: "
                            f"{outcome.message or 'error'}"
                        )
                restated |= any(o.restated_before is not None for o in outcomes)
                for entity in dict.fromkeys(o.item.entity for o in outcomes if o.kind == "empty"):
                    if not self._has_facts(ds, entity, provider.name, params_key, interval):
                        passed.append(entity)
            pending = passed
        return restated

    async def get(
        self,
        dataset: str,
        entity: str,
        interval: DateInterval | None = None,
        *,
        as_of: date | None = None,
        params: Mapping[str, str] = {},
        include_rejected: bool = False,
    ) -> SourceSlice:
        """`ensure` for one entity, then `query`. Raises `SourceUnavailable` when data can't be served."""
        await self.ensure(dataset, [entity], interval, params=params)
        return self.query(
            dataset, entity, interval, as_of=as_of, params=params, include_rejected=include_rejected
        )

    # -- renormalise -------------------------------------------------------------------------

    def renormalise(self, dataset: str, provider: str) -> int:
        """Rebuild facts for (dataset, provider) from stored raw responses; never calls `fetch`.

        Re-runs `provider.normalise` over every raw response, oldest first, keeps per key the
        row from the newest raw response (so a restated key is not replayed through its stale
        value), and appends a version wherever that differs in values or labels from the key's
        latest version, stamped with the provider's current `normaliser_version`. All appends
        and the `renormalisations` log row are one transaction. Returns the rows written.
        """
        ds = self._dataset(dataset)
        try:
            prov = self._providers[provider]
        except KeyError:
            raise ValueError(f"unknown provider {provider!r}") from None
        started, version = self._clock.now(), prov.normaliser_version(dataset)
        settled = {
            r[0]: r[1]
            for r in self._con.execute(
                "SELECT raw_id, settled_through FROM raw_responses WHERE dataset=? AND provider=?",
                [dataset, provider],
            ).fetchall()
        }
        raws = self.raw_responses(dataset, provider)
        groups: dict[tuple[str, str], list[pd.DataFrame]] = {}
        for raw in raws:  # oldest first; normalise everything before writing anything
            frame = self._settled_only(
                ds, prov.normalise(ds, raw, self._blobs.get(raw.payload_hash)), settled[raw.raw_id]
            )
            groups.setdefault((raw.entity, _params_key(raw.params)), []).append(
                frame.assign(fetch_id=raw.raw_id)
            )
        written = 0
        with self._txn():
            for (entity, params_key), frames in groups.items():
                merged = pd.concat(frames, ignore_index=True)
                merged = (
                    merged.drop_duplicates(list(ds.key_columns), keep="last")  # newest raw wins
                    if ds.key_columns
                    else merged.tail(1)
                )
                written += self._append_versions(
                    ds, provider, entity, params_key, merged, "", version, started
                )
            self._con.execute(
                "INSERT INTO renormalisations (dataset, provider, normaliser_version, started_at, finished_at, raw_responses_read, rows_written) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [dataset, provider, version, _naive_utc(started), _naive_utc(self._clock.now()),
                 len(raws), written],
            )  # fmt: skip
        return written
