"use client";

// Root layout is a server component (it exports metadata/viewport), so the
// pathname check that decides whether a route wears the app's chrome lives
// in this one client wrapper instead. "/" is the public landing page (the
// app itself starts at /ask) — it shouldn't carry the authenticated app's
// nav rail, status bar, SOS button or notification feed alongside its own
// hero and title.
import { usePathname } from "next/navigation";
import { NavRail, SosButton } from "../nav";
import { NotificationBell } from "./NotificationBell";
import { StatusBar } from "./StatusBar";

const NO_CHROME_ROUTES = ["/"];

export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (NO_CHROME_ROUTES.includes(pathname)) {
    return (
      <main id="main-content" className="h-full overflow-y-auto">
        {children}
      </main>
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
    </>
  );
}
