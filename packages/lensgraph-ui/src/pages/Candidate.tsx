/** Candidate page: dossier headline, per-lens verdicts with claim drill-down, and the review. */
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardHeader from "@mui/material/CardHeader";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Facts } from "../components/Facts";
import Button from "@mui/material/Button";
import { fmt } from "../format";
import { listNeighbours, orderedCandidateIds } from "../listOrder";
import { candidateHref, routeList, summaryHref, useRoute } from "../router";
import { useRun } from "../store";
import { CandidateGraph } from "../components/CandidateGraph";
import { statusColor } from "../theme";
import type { CandidateView, DossierReview, Flag, LensVerdict, ReviewPoint } from "../types/run-view";
import { Cites } from "../components/Cites";

/** A lens/node status as a chip coloured from the theme's status palette. */
function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      size="small"
      label={status}
      sx={{ bgcolor: (t) => statusColor(t, status), color: (t) => t.palette.getContrastText(statusColor(t, status)) }}
    />
  );
}

function FlagItem({ flag, cites }: { flag: Flag; cites?: Record<string, string | null> }) {
  const color = flag.severity === "veto" ? "error" : flag.severity === "warn" ? "warning" : "info";
  return (
    <Alert severity={color} icon={false} sx={{ py: 0 }}>
      <strong>{flag.severity}</strong> {flag.code}: {flag.text} {cites && <Cites cites={cites} />}
    </Alert>
  );
}

/** Lens version always; model, attempts and tokens only for model-backed verdicts. */
function provenanceText(p: LensVerdict["provenance"]): string {
  const base = `v${p.lens_version}`;
  if (!p.model) return base;
  return `${base}, ${p.model}${p.variant ? `, ${p.variant}` : ""}, ${p.attempts ?? 0} attempt(s), ` +
    `${p.input_tokens ?? 0}/${p.output_tokens ?? 0} tokens`;
}

function VerdictCard({ verdict, candidate }: { verdict: LensVerdict; candidate: CandidateView }) {
  const p = verdict.provenance;
  const claimRefs = candidate.claims.filter((r) => r.lens === verdict.lens);
  const flagRefs = candidate.flags.filter((r) => r.lens === verdict.lens);
  const list = (o?: Record<string, number>) =>
    Object.entries(o ?? {}).map(([k, v]) => `${k} ${fmt(v)}`).join(", ") || "—";
  return (
    <Card variant="outlined" aria-label={`Verdict ${verdict.lens}`} component="article">
      <CardHeader title={verdict.lens} action={<StatusChip status={verdict.status} />} sx={{ pb: 0 }} />
      <CardContent>
        <Facts
          facts={[
            { label: "Stance", value: `${verdict.stance ?? "—"} (mean ${fmt(verdict.stance_mean)})` },
            { label: "Conviction", value: verdict.conviction ?? "—" },
            { label: "Coverage", value: fmt(verdict.coverage) },
            { label: "Input sufficiency", value: list(verdict.input_sufficiency) },
            { label: "Components", value: list(verdict.components) },
            { label: "Provenance", value: provenanceText(p) },
          ]}
        />
        {verdict.error && (
          <Alert severity={verdict.status === "abstained" ? "info" : "error"} sx={{ mt: 1 }}>
            {verdict.status === "abstained" ? "Abstained" : "Error"}: {verdict.error}
          </Alert>
        )}
        <Stack spacing={0.75} sx={{ mt: 1 }}>
          {(verdict.claims ?? []).map((claim, i) => (
            <Box key={i}>
              <Typography variant="body2" component="span">{claim.text}</Typography>{" "}
              <Cites
                cites={claimRefs.find((r) => r.claim_index === i)?.cites ??
                  Object.fromEntries(claim.cites.map((c) => [c, null]))}
              />
            </Box>
          ))}
          {(verdict.flags ?? []).map((flag, i) => (
            <FlagItem key={`f${i}`} flag={flag} cites={flagRefs.find((r) => r.flag_index === i)?.cites} />
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

/** A review point: its text, then the priority badge (if set), then each cite as a chip. */
function ReviewPointRow({ point }: { point: ReviewPoint }) {
  return (
    <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
      <Typography variant="body2" component="span">{point.text}</Typography>
      {point.priority && <Chip size="small" color="secondary" className="badge" label={`priority: ${point.priority}`} />}
      {point.cites.map((c) => <Chip key={c} size="small" variant="outlined" className="chip" label={c} />)}
    </Stack>
  );
}

function ReviewCard({ review }: { review: DossierReview }) {
  const section = (title: string, items: DossierReview["fit"]) =>
    (items ?? []).length > 0 && (
      <Box sx={{ mt: 1 }}>
        <Typography variant="subtitle2">{title}</Typography>
        <Stack spacing={0.75}>{(items ?? []).map((pt, i) => <ReviewPointRow key={i} point={pt} />)}</Stack>
      </Box>
    );
  return (
    <Card variant="outlined" aria-label="Review" component="section">
      <CardHeader title="Review" sx={{ pb: 0 }} />
      <CardContent>
        <Typography variant="body1">{review.summary}</Typography>
        {section("Fit", review.fit)}
        {section("Gaps", review.gaps)}
        <Stack spacing={0.5} sx={{ mt: 1 }}>
          {(review.flags ?? []).map((f, i) => <FlagItem key={i} flag={f} />)}
        </Stack>
      </CardContent>
    </Card>
  );
}

/** Back to the list, and Previous/Next along the list's current sort and filter order. */
function ListNav({ id }: { id: string }) {
  const run = useRun();
  const list = routeList(useRoute());
  const pos = listNeighbours(orderedCandidateIds(run, list), id);
  const step = (label: string, target: string | null) =>
    target ? (
      <Button size="small" href={candidateHref(target, list)}>{label}</Button>
    ) : (
      <Button size="small" disabled>{label}</Button>
    );
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <Button size="small" href={summaryHref(list)}>Back to list</Button>
      {step("Previous", pos.prev)}
      {step("Next", pos.next)}
      <Typography variant="body2" color="text.secondary">
        {pos.index >= 0 ? `${pos.index + 1} of ${pos.total}` : "not in the current list"}
      </Typography>
    </Stack>
  );
}

/** One candidate's dossier and review, from `RunView.candidates`. */
export function CandidatePage({ id }: { id: string }) {
  const run = useRun();
  const candidate = run.candidates.find((c) => c.id === id);
  if (!candidate) return <Alert severity="error">Unknown candidate {id}</Alert>;
  const { dossier, review } = candidate.record;
  return (
    <Stack spacing={2}>
      <ListNav id={id} />
      <Typography variant="h5" component="h1">Candidate {candidate.id}</Typography>
      <Facts
        facts={[
          { label: "Overall stance", value: fmt(dossier.overall_stance) },
          { label: "Direction", value: fmt(dossier.direction) },
          { label: "Confidence", value: fmt(dossier.confidence) },
          { label: "Evidence share", value: fmt(dossier.evidence_share) },
          { label: "Agreement", value: fmt(dossier.agreement) },
        ]}
      />
      {dossier.flags.map((f, i) => <FlagItem key={i} flag={f} />)}
      <Typography variant="h6" component="h2">Verdicts</Typography>
      {dossier.verdicts.map((v) => <VerdictCard key={v.lens} verdict={v} candidate={candidate} />)}
      <CandidateGraph id={id} />
      {review && <ReviewCard review={review} />}
    </Stack>
  );
}
