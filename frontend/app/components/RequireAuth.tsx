"use client";

// Gate for every ORCA dashboard/chat route (P0 security fix — ORCA must not
// be reachable pre-login, see NAV_ROUTES in persona/config.ts). Tokens live
// in localStorage, not a cookie, so there is nothing a server-side proxy.ts
// could check — the guard has to run client-side, same as every other
// getToken() check already in this codebase (watches/page.tsx, ops/page.tsx).
// ponytail: a signed-out visitor still downloads the page's JS before being
// bounced — real confidentiality is the backend's job (every /api route is
// already owner-scoped, see chats_routes.py). Upgrade path if that's ever not
// enough: move the token into an httpOnly cookie and check it in proxy.ts.
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "../lib/auth";
import { Skeleton } from "./States";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (auth.status === "signed_out") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [auth.status, pathname, router]);

  if (auth.status !== "signed_in") return <Skeleton className="m-6 h-[70vh]" />;
  return <>{children}</>;
}
