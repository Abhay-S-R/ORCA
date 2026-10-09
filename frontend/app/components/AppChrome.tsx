"use client";

// Root layout is a server component (it exports metadata/viewport), so the
// pathname check that decides whether a route wears the app's chrome lives
// in this one client wrapper instead. "/" is the public landing page (the
// app itself starts at /ask) — it shouldn't carry the authenticated app's
// nav rail, status bar, SOS button or notification feed alongside its own
// hero and title.
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { NavRail, SosButton } from "../nav";
import { useAuth } from "../lib/auth";
import { NotificationBell } from "./NotificationBell";
import { CriticalAlertTakeover } from "./CriticalAlertTakeover";
import { StatusBar } from "./StatusBar";

const NO_CHROME_ROUTES = ["/", "/onboarding"];
// P3.4 — the setup wizard's onboarding gate exempts only the screens a
// caller can legitimately reach before it: the landing page, the sign-in
// form, and the wizard itself. Every other route bounces back until the
// account's role is resolved.
const ONBOARDING_EXEMPT = ["/", "/login", "/onboarding"];

export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuth();

  useEffect(() => {
    // P3.4 (`R-UX-6`) — "full screen, not skippable" for ANY signed-in
    // account with no role yet, not only a fresh signup: an existing
    // account created before this wizard existed hits the same gate the
    // next time it navigates.
    if (
      auth.status === "signed_in" &&
      auth.profile &&
      auth.profile.default_persona === "unresolved" &&
      !ONBOARDING_EXEMPT.includes(pathname)
    ) {
      router.replace("/onboarding");
    }
  }, [auth.status, auth.profile, pathname, router]);

  if (NO_CHROME_ROUTES.includes(pathname)) {
    return (
      <>
        <main id="main-content" className="h-full overflow-y-auto">
          {children}
        </main>
        <CriticalAlertTakeover />
      </>
    );
  }

  return (
    <>
      <div className="flex h-full">
        <NavRail />
        <div className="flex min-w-0 flex-1 flex-col">
          <StatusBar />
          {/* The only scroll container in the app. The shell is fixed so
              a full-bleed chart can fill the viewport exactly. */}
          <main id="main-content" className="min-h-0 flex-1 overflow-y-auto pb-16 sm:pb-0">
            {children}
          </main>
        </div>
      </div>
      <SosButton />
      {/* Sentinel notification feed — persistent, like SOS. Renders
          nothing until there is an authenticated session. */}
      <NotificationBell />
      {/* P4.12 — the ≤1 nm boundary band / cyclone Red full-screen takeover.
          Mounted once here so it works on any route, SOS stays visible
          through it (it renders above this, not instead of it). */}
      <CriticalAlertTakeover />
    </>
  );
}
