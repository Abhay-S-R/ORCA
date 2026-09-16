"use client";

// The one app-wide sign-in / account control, in the status bar next to the
// persona selector. Before it, signing in or out was only possible from
// inside /watches.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Eye, LogIn, LogOut } from "lucide-react";
import { displayNameOf, signOut, useAuth } from "../lib/auth";

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
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded border border-hairline bg-shelf-2/80 p-0.5 text-[11px] sm:pr-1.5 font-medium tracking-wide text-ink shadow-sm transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/80"
      >
        <span className="grid size-5 place-items-center rounded-sm bg-ocean-cyan text-[9px] font-bold text-on-accent" aria-hidden="true">
          {initials(name)}
        </span>
        <span className="hidden max-w-28 truncate md:inline">{name}</span>
        <span className="sr-only md:hidden">Account</span>
        {/* Initials only on a phone: the status bar has no room to spare there. */}
        <ChevronDown className="hidden size-3 text-ink-dim sm:block" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className="glass absolute top-full right-0 z-50 mt-1.5 w-56 rounded-lg p-1.5 text-xs shadow-xl"
        >
          <div className="border-b border-hairline/60 px-2 pt-1 pb-2">
            <p className="truncate font-semibold text-ink">{name}</p>
            {auth.profile?.identifier && auth.profile.identifier !== name && (
              <p className="truncate font-mono text-[10px] text-ink-dim">{auth.profile.identifier}</p>
            )}
            {auth.profile && auth.profile.role !== "user" && (
              <p className="mt-1 inline-block rounded border border-accent/40 px-1 font-mono text-[9px] tracking-wider text-accent uppercase">
                {auth.profile.role}
              </p>
            )}
          </div>
          <Link
            role="menuitem"
            href="/watches"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-2 rounded-md px-2 py-1.5 text-ink-muted hover:bg-shelf-2 hover:text-ink"
          >
            <Eye className="size-3.5" aria-hidden="true" />
            My watches
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-ink-muted hover:bg-shelf-2 hover:text-no-go"
          >
            <LogOut className="size-3.5" aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
