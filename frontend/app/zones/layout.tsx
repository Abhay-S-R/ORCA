import type { ReactNode } from "react";
import { RequireAuth } from "../components/RequireAuth";

export default function Layout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
