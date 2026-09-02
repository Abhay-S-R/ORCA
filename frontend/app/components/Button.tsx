// Buttons. A CTA says exactly what happens when it is used, so there is no
// `variant="cta"` here that would tempt a generic label — only weight.
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-abyss font-semibold hover:bg-accent/90 disabled:bg-accent/40",
  ghost: "border border-hairline text-ink-muted hover:border-hairline-strong hover:text-ink",
  danger: "bg-no-go text-abyss font-semibold hover:bg-no-go/90",
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
      className={`inline-flex items-center justify-center gap-2 rounded-sm px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
