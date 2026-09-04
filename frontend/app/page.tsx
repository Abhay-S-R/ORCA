"use client";

// ORCA public landing page — the admiralty-chart cover page for the product:
// what it is, in one screen, before a visitor ever opens the console.
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Compass,
  Fish,
  Navigation,
  Shield,
  Workflow,
} from "lucide-react";
import { OrcaMark } from "./nav";
import { type Persona } from "./persona/config";
import { usePersona } from "./persona/context";

const STATS = [
  { label: "Agents in the crew", value: "10" },
  { label: "Command stations", value: "4" },
  { label: "Languages", value: "English + தமிழ்" },
  { label: "Coastline covered", value: "7,516 km" },
  { label: "Data edition", value: "Live" },
];

const STAKEHOLDER_STATIONS = [
  {
    id: "fisherman" as const,
    title: "Fisherman",
    tagline: "An unambiguous go / no-go, in your own language, with the nearest fishing zone on the chart.",
    bullets: ["Plain-language safety verdict", "Daily Potential Fishing Zones", "Voice in, voice back out"],
    icon: Fish,
  },
  {
    id: "commercial_navigator" as const,
    title: "Commercial Navigator",
    tagline: "Passage planning across boundary standoff, bathymetry and tide windows for a whole leg.",
    bullets: ["Route corridor by segment", "EEZ / IMBL standoff radar", "Berthing tide windows"],
    icon: Navigation,
  },
  {
    id: "researcher" as const,
    title: "Researcher",
    tagline: "The full reasoning trace behind a verdict, with every figure attributed and exportable.",
    bullets: ["Ten-agent reasoning trace", "Chlorophyll & SST trends", "CSV / JSON export"],
    icon: Workflow,
  },
  {
    id: "coastal_authority" as const,
    title: "Coastal Authority",
    tagline: "A district-wide risk board and CAP-shaped alert preview for the day's advisory.",
    bullets: ["Coastal risk board, ranked", "CAP 1.2 alert preview", "One-click evidence export"],
    icon: Shield,
  },
];

const HOW_IT_DECIDES = [
  { title: "Understand", body: "Parse the question — language, place, time — no model in the loop yet." },
  { title: "Gather", body: "Independent specialists fan out concurrently: weather, ocean, hazards, boundaries." },
  { title: "Decide", body: "A weighted read of the evidence, floored by safety rules that only ever raise the alert." },
  { title: "Explain", body: "Plain words, in your language, every figure carrying the dataset it came from." },
];

const TRY_QUERIES = [
  "Is it safe to go out tomorrow morning near Thoothukudi?",
  "Where are the fishing zones closest to my port?",
  "How far am I from the maritime boundary?",
];

export default function LandingPage() {
  const router = useRouter();
  const { setPersona } = usePersona();
  const reduce = useReducedMotion();
  const stationSectionRef = useRef<HTMLDivElement>(null);
  const [openStation, setOpenStation] = useState<Persona | null>(null);

  function launchWithPersona(id: Persona) {
    setPersona(id);
    router.push("/ask");
  }

  return (
    <div className="min-h-screen bg-abyss text-ink">
      <div className="pointer-events-none fixed inset-0 chart-grid" aria-hidden="true" />

      <div className="relative mx-auto max-w-6xl px-6 py-8 sm:px-10">
        {/* Top bar */}
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <OrcaMark className="size-9" />
            <span className="font-mono text-[11px] font-semibold tracking-widest text-ink-dim uppercase">
              SIH26176 · Marine EcOsystem Reasoning with Collaborative Agents
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-medium text-ink-muted hover:text-ink">
              Sign in
            </Link>
            <Link
              href="/ask"
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink bg-ink px-4 py-2 text-sm font-bold text-on-accent transition-transform hover:scale-[1.02] active:scale-[0.98]"
            >
              Open ORCA
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </header>

        {/* Hero */}
        <section className="mt-16 grid gap-10 lg:grid-cols-[1.2fr_1fr] lg:items-center">
          <div>
            <motion.h1
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="font-display text-6xl font-black tracking-tight text-ink sm:text-8xl"
            >
              ORCA
            </motion.h1>
            <svg viewBox="0 0 220 12" className="mt-1 h-3 w-56 text-ocean-cyan/60" aria-hidden="true">
              <path d="M2 6 Q 20 -2, 38 6 T 74 6 T 110 6 T 146 6 T 182 6 T 218 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>

            <p className="mt-6 max-w-lg font-display text-2xl leading-snug font-semibold text-ink sm:text-3xl">
              Ten agents read the sea. One safe,{" "}
              <span className="text-ocean-cyan">explainable</span> decision.
            </p>

            <p className="mt-5 max-w-xl text-sm leading-relaxed text-ink-muted sm:text-base">
              ORCA fuses ISRO satellite observation, INCOIS ocean advisories, IMD weather and GIS boundary
              geofences into one conversation — a fisherman, a navigator, a researcher and a coastal authority
              each get the same underlying facts, rendered for what they actually decide.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => launchWithPersona("fisherman")}
                className="inline-flex items-center gap-2 rounded-lg border border-ink bg-ink px-5 py-2.5 text-sm font-bold text-on-accent transition-transform hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
              >
                Open ORCA
                <ArrowRight className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => stationSectionRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" })}
                className="rounded-lg border border-hairline-strong bg-shelf-1 px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-shelf-2 cursor-pointer"
              >
                Explore command stations
              </button>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-mono font-semibold text-ink-dim uppercase tracking-wider">
                Try:
              </span>
              {TRY_QUERIES.map((q) => (
                <Link
                  key={q}
                  href={`/ask?q=${encodeURIComponent(q)}`}
                  className="rounded-full border border-hairline bg-shelf-1 px-3 py-1 text-xs text-ink-muted underline decoration-hairline-strong decoration-dotted underline-offset-4 transition-colors hover:border-ocean-cyan/50 hover:text-ink"
                >
                  {q}
                </Link>
              ))}
            </div>
          </div>

          {/* Chart illustration */}
          <div className="relative mx-auto aspect-square w-full max-w-sm">
            <svg viewBox="0 0 200 200" className="size-full text-ink-dim/25" aria-hidden="true">
              <circle cx="100" cy="100" r="98" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <circle cx="100" cy="100" r="70" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <circle cx="100" cy="100" r="40" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <path d="M100 2 V198 M2 100 H198" stroke="currentColor" strokeWidth="0.5" />
            </svg>
            <div className="absolute inset-0 grid place-items-center">
              <OrcaMark className="size-24" />
            </div>
            <div className="absolute top-6 right-4 rounded-full border border-go/40 bg-shelf-1 px-2.5 py-1 text-[10px] font-mono font-semibold text-go shadow-sm">
              GO · 47.6 nm clear
            </div>
            <div className="absolute bottom-8 left-2 rounded-full border border-hairline-strong bg-shelf-1 px-2.5 py-1 text-[10px] font-mono font-semibold text-ink-muted shadow-sm">
              PFZ · 12.4 km
            </div>
          </div>
        </section>

        {/* Stat strip */}
        <section className="mt-16 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-hairline bg-hairline sm:grid-cols-5">
          {STATS.map((s) => (
            <div key={s.label} className="bg-shelf-1 p-4">
              <p className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">{s.label}</p>
              <p className="mt-1 font-display text-2xl font-bold text-ink">{s.value}</p>
            </div>
          ))}
        </section>

        {/* Command stations */}
        <section ref={stationSectionRef} className="mt-20 scroll-mt-10">
          <h2 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            One ground truth, four command stations
          </h2>
          <p className="mt-2 max-w-xl text-sm text-ink-muted">
            The underlying facts never change with who&apos;s asking — only the structure of the answer does.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STAKEHOLDER_STATIONS.map((station) => {
              const Icon = station.icon;
              const open = openStation === station.id;
              return (
                <div
                  key={station.id}
                  onMouseEnter={() => setOpenStation(station.id)}
                  onMouseLeave={() => setOpenStation((s) => (s === station.id ? null : s))}
                  className="flex flex-col justify-between rounded-xl border border-hairline bg-shelf-1 p-5 shadow-sm transition-colors hover:border-hairline-strong"
                >
                  <div>
                    <div className={`grid size-9 place-items-center rounded-lg border ${open ? "border-ocean-cyan/50 bg-ocean-cyan/10 text-ocean-cyan" : "border-hairline text-ink-dim"}`}>
                      <Icon className="size-4.5" />
                    </div>
                    <h3 className="mt-3.5 font-display text-lg font-bold text-ink">{station.title}</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">{station.tagline}</p>
                    <ul className="mt-3.5 space-y-1.5 border-t border-hairline/70 pt-3">
                      {station.bullets.map((b) => (
                        <li key={b} className="flex items-start gap-1.5 text-[11px] text-ink-dim">
                          <span className="mt-1 size-1 shrink-0 rounded-full bg-ocean-cyan/60" />
                          {b}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <button
                    type="button"
                    onClick={() => launchWithPersona(station.id)}
                    className="mt-5 flex w-full items-center justify-center gap-1.5 rounded-lg border border-hairline-strong bg-shelf-2 py-2 text-xs font-bold text-ink transition-colors hover:bg-ink hover:text-on-accent cursor-pointer"
                  >
                    Open
                    <ArrowRight className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        {/* How ORCA decides */}
        <section className="mt-20 border-t border-hairline pt-10">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              How ORCA decides
            </h2>
            <span className="font-mono text-[11px] text-ink-dim">
              deterministic safety floors · nothing hidden
            </span>
          </div>

          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_DECIDES.map((step, i) => (
              <div key={step.title} className="relative">
                <div className="flex items-center gap-2">
                  <Compass className="size-4 text-ocean-cyan" />
                  <h3 className="font-display text-lg font-bold text-ink">{step.title}</h3>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">{step.body}</p>
                {i < HOW_IT_DECIDES.length - 1 && (
                  <ArrowRight className="absolute top-1 -right-5 hidden size-4 text-ink-dim/50 lg:block" />
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className="mt-20 border-t border-hairline pt-8 pb-12">
          <div className="flex flex-wrap justify-center gap-6 text-xs text-ink-dim">
            <Link href="/ask" className="hover:text-ink">Ask</Link>
            <Link href="/safety" className="hover:text-ink">Safety</Link>
            <Link href="/map" className="hover:text-ink">Chart</Link>
            <Link href="/voyage" className="hover:text-ink">Voyage</Link>
            <Link href="/zones" className="hover:text-ink">Fishing zones</Link>
            <Link href="/reasoning" className="hover:text-ink">Reasoning</Link>
          </div>
          <p className="mt-4 text-center text-xs text-ink-dim">
            ORCA — Marine EcOsystem Reasoning with Collaborative Agents. Decision support, never a replacement
            for an official advisory. Always follow the Coast Guard and government warnings.
          </p>
        </footer>
      </div>
    </div>
  );
}
