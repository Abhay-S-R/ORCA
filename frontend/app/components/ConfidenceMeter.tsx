// Confidence as three discrete segments, not a percentage bar.
//
// This is a Ground Rule 3 decision: the backend emits a TIER, and a smooth
// 0-100 bar would invent a precision the tier does not have. Three notches
// say "one of three" honestly. The tier word is always rendered too, so the
// meter is reinforcement rather than the only carrier.
import { confidenceClass, confidenceLabel, type ConfidenceTier } from "./Badge";

const FILLED: Record<ConfidenceTier, number> = { LOW_DATA: 1, MEDIUM: 2, HIGH: 3 };

export function ConfidenceMeter({ tier }: { tier: ConfidenceTier }) {
  const filled = FILLED[tier];
  const cls = confidenceClass(tier);

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-1" role="img" aria-label={`Confidence: ${confidenceLabel(tier)} (${filled} of 3)`}>
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={`h-1 w-5 rounded-full ${n <= filled ? `bg-current ${cls}` : "bg-hairline"}`}
          />
        ))}
      </div>
      <span className={`text-[11px] font-medium ${cls}`}>{confidenceLabel(tier)} confidence</span>
    </div>
  );
}
