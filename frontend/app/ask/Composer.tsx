"use client";

// The input bar — one instance, rendered either centered (fresh thread, no
// turns yet) or docked to the bottom of the thread column. `layoutId` gives
// Framer Motion the two positions to FLIP between on the same commit that
// the first ask() swaps page.tsx from one layout to the other.
import { motion, useReducedMotion } from "framer-motion";
import { Send, type LucideIcon } from "lucide-react";
import { Button } from "../components/Button";
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
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (q: string) => void;
  disabled: boolean;
  voice: VoiceInputState;
  isFisherman: boolean;
  centered: boolean;
  presets?: { label: string; icon: LucideIcon }[];
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      layout={!reduceMotion}
      layoutId="ask-composer"
      transition={{ type: "spring", stiffness: 380, damping: 38 }}
      className={centered ? "mx-auto w-full max-w-2xl" : "w-full"}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(value);
        }}
        className={`flex flex-col gap-3 rounded-2xl border border-hairline/70 bg-shelf-1/90 p-3.5 backdrop-blur-sm transition-shadow ${
          centered ? "shadow-2xl" : "shadow-md"
        }`}
      >
        <div className="flex gap-2">
          <label htmlFor="query" className="sr-only">
            Your question about marine conditions
          </label>
          <div className="relative flex-1">
            <input
              id="query"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="Is it safe to go out tomorrow morning?"
              autoFocus={centered}
              className="w-full rounded-xl border border-hairline bg-shelf-1/90 px-4 py-3 text-sm text-ink placeholder:text-ink-dim/60 transition-all hover:border-hairline-strong focus:border-ocean-cyan/70 focus:bg-shelf-2/90 shadow-inner"
            />
          </div>
          {/* Voice ingress (plan §6 D1 Day 16-17): mic sits right next to Ask
              since both feed the same query pipeline — voice is a pre-step
              onto the text box, not a second, separate control. */}
          <VoiceMicButton voice={voice} isFisherman={isFisherman} />
          <Button
            type="submit"
            variant="primary"
            disabled={disabled || !value.trim()}
            icon={<Send className="size-4" />}
            className="px-5 font-bold"
          >
            {disabled ? "Asking" : "Ask"}
          </Button>
        </div>

        {presets && presets.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-2.5">
            <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              Try asking
            </span>
            {presets.map(({ label, icon: Icon }) => (
              <button
                key={label}
                type="button"
                onClick={() => onSubmit(label)}
                disabled={disabled}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-50"
              >
                <Icon className="size-3 shrink-0 text-ink-dim" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        )}
      </form>

      {/* Waveform while recording, transcript confirmation once done —
          requires an explicit "Ask" before it becomes a query, never
          auto-submitted (a mishearing on a safety query is a safety
          incident, not a UX annoyance). */}
      <VoiceInputPanel voice={voice} />
    </motion.div>
  );
}
