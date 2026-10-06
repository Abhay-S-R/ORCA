// Minimal layout wrapper — matches /voyage/layout.tsx exactly.
import type { ReactNode } from "react";
export default function SeaRouteLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
