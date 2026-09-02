"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Plan §4.2 — ten destinations plus one persistent control. Left rail here;
// dead links are fine for Phase 0 (exit criterion), content lands per-slice
// through Phase 1-3. Route list intentionally matches §4.2's table order.
const NAV_ITEMS = [
  { href: "/", label: "Ask" },
  { href: "/safety", label: "Safety" },
  { href: "/map", label: "Map" },
  { href: "/zones", label: "Fishing Zones" },
  { href: "/voyage", label: "Voyage" },
  { href: "/trends", label: "Trends" },
  { href: "/data", label: "Data" },
  { href: "/ops", label: "District Ops" },
  { href: "/watches", label: "Watches" },
  { href: "/reasoning", label: "Reasoning" },
];

export function NavRail() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="w-52 shrink-0 border-r border-black/10 p-4">
      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                  active ? "bg-black/10 font-medium" : "hover:bg-black/5"
                }`}
              >
                {item.label}
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
