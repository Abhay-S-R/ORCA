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
import { useRef, useState, useSyncExternalStore } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Bell,
  Building2,
  Check,
  Copy,
  Database,
  Eye,
  Fish,
  LineChart,
  Map as MapIcon,
  MapPin,
  Navigation,
  Phone,
  Radio,
  Sailboat,
  ShieldAlert,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { NAV_ROUTES, visibilityFor } from "./persona/config";
import { usePersona } from "./persona/context";
import { API_BASE } from "./lib/apiBase";
import { useAuth } from "./lib/auth";
import { useT } from "./i18n/useT";
import {
  resolveDistressContact,
} from "./lib/distressContacts";

// P-HP-1 — SOS routes dynamically based on proximity to home port.
// Within 30 km: directs to local port signal station / coastal police.
// Beyond 30 km: escalates to nationwide Coast Guard MRCC (1554).

// P3.12 (orca_final §14.4) — icons only; the label itself comes from
// useT() below, keyed as `nav.<route slug>` in app/i18n/<lang>.json (every
// slug here matches a real key in every one of the ten dictionaries).
const NAV: Record<(typeof NAV_ROUTES)[number], { label: string; Icon: LucideIcon }> = {
  "/ask": { label: "Ask", Icon: Radio },
  "/alerts": { label: "Alerts", Icon: Bell },
  "/map": { label: "Chart", Icon: MapIcon },
  "/zones": { label: "Fishing zones", Icon: Fish },
  "/voyage": { label: "Voyage", Icon: Navigation },
  "/trends": { label: "Trends", Icon: LineChart },
  "/data": { label: "Data", Icon: Database },
  "/ops": { label: "District ops", Icon: Building2 },
  "/watches": { label: "Watches", Icon: Eye },
  "/reasoning": { label: "Reasoning", Icon: Workflow },
};

function navKey(href: (typeof NAV_ROUTES)[number]): string {
  return `nav.${href.slice(1)}`;
}

const NEVER_CHANGES = () => () => {};

export function NavRail() {
  const pathname = usePathname();
  const { persona } = usePersona();
  const t = useT();

  // Hydration-safe: render with "unresolved" on both the server pass and the
  // first client render so the HTML matches, then swap in the real persona
  // once the component has mounted (localStorage has been read by then).
  // useSyncExternalStore rather than setState-in-an-effect: it is the same
  // swap, but the server/client snapshot split is the hook's actual job, so
  // there is no cascading render for `react-hooks/set-state-in-effect` to
  // object to. The store never changes, hence the no-op subscribe.
  const mounted = useSyncExternalStore(NEVER_CHANGES, () => true, () => false);
  const effectivePersona = mounted ? persona : "unresolved";

  // Nav visibility is a rendering concern only, never a capability gate
  // (§4.3) — a hidden item is simply not listed; the route still renders at
  // full depth on a direct visit, since Next's router never consults this.
  const visible = NAV_ROUTES.map((href) => ({ href, visibility: visibilityFor(href, effectivePersona) })).filter(
    (r) => r.visibility !== "hidden",
  );

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Primary"
        className="hidden w-16 shrink-0 flex-col items-center gap-1.5 border-r border-hairline bg-shelf-1/80 py-4 sm:flex backdrop-blur-md shadow-lg z-40"
      >
        {/* "/" is the public landing page, outside this rail entirely —
            inside the app, the mark goes back to Ask, the app's own home. */}
        <Link href="/ask" aria-label="Sagar Sarathi home" className="group mb-3 relative grid place-items-center transition-transform hover:scale-105">
          <OrcaMark className="size-9" />
          <span className="sr-only">Sagar Sarathi</span>
        </Link>
        {visible.map(({ href, visibility }) => {
          const { Icon } = NAV[href];
          const label = t(navKey(href));
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={label}
              className={`group relative grid size-10 place-items-center rounded-lg border transition-all ${active
                ? "border-ocean-cyan/60 bg-shelf-3/90 text-ocean-cyan shadow-md shadow-ocean-cyan/15"
                : "border-transparent text-ink-dim hover:border-hairline hover:bg-shelf-2/80 hover:text-ink"
                } ${visibility === "secondary" && !active ? "opacity-55" : ""}`}
            >
              {/* Active indicator bar */}
              {active && (
                <span
                  aria-hidden="true"
                  className="absolute -left-[17px] h-6 w-1 rounded-r bg-ocean-cyan"
                />
              )}
              <Icon className="size-[18px] transition-transform group-hover:scale-105" strokeWidth={active ? 2.2 : 1.75} aria-hidden="true" />
              <span className="sr-only">{label}</span>
              <span className="pointer-events-none absolute left-full z-50 ml-3 hidden rounded border border-hairline-strong bg-shelf-1/95 px-2.5 py-1 text-xs font-medium tracking-wide whitespace-nowrap text-ink shadow-xl backdrop-blur-md group-hover:block">
                {label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Mobile tab bar — five primary, the rest reachable from More. */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-hairline bg-shelf-1/95 backdrop-blur-xl sm:hidden shadow-2xl"
      >
        {visible.slice(0, 5).map(({ href }) => {
          const { Icon } = NAV[href];
          const label = t(navKey(href));
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] font-medium tracking-wide transition-colors ${active ? "text-ocean-cyan border-t-2 border-ocean-cyan -mt-px bg-shelf-2/40" : "text-ink-dim hover:text-ink"
                }`}
            >
              <Icon className="size-5" strokeWidth={active ? 2.2 : 1.75} aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}

// The mark: a vessel under sail, in a chart-compass roundel — what the
// product is actually about (a boat's own bridge console), not an abstract
// glyph. Exported (rather than redrawn) so /landing and /login reuse it at
// hero size. `animated` gives it a small settle-in on mount; off by default
// so the nav rail's icon never re-plays it on every route change.
export function OrcaMark({ className = "size-6", animated = false }: { className?: string; animated?: boolean }) {
  const reduce = useReducedMotion();
  const play = animated && !reduce;
  return (
    <motion.div
      className={`relative grid place-items-center rounded-full border-[1.5px] border-current ${className}`}
      style={{ color: "var(--color-ink)" }}
      initial={play ? { opacity: 0, scale: 0.85 } : false}
      animate={play ? { opacity: 1, scale: 1 } : undefined}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Sailboat className="size-[62%]" style={{ color: "var(--color-ocean-cyan)" }} strokeWidth={2} aria-hidden="true" />
    </motion.div>
  );
}

export function SosButton() {
  // Persistent on every screen, for every persona (§4.2) — never in a menu,
  // never dismissible. Sits above the mobile tab bar rather than on it.
  //
  // Exit criterion 5: Contact on screen in under 2 seconds.
  // 30 km Radius Rule:
  // - <= 30 km from registered home port: routes to Local Port Emergency Control
  // - > 30 km from registered home port (or deep sea): routes to National MRCC (1554)
  //
  // Device handling:
  // - Mobile: `tel:` anchor triggers device dialpad with single tap
  // - Web / Desktop: 1-click clipboard copy for phone & coordinates + VHF instructions
  const dialog = useRef<HTMLDialogElement>(null);
  const [sentPosition, setSentPosition] = useState<{ lat: number; lon: number } | null>(null);
  const [copiedPhone, setCopiedPhone] = useState(false);
  const [copiedCoords, setCopiedCoords] = useState(false);
  const auth = useAuth();
  const pathname = usePathname();
  const isMapPage = pathname === "/map";

  const homePort =
    auth.status === "signed_in" && auth.profile?.home_port
      ? auth.profile.home_port
      : null;

  const homePortName =
    auth.status === "signed_in" && auth.profile?.home_port_name
      ? auth.profile.home_port_name
      : null;

  // Resolve 30 km boundary against registered home port
  const resolution = resolveDistressContact(
    sentPosition,
    homePort ? { lat: homePort.lat, lon: homePort.lon } : null,
    homePortName,
  );

  function copyText(text: string, type: "phone" | "coords") {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      if (type === "phone") {
        setCopiedPhone(true);
        setTimeout(() => setCopiedPhone(false), 2000);
      } else {
        setCopiedCoords(true);
        setTimeout(() => setCopiedCoords(false), 2000);
      }
    }
  }

  function trigger() {
    dialog.current?.showModal();
    setSentPosition(null);
    setCopiedPhone(false);
    setCopiedCoords(false);

    function fireRequest(pos: { lat: number; lon: number } | null) {
      setSentPosition(pos);
      const posParam = pos ? `&lat=${pos.lat}&lon=${pos.lon}` : "";
      const es = new EventSource(`${API_BASE}/query?distress=true${posParam}`);
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        if (data.type !== "final_response") return;
        es.close();
      };
      es.onerror = () => {
        es.close();
      };
    }

    const portCoord = homePort ? { lat: homePort.lat, lon: homePort.lon } : null;

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (geoPos) => {
          fireRequest({ lat: geoPos.coords.latitude, lon: geoPos.coords.longitude });
        },
        () => {
          fireRequest(portCoord);
        },
        { timeout: 4000, maximumAge: 60_000 },
      );
    } else {
      fireRequest(portCoord);
    }
  }

  const primary = resolution.primary;
  const cleanPhone = primary.phone.replace(/[^+\d]/g, "");
  const formattedCoords = sentPosition
    ? `${sentPosition.lat.toFixed(4)}° N, ${sentPosition.lon.toFixed(4)}° E`
    : null;

  return (
    <>
      <button
        type="button"
        onClick={trigger}
        aria-label="Send a distress alert"
        className={`group fixed z-50 flex size-14 items-center justify-center rounded-full border-2 border-no-go/60 bg-no-go text-sm font-black tracking-widest text-on-accent shadow-lg transition-all hover:scale-105 active:scale-95 ${
          isMapPage
            ? "left-16 bottom-12 sm:left-16.5 sm:bottom-19.5"
            : "right-4 bottom-18 sm:right-2.5 sm:bottom-1.5"
        }`}
      >
        <span className="absolute inset-0 -z-10 rounded-full bg-no-go/30 animate-ping opacity-75 pointer-events-none" />
        <span className="relative z-10 font-mono text-base font-black">SOS</span>
      </button>

      {/* Native <dialog>: Escape-to-close, focus containment */}
      <dialog
        ref={dialog}
        aria-labelledby="sos-title"
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-no-go/50 bg-shelf-1 p-5 text-ink shadow-2xl backdrop:bg-abyss/85"
      >
        <div className="flex items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-no-go/15 text-no-go border border-no-go/30">
            <ShieldAlert className="size-5" />
          </div>
          <h2 id="sos-title" className="text-lg font-bold tracking-tight text-no-go">
            Maritime Distress Alert
          </h2>
        </div>

        {/* Primary Contact Card */}
        <div className="mt-4 rounded-lg border border-no-go/40 bg-no-go/10 p-4">
          <div className="text-sm font-bold text-ink">{primary.name}</div>
          <div className="text-xs text-ink-muted">{primary.stationName}</div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-no-go/20">
            <div data-readout className="font-mono text-2xl font-black tracking-wide text-ink">
              {primary.phone}
            </div>
            <div className="flex items-center gap-2">
              <a
                href={`tel:${cleanPhone}`}
                className="flex items-center gap-1.5 rounded-md bg-no-go px-3.5 py-2 text-xs font-bold text-white hover:brightness-110 active:scale-95 transition-all"
              >
                <Phone className="size-3.5" />
                Call
              </a>
              <button
                type="button"
                onClick={() => copyText(primary.phone, "phone")}
                className="flex items-center gap-1.5 rounded-md border border-hairline bg-shelf-2 px-3 py-2 text-xs font-medium text-ink hover:border-hairline-strong active:scale-95 transition-all"
              >
                {copiedPhone ? (
                  <><Check className="size-3.5 text-go" /><span className="text-go">Copied</span></>
                ) : (
                  <><Copy className="size-3.5 text-ink-dim" />Copy</>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* GPS + VHF row */}
        <div className="mt-3 space-y-2 text-xs">
          {formattedCoords && (
            <div className="flex items-center justify-between rounded-md border border-hairline bg-shelf-2/60 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <MapPin className="size-3.5 text-ocean-cyan shrink-0" />
                <span className="font-mono font-semibold text-ink">{formattedCoords}</span>
              </div>
              <button
                type="button"
                onClick={() => copyText(formattedCoords, "coords")}
                className="flex items-center gap-1 rounded border border-hairline bg-shelf-1 px-2 py-1 text-[11px] font-medium text-ink hover:border-hairline-strong"
              >
                {copiedCoords ? (
                  <><Check className="size-3 text-go" /><span className="text-go">Copied</span></>
                ) : (
                  <><Copy className="size-3 text-ink-dim" />Copy GPS</>
                )}
              </button>
            </div>
          )}
          <div className="flex items-center gap-2 rounded-md border border-hairline bg-shelf-2/60 px-3 py-2.5">
            <Radio className="size-3.5 text-amber-500 shrink-0" />
            <span className="font-mono font-semibold text-ink">VHF Channel 16</span>
            <span className="text-ink-dim">— 156.8 MHz</span>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <p className="text-[11px] text-ink-dim">
            Beyond 80 km from home port, national helpline <a href="tel:1554" className="font-mono font-semibold text-ink-muted hover:text-ocean-cyan">1554</a> is used.
          </p>
          <form method="dialog">
            <button className="rounded-lg border border-hairline bg-shelf-2 px-4 py-1.5 text-xs font-semibold text-ink hover:border-hairline-strong active:scale-95 transition-all">
              Close
            </button>
          </form>
        </div>
      </dialog>
    </>
  );
}


