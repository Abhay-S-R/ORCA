"use client";

// The instrument bezel (plan §4.2 — ten destinations plus one persistent
// control). Desktop gets a 60px icon rail rather than a 208px text sidebar:
// the map is the product, and 150px of chrome on every screen is 150px the
// chart does not get. Mobile gets a bottom tab bar, five primary plus
// overflow, because the fisherman surface is thumb-driven.
//
// Icons are chosen from the maritime vernacular where one exists — Ask is a
// radio because that is how you ask a question at sea.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Building2,
  Database,
  Eye,
  Fish,
  LineChart,
  Map as MapIcon,
  Navigation,
  Radio,
  ShieldAlert,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { NAV_ROUTES, visibilityFor } from "./persona/config";
import { usePersona } from "./persona/context";
import { API_BASE } from "./lib/apiBase";

// Thoothukudi, the pilot region's own reference position — the same default
// the API uses when no live fix is supplied. Live GPS is Phase 2.
const DEFAULT_POSITION = { lat: 8.8, lon: 78.14 };

type MrccContact = {
  primary: { name: string; phone: string; vhf_channel: string };
  nationwide_fallback: { name: string; phone: string; vhf_channel: string };
};

// Duplicated from the backend on purpose: this is the one number that has to
// be on screen when nothing else works, including the ORCA server.
const NATIONWIDE_MRCC = {
  name: "Indian Coast Guard MRCC",
  phone: "1554",
  vhf_channel: "16",
};

const NAV: Record<(typeof NAV_ROUTES)[number], { label: string; Icon: LucideIcon }> = {
  "/ask": { label: "Ask", Icon: Radio },
  "/safety": { label: "Safety", Icon: ShieldAlert },
  "/map": { label: "Chart", Icon: MapIcon },
  "/zones": { label: "Fishing zones", Icon: Fish },
  "/voyage": { label: "Voyage", Icon: Navigation },
  "/trends": { label: "Trends", Icon: LineChart },
  "/data": { label: "Data", Icon: Database },
  "/ops": { label: "District ops", Icon: Building2 },
  "/watches": { label: "Watches", Icon: Eye },
  "/reasoning": { label: "Reasoning", Icon: Workflow },
};

export function NavRail() {
  const pathname = usePathname();
  const { persona } = usePersona();

  // Nav visibility is a rendering concern only, never a capability gate
  // (§4.3) — a hidden item is simply not listed; the route still renders at
  // full depth on a direct visit, since Next's router never consults this.
  const visible = NAV_ROUTES.map((href) => ({ href, visibility: visibilityFor(href, persona) })).filter(
    (r) => r.visibility !== "hidden",
  );

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Primary"
        className="hidden w-15 shrink-0 flex-col items-center gap-1 border-r border-hairline bg-shelf-1/40 py-3 sm:flex"
      >
        {/* "/" is the public landing page, outside this rail entirely —
            inside the app, the mark goes back to Ask, the app's own home. */}
        <Link href="/ask" aria-label="ORCA home" className="mb-2 grid size-9 place-items-center">
          <OrcaMark />
        </Link>
        {visible.map(({ href, visibility }) => {
          const { label, Icon } = NAV[href];
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={label}
              className={`group relative grid size-10 place-items-center rounded-md transition-colors ${
                active ? "bg-shelf-3/70 text-accent" : "text-ink-dim hover:bg-shelf-2/60 hover:text-ink"
              } ${visibility === "secondary" && !active ? "opacity-55" : ""}`}
            >
              {/* Active state is carried by an accent rule AND the icon
                  colour AND aria-current — never by colour alone. */}
              {active && (
                <span aria-hidden="true" className="absolute -left-[13px] h-6 w-[2px] rounded-r bg-accent" />
              )}
              <Icon className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
              <span className="sr-only">{label}</span>
              <span className="pointer-events-none absolute left-full z-50 ml-2 hidden rounded-sm border border-hairline bg-shelf-2 px-2 py-1 text-xs whitespace-nowrap text-ink group-hover:block">
                {label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Mobile tab bar — five primary, the rest reachable from More. */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-hairline bg-shelf-1/95 backdrop-blur-md sm:hidden"
      >
        {visible.slice(0, 5).map(({ href }) => {
          const { label, Icon } = NAV[href];
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-1 py-2 text-[10px] ${
                active ? "text-accent" : "text-ink-dim"
              }`}
            >
              <Icon className="size-5" strokeWidth={1.75} aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}

// The mark: a depth sounding. Three descending strokes, which is what a
// sounding line looks like on a chart, and what the product actually does.
// Exported (rather than redrawn) so /landing can reuse it at hero size, with
// an opt-in `animated` pass that draws the three strokes in as an actual
// sounding — motion tied to what the mark already means, not decoration
// bolted on. Nav rail usage is unaffected (animated defaults off).
export function OrcaMark({ className = "size-6", animated = false }: { className?: string; animated?: boolean }) {
  const reduce = useReducedMotion();
  const draw = animated && !reduce;
  const Stroke = draw ? motion.path : "path";
  const drawProps = (delay: number) =>
    draw ? { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 0.5, delay, ease: "easeOut" as const } } : {};
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <Stroke d="M3 6h18" stroke="var(--color-hairline-strong)" strokeWidth="1.5" strokeLinecap="round" {...drawProps(0)} />
      <Stroke d="M5 12h14" stroke="var(--color-shoal)" strokeWidth="1.5" strokeLinecap="round" {...drawProps(0.15)} />
      <Stroke d="M8 18h8" stroke="var(--color-accent)" strokeWidth="1.5" strokeLinecap="round" {...drawProps(0.3)} />
    </svg>
  );
}

export function SosButton() {
  // Persistent on every screen, for every persona (§4.2) — never in a menu,
  // never dismissible. Sits above the mobile tab bar rather than on it.
  //
  // Exit criterion 5: MRCC contact on screen in under 2 seconds, with all
  // persona rendering bypassed. The dialog therefore opens on the tap, not
  // on the response — the request fills the numbers in (typically a few
  // milliseconds, since Agent 12 short-circuits the graph), and the
  // nationwide fallback below is what shows if the backend never answers.
  const dialog = useRef<HTMLDialogElement>(null);
  const [contact, setContact] = useState<MrccContact | null>(null);
  const [reachedBackend, setReachedBackend] = useState<boolean | null>(null);

  function trigger() {
    dialog.current?.showModal();
    setContact(null);
    setReachedBackend(null);

    const es = new EventSource(
      `${API_BASE}/query?distress=true&lat=${DEFAULT_POSITION.lat}&lon=${DEFAULT_POSITION.lon}`,
    );
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type !== "final_response") return;
      if (data.mrcc_contact) setContact(data.mrcc_contact);
      setReachedBackend(true);
      es.close();
    };
    es.onerror = () => {
      setReachedBackend(false);
      es.close();
    };
  }

  const primary = contact?.primary ?? NATIONWIDE_MRCC;

  return (
    <>
      <button
        type="button"
        onClick={trigger}
        aria-label="Send a distress alert"
        className="fixed right-4 bottom-18 z-50 grid size-14 place-items-center rounded-full bg-no-go text-sm font-bold tracking-wide text-abyss shadow-lg shadow-no-go/25 transition-transform hover:scale-105 active:scale-95 sm:right-6 sm:bottom-6"
      >
        SOS
      </button>

      {/* Native <dialog>: Escape-to-close, focus containment and inertness
          come from the platform rather than from a modal library. */}
      <dialog
        ref={dialog}
        aria-labelledby="sos-title"
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-no-go/40 bg-shelf-1 p-5 text-ink backdrop:bg-abyss/80"
      >
        <h2 id="sos-title" className="text-xl font-semibold tracking-tight text-no-go">
          Distress alert
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Call the Coast Guard now. Give your position and the number of people aboard.
        </p>

        <a
          href={`tel:${primary.phone.replace(/[^+\d]/g, "")}`}
          className="mt-4 flex items-center justify-between rounded-md border border-no-go/40 bg-no-go/10 px-4 py-3"
        >
          <span className="text-sm text-ink-muted">{primary.name}</span>
          <span data-readout className="text-lg font-semibold text-ink">
            {primary.phone}
          </span>
        </a>

        <dl className="mt-3 flex flex-col gap-1.5 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">Nationwide</dt>
            <dd data-readout className="text-ink">
              <a href={`tel:${NATIONWIDE_MRCC.phone}`}>{NATIONWIDE_MRCC.phone}</a>
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">VHF channel</dt>
            <dd data-readout className="text-ink">{primary.vhf_channel}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-muted">Position sent</dt>
            <dd data-readout className="text-ink">
              {DEFAULT_POSITION.lat.toFixed(3)}, {DEFAULT_POSITION.lon.toFixed(3)}
            </dd>
          </div>
        </dl>

        {/* Never claim a delivery that did not happen. */}
        <p className="mt-3 border-t border-hairline pt-3 text-xs text-ink-dim">
          {reachedBackend === false
            ? "ORCA could not reach its server, so nothing was logged. The numbers above are the nationwide Coast Guard contacts — call them directly."
            : "The handoff to DAT-SG is SIMULATED in this build: no alert has been transmitted. Calling is what reaches help."}
        </p>

        <form method="dialog" className="mt-4 flex justify-end">
          <button className="rounded-md border border-hairline px-3 py-1.5 text-sm text-ink-muted hover:border-hairline-strong hover:text-ink">
            Close
          </button>
        </form>
      </dialog>
    </>
  );
}
