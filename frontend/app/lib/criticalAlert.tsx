"use client";

// P4.12 — the shared signal a critical band (the ≤1 nm boundary DANGER/
// INSIDE alert level, or a cyclone Red) needs to take the full screen from,
// on any route. The condition is already computed by every `/query` answer
// (`hazard_breakdown.imbl_alert_level`, `weather_summary.cyclone_alert`) —
// this context just carries the latest qualifying reading from wherever an
// answer streams in (`/ask`) to the one takeover component mounted in
// `AppChrome`, since that component sits outside `/ask`'s own tree.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type CriticalCondition = {
  kind: "boundary" | "cyclone";
  // DANGER/INSIDE for boundary; the cyclone's own alert level ("Red") for cyclone.
  level: string;
  distanceNm: number | null;
  queryId: string | null;
  raisedAt: number;
};

type CriticalAlertContextValue = {
  condition: CriticalCondition | null;
  raise: (c: Omit<CriticalCondition, "raisedAt">) => void;
  acknowledge: () => void;
};

const CriticalAlertContext = createContext<CriticalAlertContextValue | null>(null);

export function CriticalAlertProvider({ children }: { children: ReactNode }) {
  const [condition, setCondition] = useState<CriticalCondition | null>(null);

  const raise = useCallback((c: Omit<CriticalCondition, "raisedAt">) => {
    setCondition({ ...c, raisedAt: Date.now() });
  }, []);
  const acknowledge = useCallback(() => setCondition(null), []);

  const value = useMemo(() => ({ condition, raise, acknowledge }), [condition, raise, acknowledge]);
  return <CriticalAlertContext.Provider value={value}>{children}</CriticalAlertContext.Provider>;
}

export function useCriticalAlert(): CriticalAlertContextValue {
  const ctx = useContext(CriticalAlertContext);
  if (!ctx) throw new Error("useCriticalAlert must be used within CriticalAlertProvider");
  return ctx;
}
