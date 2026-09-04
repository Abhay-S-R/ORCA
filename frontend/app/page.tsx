"use client";

// Public entry point. No server data — three real product hooks stitched
// into one page: signing in (lib/auth, unchanged), choosing a persona (the
// same store the in-app PersonaSelector writes to, so a choice here is a
// choice there), and the pitch itself, which is just the Ask page's own
// "same facts, rendered per persona" idea (see PersonaAnswerMatrix) stated
// up front instead of discovered later.
import Link from "next/link";
import { useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { OrcaMark } from "./nav";
import { PERSONAS, type Persona } from "./persona/config";
import { usePersona } from "./persona/context";

const TECH = [
  "Next.js",
  "React",
  "Tailwind CSS",
  "Framer Motion",
  "MapLibre GL",
  "deck.gl",
  "FastAPI",
  "LangGraph",
  "PostgreSQL + PostGIS",
  "Shapely",
];

// What each persona's primary nav actually surfaces (persona/config.ts's
// visibility matrix) — the pitch is the product's own routing, not separate
// marketing copy that can drift from it.
const PERSONA_BLURB: Record<Exclude<Persona, "unresolved">, string> = {
  fisherman: "Go / no-go verdicts, safety alerts, nearest fishing zones.",
  commercial_navigator: "Voyage planning, boundary proximity, hazard charts.",
  researcher: "Trend charts, raw datasets, the full agent reasoning trace.",
  coastal_authority: "Fleet ops, threat levels, cross-vessel position reads.",
};

const PICKABLE = PERSONAS.filter((p) => p.id !== "unresolved") as {
  id: Exclude<Persona, "unresolved">;
  label: string;
}[];

const heroItem = {
  hidden: { opacity: 0, y: 12 },
  shown: { opacity: 1, y: 0 },
};

export default function LandingPage() {
  const router = useRouter();
  const { setPersona } = usePersona();
  const reduce = useReducedMotion();
  const personaSectionRef = useRef<HTMLDivElement>(null);

  // Persona is a rendering hint, same as the in-app selector (config.ts) —
  // picking one here just pre-sets that hint and drops you at the Ask page.
  function choosePersona(id: Persona) {
    setPersona(id);
    router.push("/ask");
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-20 px-5 py-16">
      <motion.section
        initial="hidden"
        animate="shown"
        variants={{ shown: { transition: { staggerChildren: reduce ? 0 : 0.12 } } }}
        className="flex flex-col items-center gap-5 text-center"
      >
        <motion.div variants={heroItem}>
          <OrcaMark className="size-14" animated />
        </motion.div>
        <motion.h1 variants={heroItem} className="text-4xl font-semibold tracking-tight text-ink">
          ORCA
        </motion.h1>
        <motion.p variants={heroItem} className="max-w-[52ch] text-[15px] leading-relaxed text-ink-muted">
          Twelve agents read live ocean, weather and maritime-boundary data and turn it into one
          go / no-go verdict — for the Tamil Nadu coast, in the view each stakeholder actually needs.
        </motion.p>
        <motion.div variants={heroItem} className="flex items-center gap-3">
          <button
            type="button"
            onClick={() =>
              personaSectionRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" })
            }
            className="rounded-sm bg-accent px-4 py-2.5 text-sm font-semibold text-abyss transition-colors hover:bg-accent/90"
          >
            Explore ORCA
          </button>
          <Link
            href="/login"
            className="rounded-sm border border-hairline px-4 py-2.5 text-sm text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink"
          >
            Sign in
          </Link>
        </motion.div>
      </motion.section>

      <section ref={personaSectionRef} className="flex flex-col gap-5 scroll-mt-8">
        <div className="text-center">
          <h2 className="text-lg font-semibold text-ink">One answer, rendered four ways</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Pick how you read ORCA — this sets the view, not the underlying data.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {PICKABLE.map((p, i) => (
            <motion.button
              key={p.id}
              type="button"
              onClick={() => choosePersona(p.id)}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.35, delay: reduce ? 0 : i * 0.06 }}
              whileHover={reduce ? {} : { y: -2 }}
              whileTap={{ scale: 0.98 }}
              className="rounded-md border border-hairline bg-shelf-1/70 p-4 text-left transition-colors hover:border-accent/60"
            >
              <p className="text-sm font-semibold text-ink">{p.label}</p>
              <p className="mt-1 text-xs text-ink-muted">{PERSONA_BLURB[p.id]}</p>
            </motion.button>
          ))}
        </div>
      </section>

      <section className="flex flex-col items-center gap-3 border-t border-hairline pt-10 text-center">
        <p className="text-xs font-medium text-ink-dim">Built with</p>
        <div className="flex flex-wrap justify-center gap-2">
          {TECH.map((t) => (
            <span key={t} className="rounded-sm border border-hairline px-2.5 py-1 text-xs text-ink-muted">
              {t}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
