"use client";

// The input bar — one rounded pill, one instance, rendered either centered (fresh thread, no
// turns yet) or docked to the bottom of the thread column. `layoutId` gives
// Framer Motion the two positions to FLIP between on the same commit that
// the first ask() swaps page.tsx from one layout to the other.
import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { ArrowUp, Loader2, type LucideIcon } from "lucide-react";
import { VoiceMicButton, VoiceInputPanel, type VoiceInputState } from "../components/VoiceInput";

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  voice,
  isFisherman,
  centered,
  presets,
  leading,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (q: string) => void;
  disabled: boolean;
  voice: VoiceInputState;
  isFisherman: boolean;
  centered: boolean;
  presets?: { label: string; icon: LucideIcon }[];
  // The control at the left of the pill (the vessel button). Null for a signed-out visitor.
  leading?: ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  const canSend = !disabled && value.trim().length > 0;

  return (
    // One width for the whole page (PLAN-ASK-3): the thread and this box sit in the same centred column, so the box is
    // the same size with the chat sidebar open or closed.
    <motion.div
      layout={!reduceMotion}
      layoutId="ask-composer"
      transition={{ type: "spring", stiffness: 380, damping: 38 }}
      className="mx-auto w-full max-w-4xl"
    >
      {/* PLAN-ASK-2: the input box only, as in ChatGPT's: one rounded pill, the field inside it, the mic and a round
          send button at its right, the vessel control where ChatGPT keeps its "+". No card around it, no second
          bordered field, no "Ask" word button. */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) onSubmit(value);
        }}
        className={`flex items-center gap-1 rounded-full border border-hairline/70 bg-shelf-1/95 py-1.5 pr-1.5 pl-2 backdrop-blur-sm transition-shadow focus-within:border-ocean-cyan/60 ${
          centered ? "shadow-2xl" : "shadow-lg"
        }`}
      >
        {leading}
        <label htmlFor="query" className="sr-only">
          Your question about marine conditions
        </label>
        <input
          id="query"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Is it safe to go out tomorrow morning?"
          autoFocus={centered}
          autoComplete="off"
          // P4.4 — "≥18px body, maximum sunlight contrast" on the fisherman surface: the question box is the one piece
          // of text every fisherman query starts from.
          className={`min-w-0 flex-1 bg-transparent px-2 py-2.5 text-ink outline-none placeholder:text-ink-dim/60 ${
            isFisherman ? "text-lg" : "text-sm sm:text-base"
          } ${leading ? "" : "pl-3"}`}
        />
        {/* Voice ingress (plan §6 D1 Day 16-17): the mic sits beside send since both feed the same query pipeline: voice
            is a pre-step onto the text box, not a second, separate control. */}
        <VoiceMicButton voice={voice} isFisherman={false} quiet />
        <button
          type="submit"
          disabled={!canSend}
          aria-label={disabled ? "Asking" : "Ask"}
          title={disabled ? "Asking…" : "Ask"}
          className="grid size-10 shrink-0 place-items-center rounded-full bg-ocean-cyan text-on-accent transition-all hover:bg-ocean-cyan/90 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-shelf-3 disabled:text-ink-dim/60"
        >
          {disabled ? <Loader2 className="size-[18px] animate-spin" aria-hidden="true" /> : <ArrowUp className="size-5" aria-hidden="true" />}
        </button>
      </form>

      {/* Waveform while recording, transcript confirmation once done — requires an explicit "Ask" before it becomes a
          query, never auto-submitted (a mishearing on a safety query is a safety incident, not a UX annoyance). */}
      <div className="mt-2">
        <VoiceInputPanel voice={voice} />
      </div>

      {presets && presets.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {presets.map(({ label, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => onSubmit(label)}
              disabled={disabled}
              className="flex items-center gap-2 rounded-2xl border border-hairline/60 bg-shelf-2/40 px-3.5 py-2.5 text-left text-xs text-ink-muted transition-all hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-50"
            >
              <Icon className="size-3.5 shrink-0 text-ocean-cyan/80" aria-hidden="true" />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </div>
      )}
    </motion.div>
  );
}
