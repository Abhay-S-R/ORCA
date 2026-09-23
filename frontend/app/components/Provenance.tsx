// P4.6 (`R-NEW-9`) — the five-tier provenance legend. Provenance (where a
// number came from) and confidence (how much to trust it) are orthogonal —
// `Badge`'s `ConfidenceTier` already covers the second axis; this covers the
// first, which the product had no vocabulary for at all until this point.
//
// LIVE and REFERENCE/DERIVED are computed from data the backend already
// exposes (freshness class, authority tier, whether an agent's own citation
// is the deterministic safety engine itself) rather than guessed from a
// dataset's display name — a wrong guess here would be exactly the kind of
// fabricated label principle 1 forbids applying to a number's origin, not
// just to the number itself. DEMO is reserved for `/demo` (P6.6) fixture
// runs, which can pass `isDemo` once that surface exists.
export type ProvenanceTier = "LIVE" | "REFERENCE" | "DERIVED" | "DEMO" | "MISSING";

export const PROVENANCE_LEGEND: { tier: ProvenanceTier; dot: string; label: string; detail: string }[] = [
  { tier: "LIVE", dot: "🟢", label: "Live", detail: "Fetched for this query, or a periodically-refreshed feed" },
  { tier: "REFERENCE", dot: "🔵", label: "Reference", detail: "Static geometry or tables — does not go stale" },
  { tier: "DERIVED", dot: "🟡", label: "Derived", detail: "Computed by ORCA itself, not fetched from anywhere" },
  { tier: "DEMO", dot: "🟣", label: "Demo", detail: "A pinned fixture, run for the guided demonstration" },
  { tier: "MISSING", dot: "⚪", label: "Missing", detail: "No value — never shown as a number" },
];

const TIER_DOT_CLASS: Record<ProvenanceTier, string> = {
  LIVE: "bg-go",
  REFERENCE: "bg-ocean-cyan",
  DERIVED: "bg-caution",
  DEMO: "bg-accent",
  MISSING: "bg-ink-dim/40",
};

export function ProvenanceDot({ tier, className = "" }: { tier: ProvenanceTier; className?: string }) {
  const legend = PROVENANCE_LEGEND.find((l) => l.tier === tier);
  return (
    <span
      aria-hidden="true"
      title={legend ? `${legend.label} — ${legend.detail}` : tier}
      className={`inline-block size-1.5 rounded-full ${TIER_DOT_CLASS[tier]} ${className}`}
    />
  );
}

export function ProvenanceBadge({ tier }: { tier: ProvenanceTier }) {
  const legend = PROVENANCE_LEGEND.find((l) => l.tier === tier);
  return (
    <span
      className="inline-flex items-center gap-1 text-[9px] font-semibold tracking-wide text-ink-dim uppercase"
      title={legend?.detail}
    >
      <ProvenanceDot tier={tier} />
      {legend?.label ?? tier}
    </span>
  );
}

export function ProvenanceLegend({ className = "" }: { className?: string }) {
  return (
    <ul className={`space-y-1 ${className}`}>
      {PROVENANCE_LEGEND.map((l) => (
        <li key={l.tier} className="flex items-start gap-2">
          <ProvenanceDot tier={l.tier} className="mt-1" />
          <div className="min-w-0">
            <span className="font-medium text-ink-muted">{l.label}</span>{" "}
            <span className="text-ink-dim">— {l.detail}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// `/ask`'s citations carry only {agent_name, dataset, acquisition_timestamp,
// freshness_minutes} — no authority tier or freshness class. Two rules that
// hold with certainty from that shape alone: the safety engine's own
// citation is computed, never fetched, and a `0`-minute freshness is this
// codebase's existing convention for "static reference" (SourceChip's
// freshnessLabel already reads it that way). Everything else carries a real
// acquisition timestamp for a real reading, live or periodically cached.
export function provenanceTierForCitation(agentName: string, freshnessMinutes: number | undefined): ProvenanceTier {
  if (agentName === "risk_assessment") return "DERIVED";
  if (freshnessMinutes === 0) return "REFERENCE";
  return "LIVE";
}

// `/data` rows carry the fuller picture: `authority_tier` (TIER3 is already
// labelled "derived" in this codebase's own TIER_LABEL), `freshness_class`
// and whether the source is actually fetched live right now.
export function provenanceTierForSource(source: {
  authority_tier?: string;
  freshness_class?: "LIVE" | "DAILY" | "WEEKLY" | "STATIC" | null;
  fetched_live?: boolean;
}): ProvenanceTier {
  if (source.authority_tier === "TIER3") return "DERIVED";
  if (source.freshness_class === "STATIC") return "REFERENCE";
  if (source.fetched_live) return "LIVE";
  if (source.freshness_class === "LIVE" || source.freshness_class === "DAILY" || source.freshness_class === "WEEKLY") {
    return "LIVE";
  }
  return "REFERENCE";
}
