"use client";

// The one app-wide sign-in / account control, in the status bar next to the
// persona selector. Before it, signing in or out was only possible from
// inside /watches.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Eye, LogIn, LogOut } from "lucide-react";
import { displayNameOf, signOut, useAuth } from "../lib/auth";
import { PersonaSelector } from "../persona/PersonaSelector";

function initials(name: string): string {
  const parts = name.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function AccountMenu() {
  const auth = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Same footprint while loading, so the status bar doesn't jump on hydration.
  if (auth.status === "loading") return <span className="inline-block h-6 w-6" aria-hidden="true" />;

  if (auth.status === "signed_out") {
    if (pathname === "/login") return null;
    return (
      <Link
        href={`/login?next=${encodeURIComponent(pathname)}`}
        className="inline-flex items-center gap-1.5 rounded border border-hairline bg-shelf-2/80 px-2 py-1 text-[11px] font-medium tracking-wide text-ink shadow-sm transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/80"
      >
        <LogIn className="size-3 text-ocean-cyan" aria-hidden="true" />
        <span className="hidden sm:inline">Sign in</span>
      </Link>
    );
  }

  const name = displayNameOf(auth.profile);
  const identifier = auth.profile?.identifier && auth.profile.identifier !== name ? auth.profile.identifier : null;

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 rounded-lg border border-hairline/80 bg-shelf-2/80 p-1 text-[11px] sm:pr-2 font-medium tracking-wide text-ink shadow-sm transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/90 focus:outline-none"
      >
        <span className="grid size-5.5 place-items-center rounded-md bg-ocean-cyan text-[10px] font-bold text-on-accent shadow-xs" aria-hidden="true">
          {initials(name)}
        </span>
        <span className="hidden max-w-28 truncate font-semibold md:inline">{name}</span>
        <span className="sr-only md:hidden">Account</span>
        <ChevronDown className={`hidden size-3 text-ink-dim transition-transform duration-200 sm:block ${open ? "rotate-180 text-ocean-cyan" : ""}`} aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className="glass absolute top-full right-0 z-50 mt-2 w-72 rounded-2xl border border-hairline-strong/80 bg-shelf-1/95 p-3 text-xs shadow-2xl backdrop-blur-xl animate-in fade-in slide-in-from-top-2 duration-150"
        >
          {/* Header Profile Section */}
          <div className="flex items-center gap-3 rounded-xl border border-hairline/60 bg-shelf-2/60 p-2.5 shadow-inner">
            <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-ocean-cyan text-xs font-extrabold text-on-accent shadow-sm">
              {initials(name)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-1">
                <p className="truncate font-bold text-ink text-sm leading-tight">{name}</p>
                {auth.profile && auth.profile.role !== "user" && (
                  <span className="shrink-0 rounded-full border border-accent/40 bg-accent/10 px-1.5 py-0.2 font-mono text-[9px] font-bold tracking-wider text-accent uppercase">
                    {auth.profile.role}
                  </span>
                )}
              </div>
              {identifier && (
                <p className="truncate font-mono text-[10px] text-ink-dim mt-0.5">{identifier}</p>
              )}
            </div>
          </div>

          {/* Viewing Persona Selector Card */}
          <div className="mt-2.5 rounded-xl border border-hairline/60 bg-shelf-2/30 p-2.5 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                Viewing Persona
              </span>
              <span className="size-1.5 rounded-full bg-ocean-cyan" />
            </div>
            <div className="w-full">
              <PersonaSelector />
            </div>
          </div>

          <div className="my-2 border-t border-hairline/60" />

          {/* Navigation Links */}
          <div className="space-y-0.5">
            <Link
              role="menuitem"
              href="/watches"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-xl px-2.5 py-2 font-medium text-ink-muted transition-colors hover:bg-shelf-2 hover:text-ink"
            >
              <Eye className="size-4 text-ocean-cyan" aria-hidden="true" />
              <span>My watches</span>
            </Link>

            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false);
                signOut();
              }}
              className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left font-medium text-ink-muted transition-colors hover:bg-no-go/10 hover:text-no-go"
            >
              <LogOut className="size-4" aria-hidden="true" />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
