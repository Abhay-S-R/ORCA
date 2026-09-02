// The inline "dataset · timestamp · confidence" display (plan §4 S4 Day 4).
// Exit criterion 4 ("every number on screen carries dataset + timestamp")
// depends on this existing — the click-through provenance popover is Phase 2.
import { Badge, confidenceTone, type BadgeTone } from "./Badge";

export function SourceChip({
  dataset,
  acquisitionTimestamp,
  confidenceTier,
}: {
  dataset: string;
  acquisitionTimestamp: string;
  confidenceTier?: "HIGH" | "MEDIUM" | "LOW_DATA";
}) {
  const when = formatTimestamp(acquisitionTimestamp);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs text-black/60">
      <span className="font-medium text-black/80">{dataset}</span>
      <span aria-hidden="true">·</span>
      <time dateTime={acquisitionTimestamp}>{when}</time>
      {confidenceTier && (
        <>
          <span aria-hidden="true">·</span>
          <Badge tone={confidenceTone(confidenceTier) as BadgeTone}>{confidenceTier.replace("_", "-")}</Badge>
        </>
      )}
    </span>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
