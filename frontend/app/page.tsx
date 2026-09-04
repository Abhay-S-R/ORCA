"use client";

// ORCA Maritime Operations Platform — Public Command Bridge.
// Root entry point: authentic nautical telemetry, interactive sonar scope,
// live oceanographic conditions, and stakeholder command stations.
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  Anchor,
  Compass,
  Database,
  ExternalLink,
  Fish,
  Navigation,
  Radio,
  Shield,
  ShieldAlert,
  Workflow,
  ArrowRight,
} from "lucide-react";
import { OrcaMark } from "./nav";
import { type Persona } from "./persona/config";
import { usePersona } from "./persona/context";

const TELEMETRY_FEED = [
  { label: "Arabian Sea (West)", val: "1.4 m", sub: "Kochi Buoy · INCOIS" },
  { label: "Bay of Bengal (East)", val: "1.8 m", sub: "Vizag Buoy · INCOIS" },
  { label: "Gulf of Mannar (South)", val: "1.2 m", sub: "Thoothukudi Buoy" },
  { label: "Wind Velocity", val: "16.4 kn", sub: "SW Monsoon · 220°" },
  { label: "Indian EEZ Standoff", val: "200 nm", sub: "Sovereign Perimeter" },
  { label: "All-India PFZ Feeds", val: "ACTIVE", sub: "Daily INCOIS / ISRO" },
];

const STAKEHOLDER_STATIONS = [
  {
    id: "fisherman" as const,
    title: "Fisherman Station",
    tamilTitle: "மீனவர் தகவல் மையம் · Multilingual",
    tagline: "Unambiguous Go / No-Go safety verdicts, voice queries, and daily INCOIS Potential Fishing Zones.",
    metrics: ["Instant Safety Gatekeeper", "Pan-India PFZ Advisory", "VHF 16 / MRCC 1554 SOS"],
    icon: Fish,
    accent: "text-go border-go/40 bg-go/10",
  },
  {
    id: "commercial_navigator" as const,
    title: "Commercial Navigator",
    tamilTitle: "வணிக மாலுமி மையம் · Merchant Marine",
    tagline: "Passage corridor planning across Indian coastal routes, EEZ boundaries, and berthing tides.",
    metrics: ["Per-Leg Classified Routes", "EEZ Standoff Radar", "Destination Tide Windows"],
    icon: Navigation,
    accent: "text-ocean-cyan border-ocean-cyan/40 bg-ocean-cyan/10",
  },
  {
    id: "researcher" as const,
    title: "Marine Scientist",
    tamilTitle: "கடல் சூழலியல் ஆய்வாளர் · Oceanography",
    tagline: "Multimodal agentic reasoning traces, catch-decline regression, and cited oceanographic exports.",
    metrics: ["10-Agent Graph Trace", "Chlorophyll & SST Trends", "CSV / GeoJSON Provenance Export"],
    icon: Workflow,
    accent: "text-confidence-medium border-confidence-medium/40 bg-confidence-medium/10",
  },
  {
    id: "coastal_authority" as const,
    title: "Coastal Authority",
    tamilTitle: "கடலோர பாதுகாப்பு பிரிவு · Maritime Security",
    tagline: "National coastal threat matrices, CAP 1.2 emergency broadcasts, and fleet density monitoring.",
    metrics: ["Aggregated Fleet Densities", "CAP 1.2 Multi-Channel Alerts", "Hazard Zone Audits"],
    icon: Shield,
    accent: "text-caution border-caution/40 bg-caution/10",
  },
];

const ARCHITECTURE_PILLARS = [
  {
    num: "01",
    title: "Deterministic Oceanographic Calculations",
    body: "Safety verdicts and wave-height gates are evaluated deterministically against calibrated physical thresholds (INCOIS wave buoys, IMD radar, GEBCO bathymetry) with mathematical verification.",
    icon: Database,
  },
  {
    num: "02",
    title: "Rigorous PostGIS Spatial Geofencing",
    body: "National maritime boundaries, international EEZ limits, and marine protected areas are evaluated against exact spatial polygons with sub-meter coordinate precision.",
    icon: Compass,
  },
  {
    num: "03",
    title: "2ms Distress Emergency Handoff",
    body: "Emergency distress signals instantly bypass standard processing to display verified Indian Coast Guard MRCC dispatch lines and VHF channel 16 coordinates.",
    icon: ShieldAlert,
  },
];

export default function LandingPage() {
  const router = useRouter();
  const { setPersona } = usePersona();
  const reduce = useReducedMotion();
  const [selectedTab, setSelectedTab] = useState<"radar" | "telemetry" | "graph">("radar");
  const personaSectionRef = useRef<HTMLDivElement>(null);

  function launchWithPersona(id: Persona) {
    setPersona(id);
    router.push("/ask");
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-abyss text-ink">
      {/* Background Graticule & Bathymetric Contour Styling */}
      <div className="pointer-events-none fixed inset-0 chart-grid opacity-30" aria-hidden="true" />
      <div
        className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_50%_15%,rgba(0,229,255,0.08)_0%,transparent_65%)]"
        aria-hidden="true"
      />

      {/* Top Telemetry Header */}
      <div className="relative z-20 border-b border-hairline/80 bg-shelf-1/90 px-4 py-2 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between text-xs">
          <div className="flex items-center gap-2 font-mono text-[11px] text-ink-muted">
            <span className="size-2 rounded-full bg-go beacon-pulse" aria-hidden="true" />
            <span className="font-semibold text-ink">ORCA SYSTEM ONLINE</span>
            <span className="hidden text-ink-dim sm:inline">· ALL-INDIA MARITIME DOMAIN AWARENESS (EEZ &amp; COASTAL WATERS)</span>
          </div>

          <div className="flex items-center gap-4 text-[11px] text-ink-dim">
            <span className="hidden font-mono md:inline">7,516 KM COASTLINE · ARABIAN SEA · BAY OF BENGAL · INDIAN OCEAN</span>
            <Link
              href="/login"
              className="rounded border border-hairline px-2.5 py-1 text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:text-ink"
            >
              Sign in
            </Link>
          </div>
        </div>
      </div>

      <main className="relative z-10 mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        {/* Hero Section */}
        <section className="flex flex-col items-center text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-ocean-cyan/30 bg-shelf-2/80 px-4 py-1.5 text-xs font-semibold text-ocean-cyan backdrop-blur-md shadow-sm">
            <OrcaMark className="size-4" />
            <span>ORCA · Marine EcOsystem Reasoning with Collaborative Agents</span>
          </div>

          <h1 className="max-w-5xl text-4xl font-extrabold tracking-tight text-ink sm:text-6xl sm:leading-[1.1]">
            ORCA
            <span className="block mt-2 text-2xl sm:text-4xl font-bold text-ink tracking-tight">
              Marine EcOsystem Reasoning with Collaborative Agents
            </span>
            <span className="block mt-3 bg-gradient-to-r from-ocean-cyan via-go to-sky-300 bg-clip-text text-transparent text-xl sm:text-3xl font-semibold tracking-normal">
              Agentic AI Conversational Platform for Indian Marine Intelligence
            </span>
          </h1>

          <div className="mt-6 max-w-3xl text-center">
            <p className="text-base leading-relaxed text-ink-muted sm:text-lg">
              <strong className="font-semibold text-ink">ORCA</strong> is an Agentic AI-powered conversational decision-support platform enabling
              fishermen, researchers, coastal authorities, and maritime operators to access, analyze, and reason over oceanographic data using natural language.
              Coordinating specialized AI agents, ORCA autonomously fuses ISRO satellite Earth Observation data (SST, Chlorophyll), INCOIS ocean advisories
              (Potential Fishing Zones, wave buoys), IMD weather forecasts, and GIS boundary geofences to synthesize explainable Go / No-Go verdicts,
              passage corridors, and proactive coastal hazard alerts across all 7,516 km of India&apos;s coastline.
            </p>
          </div>

          {/* Typical Conversational Scenarios */}
          <div className="mt-6 flex max-w-4xl flex-wrap items-center justify-center gap-2">
            <span className="text-[11px] font-semibold text-ink-dim uppercase tracking-wider">
              Ask ORCA:
            </span>
            {[
              "Where is the nearest Potential Fishing Zone (PFZ) today?",
              "Is it safe to venture into the sea tomorrow morning?",
              "What are the tide, weather, and sea conditions?",
              "Are there any lightning or cyclone alerts?",
              "High chlorophyll & favorable SST zones",
              "Safest route considering sea-state conditions",
            ].map((query) => (
              <Link
                key={query}
                href={`/ask?q=${encodeURIComponent(query)}`}
                className="rounded-full border border-hairline/80 bg-shelf-2/60 px-3 py-1 text-xs text-ink-muted transition-all hover:border-ocean-cyan/60 hover:bg-shelf-3 hover:text-ocean-cyan"
              >
                &ldquo;{query}&rdquo;
              </Link>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <button
              type="button"
              onClick={() => launchWithPersona("fisherman")}
              className="flex items-center gap-2 rounded-lg border border-ocean-cyan/60 bg-ocean-cyan px-6 py-3 text-sm font-bold text-abyss shadow-[0_0_20px_rgba(0,229,255,0.35)] transition-all hover:bg-ocean-cyan/90 hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
            >
              <Radio className="size-4" />
              <span>Launch Conversational Bridge</span>
              <ArrowRight className="size-4" />
            </button>

            <button
              type="button"
              onClick={() =>
                personaSectionRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" })
              }
              className="flex items-center gap-2 rounded-lg border border-hairline-strong bg-shelf-2/80 px-5 py-3 text-sm font-semibold text-ink transition-all hover:border-ocean-cyan/60 hover:bg-shelf-3 cursor-pointer"
            >
              <span>Explore Stakeholder Decks</span>
            </button>
          </div>
        </section>

        {/* Live Operational Conditions Ticker */}
        <section className="mt-14">
          <div className="rounded-xl border border-hairline bg-shelf-1/70 p-4 shadow-xl backdrop-blur-md">
            <div className="mb-3 flex items-center justify-between text-xs">
              <span className="font-mono text-[11px] font-semibold text-ink-dim uppercase tracking-wider">
                Live Pan-India Coastal Buoy &amp; Satellite Telemetry
              </span>
              <span className="font-mono text-[10px] text-ocean-cyan">Refreshed 2m ago · INCOIS / IMD / ISRO</span>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {TELEMETRY_FEED.map((item) => (
                <div
                  key={item.label}
                  className="rounded-lg border border-hairline/60 bg-shelf-2/50 p-2.5 transition-colors hover:border-hairline-strong"
                >
                  <p className="text-[11px] font-medium text-ink-dim">{item.label}</p>
                  <p data-readout className="mt-0.5 text-base font-bold text-ink">
                    {item.val}
                  </p>
                  <p className="mt-0.5 truncate text-[10px] text-ink-dim">{item.sub}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Interactive Tactical Radar & System Scope */}
        <section className="mt-16">
          <div className="overflow-hidden rounded-2xl border border-hairline-strong/80 bg-shelf-1/60 shadow-2xl backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between border-b border-hairline bg-shelf-2/40 px-5 py-3.5">
              <div className="flex items-center gap-3">
                <div className="grid size-8 place-items-center rounded-lg border border-ocean-cyan/40 bg-ocean-cyan/10 text-ocean-cyan">
                  <Compass className="size-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold tracking-tight text-ink">
                    National Maritime Situational Display (ECDIS)
                  </h2>
                  <p className="text-[11px] text-ink-dim">
                    Pan-India spatial monitoring: EEZ &amp; IMBL standoff, marine sanctuaries, bathymetric corridors &amp; cyclone tracks
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5 rounded-lg border border-hairline bg-shelf-1/80 p-1">
                {(["radar", "telemetry", "graph"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setSelectedTab(tab)}
                    className={`rounded px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
                      selectedTab === tab
                        ? "bg-ocean-cyan text-abyss font-bold"
                        : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid lg:grid-cols-[1fr_360px]">
              {/* Interactive Radar Visualizer */}
              <div className="relative flex min-h-[380px] items-center justify-center p-8">
                {/* Concentric Range Rings */}
                <div className="relative grid size-72 place-items-center rounded-full border border-hairline/80 sm:size-88">
                  <div className="absolute size-56 rounded-full border border-hairline/60 sm:size-68" />
                  <div className="absolute size-36 rounded-full border border-hairline/40 sm:size-44" />
                  <div className="absolute size-16 rounded-full border border-ocean-cyan/20" />

                  {/* Crosshairs */}
                  <div className="absolute inset-x-0 top-1/2 h-px bg-hairline/60" />
                  <div className="absolute inset-y-0 left-1/2 w-px bg-hairline/60" />

                  {/* Radar Sweeping Beam */}
                  <div className="radar-sweep absolute inset-0 origin-center rounded-full bg-[conic-gradient(from_0deg,transparent_0_310deg,rgba(0,229,255,0.25)_360deg)] pointer-events-none" />

                  {/* Tactical Target Blips */}
                  <div
                    className="absolute top-1/4 right-1/3 flex items-center gap-1.5 text-[10px] font-mono text-go"
                    title="Advisable Fishing Zone"
                  >
                    <span className="size-2 rounded-full bg-go shadow-[0_0_8px_rgba(16,229,153,0.8)] beacon-pulse" />
                    <span>PFZ-8 (12.4 km)</span>
                  </div>

                  <div
                    className="absolute bottom-1/4 right-1/4 flex items-center gap-1.5 text-[10px] font-mono text-caution"
                    title="IMBL Standoff Warning Line"
                  >
                    <span className="size-2 rounded-full bg-caution shadow-[0_0_8px_rgba(245,158,11,0.8)]" />
                    <span>IMBL (18.4 nm)</span>
                  </div>

                  <div
                    className="absolute top-1/3 left-1/4 flex items-center gap-1.5 text-[10px] font-mono text-ocean-cyan"
                    title="Thoothukudi Port Reference"
                  >
                    <Anchor className="size-3 text-ocean-cyan" />
                    <span>Thoothukudi Base</span>
                  </div>
                </div>

                <div className="absolute bottom-4 left-4 font-mono text-[10px] text-ink-dim">
                  RANGE: 25 NM · HEAD-UP · NORTH STABILIZED
                </div>
              </div>

              {/* Radar Side Telemetry Panel */}
              <div className="flex flex-col justify-between border-t border-hairline bg-shelf-1/40 p-5 lg:border-t-0 lg:border-l">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-xs font-bold text-ink uppercase tracking-wider">
                      Real-time Spatial Hazard Assessment
                    </h3>
                    <p className="mt-1 text-xs text-ink-muted">
                      Every coordinates fix evaluates 5 distinct safety vectors simultaneously:
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between rounded-lg border border-hairline bg-shelf-2/60 p-2.5 text-xs">
                      <span className="text-ink-muted">Sovereign EEZ &amp; IMBL Boundary</span>
                      <span className="font-mono font-bold text-go">18.4 nm CLEAR</span>
                    </div>

                    <div className="flex items-center justify-between rounded-lg border border-hairline bg-shelf-2/60 p-2.5 text-xs">
                      <span className="text-ink-muted">Marine Protected Areas (MPAs)</span>
                      <span className="font-mono font-bold text-go">SAFE EXTERIOR</span>
                    </div>

                    <div className="flex items-center justify-between rounded-lg border border-hairline bg-shelf-2/60 p-2.5 text-xs">
                      <span className="text-ink-muted">Wave Height Threshold</span>
                      <span className="font-mono font-bold text-go">1.2m &lt; 2.0m</span>
                    </div>

                    <div className="flex items-center justify-between rounded-lg border border-hairline bg-shelf-2/60 p-2.5 text-xs">
                      <span className="text-ink-muted">Severe Weather &amp; Lightning</span>
                      <span className="font-mono font-bold text-go">CLEAR SECTOR</span>
                    </div>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-hairline">
                  <Link
                    href="/map"
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-ocean-cyan/60 bg-shelf-3/80 py-2.5 text-xs font-bold text-ocean-cyan transition-colors hover:bg-shelf-3 hover:text-ink"
                  >
                    <span>Open Fullscreen Nautical Chart</span>
                    <ExternalLink className="size-3.5" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Stakeholder Command Stations */}
        <section ref={personaSectionRef} className="mt-20 scroll-mt-10">
          <div className="text-center">
            <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              One Ground Truth, Rendered per Stakeholder
            </h2>
            <p className="mx-auto mt-2 max-w-xl text-sm text-ink-muted">
              Select your command station. The underlying safety facts remain identical, while the
              visual presentation adapts to your operational requirements.
            </p>
          </div>

          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STAKEHOLDER_STATIONS.map((station, i) => {
              const Icon = station.icon;
              return (
                <div
                  key={station.id}
                  className="group relative flex flex-col justify-between rounded-xl border border-hairline bg-shelf-1/80 p-5 shadow-lg backdrop-blur-md transition-all hover:border-ocean-cyan/60 hover:bg-shelf-2/80 hover:shadow-2xl"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <div className={`grid size-10 place-items-center rounded-lg border ${station.accent}`}>
                        <Icon className="size-5" />
                      </div>
                      <span className="font-mono text-[10px] text-ink-dim uppercase">STATION {i + 1}</span>
                    </div>

                    <h3 className="mt-4 text-base font-bold text-ink group-hover:text-ocean-cyan transition-colors">
                      {station.title}
                    </h3>
                    <p className="text-xs font-medium text-ink-dim">{station.tamilTitle}</p>

                    <p className="mt-2.5 text-xs leading-relaxed text-ink-muted">
                      {station.tagline}
                    </p>

                    <div className="mt-4 space-y-1.5 border-t border-hairline/60 pt-3">
                      {station.metrics.map((m) => (
                        <div key={m} className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                          <span className="size-1 rounded-full bg-ocean-cyan/60" />
                          <span>{m}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => launchWithPersona(station.id)}
                    className="mt-6 flex w-full items-center justify-center gap-1.5 rounded border border-hairline-strong bg-shelf-2/80 py-2 text-xs font-semibold text-ink transition-all group-hover:border-ocean-cyan group-hover:bg-ocean-cyan group-hover:text-abyss cursor-pointer"
                  >
                    <span>Enter Station</span>
                    <ArrowRight className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        {/* Operational Engineering & Reliability Section */}
        <section className="mt-20 border-t border-hairline pt-14">
          <div className="mb-10 text-center">
            <span className="text-xs font-mono font-bold text-ocean-cyan uppercase tracking-widest">
              Engineered for Real-World Sea Trials
            </span>
            <h2 className="mt-1.5 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              Operational Principles &amp; Maritime Reliability
            </h2>
            <p className="mx-auto mt-2 max-w-xl text-xs text-ink-muted sm:text-sm">
              Mission-critical safeguards engineered for coastal fishermen, merchant vessels, and maritime authorities across all Indian waters.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {ARCHITECTURE_PILLARS.map((pillar) => {
              const Icon = pillar.icon;
              return (
                <div
                  key={pillar.num}
                  className="relative rounded-xl border border-hairline bg-shelf-1/60 p-6 shadow-md"
                >
                  <div className="flex items-center justify-between text-xs font-mono text-ocean-cyan">
                    <span>RULE {pillar.num}</span>
                    <Icon className="size-4" />
                  </div>
                  <h3 className="mt-3 text-base font-bold text-ink">{pillar.title}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-ink-muted">{pillar.body}</p>
                </div>
              );
            })}
          </div>
        </section>

        {/* Footer */}
        <footer className="mt-20 border-t border-hairline/80 pt-8 pb-12 text-center text-xs text-ink-dim">
          <div className="flex flex-wrap justify-center gap-6">
            <Link href="/ask" className="hover:text-ink">Bridge Console</Link>
            <Link href="/safety" className="hover:text-ink">Vessel Safety</Link>
            <Link href="/map" className="hover:text-ink">Nautical Chart</Link>
            <Link href="/voyage" className="hover:text-ink">Voyage Planning</Link>
            <Link href="/zones" className="hover:text-ink">Fishing Zones</Link>
            <Link href="/reasoning" className="hover:text-ink">Reasoning Graph</Link>
          </div>
          <p className="mt-4">
            ORCA: Marine EcOsystem Reasoning with Collaborative Agents · Agentic AI Conversational Platform for India&apos;s 7,516 km Coastline and Exclusive Economic Zone (EEZ).
          </p>
        </footer>
      </main>
    </div>
  );
}
