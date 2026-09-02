// Design system primitive (plan §3.2). Semantic <section> + heading so
// every surface's panels are landmark-navigable, not just visually boxed.
import type { ReactNode } from "react";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded border border-black/10 p-4 ${className}`}>
      {title && <h2 className="mb-2 text-sm font-semibold">{title}</h2>}
      {children}
    </section>
  );
}
