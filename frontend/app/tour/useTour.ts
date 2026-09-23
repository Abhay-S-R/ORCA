"use client";

// P4.9 (R-UX-5) — "no tour library: framer-motion and a useTour() hook."
// State lives in localStorage so the tour is resumable across a reload and,
// per the point's own Done-when, never shown twice once finished.
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "orca.tour.v1";

export type TourState = {
  active: boolean;
  step: 1 | 2 | 3 | 4 | 5;
  completed: boolean;
};

const DEFAULT_STATE: TourState = { active: false, step: 1, completed: false };

function read(): TourState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_STATE, ...JSON.parse(raw) };
  } catch {
    /* storage disabled — the tour just starts fresh every time */
  }
  return DEFAULT_STATE;
}

function write(state: TourState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* not remembered — the tour still works for this page view */
  }
}

export function useTour() {
  const [state, setState] = useState<TourState>(DEFAULT_STATE);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage only exists after mount
    setState(read());
  }, []);

  const start = useCallback(() => {
    const next: TourState = { active: true, step: 1, completed: false };
    write(next);
    setState(next);
  }, []);

  const advance = useCallback(() => {
    setState((s) => {
      const next: TourState = s.step >= 5 ? { active: false, step: 1, completed: true } : { ...s, step: (s.step + 1) as TourState["step"] };
      write(next);
      return next;
    });
  }, []);

  const skip = useCallback(() => {
    const next: TourState = { active: false, step: 1, completed: true };
    write(next);
    setState(next);
  }, []);

  return { ...state, start, advance, skip };
}
