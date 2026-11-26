"""Compare one lens's verdicts between two runs, e.g. a rubric run and a `buffett_persona` run.

Offline: reads the run index and the blob store only, never the network (finance.md, v1 lenses;
core.md, Variants). Usage:
    uv run python packages/alpha_nodes/scripts/compare_variants.py RUN_A RUN_B [--lens quality_value] [--store PATH]

Prints, per candidate, the lens's status, stance and conviction in each run and the input names it
cited; then the stance agreement (exact and within 1), the mean |stance difference| and the
cites per input of each run. Candidates are those with a stored dossier in both runs.
"""

import re
from collections import Counter
from pathlib import Path

import click
from lensgraph.config import Settings
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.files import FileBlobStore
from lensgraph.verdict import Dossier, LensVerdict
from pydantic import BaseModel, ConfigDict


class RunVerdict(BaseModel):
    """One lens verdict of one candidate in one run, reduced to what the comparison shows."""

    model_config = ConfigDict(extra="forbid")

    status: str
    stance: int | None = None
    conviction: str | None = None
    cited_inputs: list[str] = []


class CandidateComparison(BaseModel):
    """One candidate's verdict in run A and in run B."""

    model_config = ConfigDict(extra="forbid")

    candidate: str
    a: RunVerdict
    b: RunVerdict


class VariantComparison(BaseModel):
    """The comparison of one lens across two runs: a row per candidate plus the summary.

    Attributes:
        agreement_exact: share of compared candidates (both runs `ok`) with equal stance, in [0, 1].
        agreement_within_1: share whose stances differ by at most 1, in [0, 1].
        mean_abs_difference: mean |stance A - stance B| over those candidates.
        cites_per_input_a, cites_per_input_b: how often each input was cited, per run.
    """

    model_config = ConfigDict(extra="forbid")

    run_a: str
    run_b: str
    lens: str
    rows: list[CandidateComparison]
    compared: int
    agreement_exact: float
    agreement_within_1: float
    mean_abs_difference: float
    cites_per_input_a: dict[str, int]
    cites_per_input_b: dict[str, int]

    def render(self) -> str:
        """The plain-text report the command prints."""
        lines = [f"lens {self.lens}: {self.run_a} (A) vs {self.run_b} (B)"]
        for row in self.rows:
            lines.append(f"{row.candidate}")
            for tag, v in (("A", row.a), ("B", row.b)):
                lines.append(
                    f"  {tag}: {v.status} stance={v.stance} conviction={v.conviction}"
                    f" cites={','.join(v.cited_inputs) or '-'}"
                )
        lines += [
            f"compared (both ok): {self.compared} of {len(self.rows)}",
            f"stance agreement: exact {self.agreement_exact:.0%}, within 1 {self.agreement_within_1:.0%}",
            f"mean |stance difference|: {self.mean_abs_difference:.2f}",
            f"cites per input A: {dict(sorted(self.cites_per_input_a.items()))}",
            f"cites per input B: {dict(sorted(self.cites_per_input_b.items()))}",
        ]
        return "\n".join(lines)


def _input_name(cite: str) -> str:
    """The input a cite id points into: `profitability.roe_mean` -> `profitability`."""
    return re.split(r"[.\[]", cite, maxsplit=1)[0]


def _summarise(verdict: LensVerdict | None) -> RunVerdict:
    """Reduce a verdict (None: the lens is missing from the dossier) to a `RunVerdict`."""
    if verdict is None:
        return RunVerdict(status="missing")
    cited = sorted({_input_name(c) for claim in verdict.claims for c in claim.cites})
    return RunVerdict(
        status=verdict.status,
        stance=verdict.stance,
        conviction=verdict.conviction,
        cited_inputs=cited,
    )


def _dossiers(index: DuckDBRunIndex, blobs: FileBlobStore, run_id: str) -> dict[str, Dossier]:
    """The stored dossier of every candidate of `run_id`, by candidate id."""
    config = index.run_config(run_id)
    panel = config.get("panel") or {}
    aggregator = panel.get("aggregator", "dossier")
    out: dict[str, Dossier] = {}
    for result in index.node_results(run_id):
        if result.key.name != aggregator or result.key.candidate is None or result.output_hash is None:
            continue
        dossier = blobs.get(result.output_hash)
        if isinstance(dossier, Dossier):
            out[result.key.candidate] = dossier
    return out


def _cite_counts(dossiers: dict[str, Dossier], lens: str) -> dict[str, int]:
    """How many claim cites each input received across `dossiers`' verdicts of `lens`."""
    counts: Counter[str] = Counter()
    for dossier in dossiers.values():
        for verdict in dossier.verdicts:
            if verdict.lens == lens:
                counts.update(_input_name(c) for claim in verdict.claims for c in claim.cites)
    return dict(counts)


def compare(store_root: Path, run_a: str, run_b: str, lens: str = "quality_value") -> VariantComparison:
    """Compare `lens` between two runs of the store at `store_root`, from its run index and blobs.

    Rows cover candidates with a dossier in both runs, sorted by id. The agreement figures use the
    candidates where both runs have an `ok` verdict (0.0 when there are none).
    """
    store_root = Path(store_root)
    index = DuckDBRunIndex(store_root / "index.duckdb")
    try:
        blobs = FileBlobStore(store_root / "blobs")
        dossiers_a, dossiers_b = _dossiers(index, blobs, run_a), _dossiers(index, blobs, run_b)
    finally:
        index.close()
    rows = []
    for candidate in sorted(set(dossiers_a) & set(dossiers_b)):
        pick = [
            next((v for v in d[candidate].verdicts if v.lens == lens), None)
            for d in (dossiers_a, dossiers_b)
        ]
        rows.append(
            CandidateComparison(candidate=candidate, a=_summarise(pick[0]), b=_summarise(pick[1]))
        )
    diffs = [
        abs(r.a.stance - r.b.stance)
        for r in rows
        if r.a.status == "ok" and r.b.status == "ok" and r.a.stance is not None and r.b.stance is not None
    ]
    n = len(diffs)
    return VariantComparison(
        run_a=run_a,
        run_b=run_b,
        lens=lens,
        rows=rows,
        compared=n,
        agreement_exact=sum(d == 0 for d in diffs) / n if n else 0.0,
        agreement_within_1=sum(d <= 1 for d in diffs) / n if n else 0.0,
        mean_abs_difference=sum(diffs) / n if n else 0.0,
        cites_per_input_a=_cite_counts(dossiers_a, lens),
        cites_per_input_b=_cite_counts(dossiers_b, lens),
    )


@click.command()
@click.argument("run_a")
@click.argument("run_b")
@click.option("--lens", default="quality_value", show_default=True, help="Lens whose verdicts to compare.")
@click.option(
    "--store",
    type=click.Path(path_type=Path),
    help="Store root (default: LENSGRAPH_STORE_ROOT, else .lensgraph).",
)
def main(run_a: str, run_b: str, lens: str, store: Path | None) -> None:
    """Print RUN_A's and RUN_B's verdicts of one lens side by side, with an agreement summary."""
    click.echo(compare(store if store is not None else Settings().store_root, run_a, run_b, lens).render())


if __name__ == "__main__":
    main()
