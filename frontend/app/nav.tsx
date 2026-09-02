"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ROUTES, visibilityFor } from "./persona/config";
import { usePersona } from "./persona/context";
import { PersonaSelector } from "./persona/PersonaSelector";

// Plan §4.2 — ten destinations plus one persistent control. Route list
// intentionally matches §4.2's table order; visibility per persona comes
// from the declarative matrix (parent plan §4.3), not a conditional here.
const NAV_LABELS: Record<(typeof NAV_ROUTES)[number], string> = {
  "/": "Ask",
  "/safety": "Safety",
  "/map": "Map",
  "/zones": "Fishing Zones",
  "/voyage": "Voyage",
  "/trends": "Trends",
  "/data": "Data",
  "/ops": "District Ops",
  "/watches": "Watches",
  "/reasoning": "Reasoning",
};

export function NavRail() {
  const pathname = usePathname();
  const { persona } = usePersona();

  return (
    <nav aria-label="Primary" className="w-52 shrink-0 border-r border-black/10 p-4">
      <PersonaSelector />
      <ul className="flex flex-col gap-1">
        {NAV_ROUTES.map((href) => {
          // Nav visibility is a rendering concern only, never a capability
          // gate (parent plan §4.3) — a "hidden" item is simply not listed
          // here; the route at `href` still renders at full depth on a
          // direct visit, since Next's router never consults this matrix.
          const visibility = visibilityFor(href, persona);
          if (visibility === "hidden") return null;

          const active = pathname === href;
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`block rounded px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                  active ? "bg-black/10 font-medium" : "hover:bg-black/5"
                } ${visibility === "secondary" ? "opacity-60" : ""}`}
              >
                {NAV_LABELS[href]}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function SosButton() {
  // Persistent on every screen, every persona (§4.2) — never in a menu.
  return (
    <button
      type="button"
      aria-label="SOS — report a distress emergency"
      className="fixed bottom-6 right-6 z-50 rounded-full bg-red-600 px-5 py-3 text-sm font-bold text-white shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
    >
      SOS
    </button>
  );
}
