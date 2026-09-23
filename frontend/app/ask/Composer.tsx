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
      className={centered ? "mx-auto w-full max-w-3xl" : "w-full"}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(value);
        }}
        className={`flex flex-col gap-4 rounded-2xl border border-hairline/70 bg-shelf-1/90 p-4 sm:p-5 backdrop-blur-sm transition-shadow ${centered ? "shadow-2xl" : "shadow-md"
          }`}
      >
        <div className="flex items-center gap-2.5">
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
              // P4.4 — "≥18px body, maximum sunlight contrast" on the
              // fisherman surface: the question box is the one piece of text
              // every fisherman query starts from.
              className={`w-full rounded-xl border border-hairline bg-shelf-1/90 px-4 py-3 text-ink placeholder:text-ink-dim/60 transition-all hover:border-hairline-strong focus:border-ocean-cyan/70 focus:bg-shelf-2/90 shadow-inner outline-none ${
                isFisherman ? "text-lg" : "text-sm sm:text-base"
              }`}
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
            icon={<Send className="size-3.5" />}
            className="h-[44px] min-w-[80px] px-5 text-sm font-bold"
          >
            {disabled ? "Asking…" : "Ask"}
          </Button>
        </div>

        {presets && presets.length > 0 && (
          <div className="border-t border-hairline/50 pt-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {presets.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => onSubmit(label)}
                  disabled={disabled}
                  className="flex items-center gap-2 rounded-xl border border-hairline/60 bg-shelf-2/50 px-3 py-2 text-xs text-ink-muted text-left transition-all hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-50"
                >
                  <Icon className="size-3.5 shrink-0 text-ocean-cyan/80" aria-hidden="true" />
                  <span className="truncate">{label}</span>
                </button>
              ))}
            </div>
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
