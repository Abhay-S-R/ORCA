// Buttons. A CTA says exactly what happens when it is used, so there is no
// `variant="cta"` here that would tempt a generic label — only weight.
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger";

const VARIANT: Record<Variant, string> = {
  primary:
    "border border-ocean-cyan/50 bg-ocean-cyan text-on-accent font-bold shadow-sm hover:bg-ocean-cyan/90 active:scale-[0.98] disabled:border-hairline disabled:bg-shelf-3/50 disabled:text-ink-dim",
  ghost:
    "border border-hairline bg-shelf-2/70 text-ink-muted hover:border-ocean-cyan/50 hover:bg-shelf-3/80 hover:text-ink active:scale-[0.98]",
  danger:
    "border border-no-go/60 bg-no-go text-on-accent font-bold shadow-sm hover:bg-no-go/90 active:scale-[0.98]",
};

export function Button({
  variant = "ghost",
  icon,
  children,
  className = "",
  ...rest
}: { variant?: Variant; icon?: ReactNode; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
