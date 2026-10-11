"use client";

// Sign in / create account (D1 auth, plan §5.4). One page, two modes — the
// fields barely differ, and a separate route would mean two places to keep
// the phone/email guidance in step. All token handling is lib/auth's.
//
// Home port (P-HP-1) — the registration form now collects the user's home
// port (lat/lon + optional name). After a successful register the tokens are
// stored and then PUT /api/profile/home-port is called in the background so
// the account carries the port from its very first use. The field is optional
// but prominently placed so a fisherman does not have to hunt for it later.
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldAlert, UserCheck } from "lucide-react";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { PasswordInput } from "../components/PasswordInput";
import { Card } from "../components/Panel";
import { OrcaMark } from "../nav";
import { register, signInWithPassword, useAuth } from "../lib/auth";
import { PERSONA_DEFAULT_ROUTE, PERSONA_STORAGE_KEY, type Persona } from "../persona/config";
import { useT } from "../i18n/useT";

type Mode = "sign_in" | "register";

type DemoCredential = {
  id: string;
  title: string;
  badge: string;
  badgeColor: string;
  subtitle: string;
  username: string;
  password: string;
  homePort: string;
  language: string;
  vesselType: string;
  personaTarget: Persona;
  icon: typeof UserCheck;
};

const DEMO_PRESETS: DemoCredential[] = [
  {
    id: "demouser",
    title: "Demo User (All Personas)",
    badge: "Fisherman · Navigator · Researcher",
    badgeColor: "bg-ocean-cyan/15 text-ocean-cyan border-ocean-cyan/30",
    subtitle: "General mariner account for sea safety, routing & analytics",
    username: "demouser",
    password: "demouser123",
    homePort: "Mumbai",
    language: "English",
    vesselType: "Fibreglass boat",
    personaTarget: "fisherman",
    icon: UserCheck,
  },
  {
    id: "mumbai_authority",
    title: "Coastal Authority (Mumbai)",
    badge: "Port Authority",
    badgeColor: "bg-amber-600/20 text-amber-900 border-amber-600/50 font-bold",
    subtitle: "Authority account for District Ops (/ops), distress alerts & broadcasts",
    username: "authority.mumbai@orca.test",
    password: "orca-authority-local-dev",
    homePort: "Mumbai",
    language: "English",
    vesselType: "Patrol Craft",
    personaTarget: "coastal_authority",
    icon: ShieldAlert,
  },
];

// Only same-app paths: `?next=https://evil.example` must not become an open
// redirect off the back of a successful sign-in.
function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  try {
    const persona = window.localStorage.getItem(PERSONA_STORAGE_KEY) as Persona | null;
    if (persona && persona in PERSONA_DEFAULT_ROUTE) return PERSONA_DEFAULT_ROUTE[persona];
  } catch {
    /* storage disabled — fall through to the default */
  }
  return "/ask";
}

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const t = useT();
  const [mode, setMode] = useState<Mode>("sign_in");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const registering = mode === "register";

  // Already signed in (e.g. a stale bookmark) — nothing to do here.
  useEffect(() => {
    if (auth.status === "signed_in") router.replace(nextPath());
  }, [auth.status, router]);

  async function executeSignIn(userEmail: string, userPass: string) {
    setError(null);
    setPending(true);
    const result = await signInWithPassword(userEmail, userPass);
    setPending(false);
    if (result.ok) {
      router.push(nextPath());
    } else {
      setError(result.error);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);

    if (registering) {
      const result = await register(identifier, password, displayName);
      if (!result.ok) {
        setPending(false);
        setError(result.error);
        return;
      }
      setPending(false);
      router.push("/onboarding");
    } else {
      const result = await signInWithPassword(identifier, password);
      setPending(false);
      if (result.ok) router.push(nextPath());
      else setError(result.error);
    }
  }

  function handlePickDemo(preset: DemoCredential, autoSignIn = false) {
    setMode("sign_in");
    setIdentifier(preset.username);
    setPassword(preset.password);
    setError(null);

    // Save preferred persona to storage for sensible routing
    try {
      window.localStorage.setItem(PERSONA_STORAGE_KEY, preset.personaTarget);
    } catch {
      // storage disabled
    }

    if (autoSignIn) {
      void executeSignIn(preset.username, preset.password);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col items-center justify-start gap-6 p-4 py-8 sm:py-12">
        {/* Sign-in Form (Preserved compact max-w-sm as before) */}
        <div className="flex w-full max-w-sm flex-col gap-5">
          <div className="flex flex-col items-center gap-2 text-center pt-2">
            <OrcaMark className="size-8 shrink-0" />
          <h1 className="text-lg font-semibold tracking-tight text-ink">
            {registering ? t("login.createTitle") : t("login.signInTitle")}
          </h1>
          <p className="text-xs text-ink-muted">
            {registering ? t("login.createSubtitle") : t("login.signInSubtitle")}
          </p>
        </div>

        <div role="tablist" aria-label={t("login.accountTabs")} className="grid grid-cols-2 gap-1 rounded-lg border border-hairline bg-shelf-2/60 p-1">
          {(
            [
              ["sign_in", t("common.signIn")],
              ["register", t("common.createAccount")],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              onClick={() => switchMode(id)}
              className={`rounded-md py-1.5 text-xs font-semibold tracking-wide transition-colors ${
                mode === id ? "bg-shelf-3 text-ocean-cyan shadow-sm" : "text-ink-dim hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <Card>
          <form onSubmit={handleSubmit}>
            {registering && (
              <Field label={t("login.name")} hint={t("login.nameHint")}>
                {(id) => (
                  <input
                    id={id}
                    className={inputClass}
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    autoComplete="name"
                    maxLength={80}
                  />
                )}
              </Field>
            )}
            <Field label={t("login.phoneOrEmail")} hint={registering ? t("login.phoneHint") : undefined}>
              {(id) => (
                <input
                  id={id}
                  className={inputClass}
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  autoComplete="username"
                  inputMode="email"
                  required
                />
              )}
            </Field>
            <Field label={t("login.password")} hint={registering ? t("login.passwordHint") : undefined}>
              {(id) => (
                <PasswordInput
                  id={id}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={registering ? "new-password" : "current-password"}
                  minLength={8}
                  maxLength={128}
                  required
                />
              )}
            </Field>

            {error && (
              <p role="alert" className="mb-3 text-xs text-no-go">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" className="w-full" disabled={pending}>
              {pending
                ? registering
                  ? t("login.creatingAccount")
                  : t("login.signingIn")
                : registering
                  ? t("common.createAccount")
                  : t("common.signIn")}
            </Button>
          </form>
        </Card>
      </div>

      {/* Demo Accounts Horizontal Container */}
      <div className="flex w-full flex-col gap-2.5 rounded-xl border border-hairline bg-shelf-1/60 p-3.5 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-ink">Demo Accounts (1-Click Fill for the Judge Review)</span>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-ink-muted">Quick Access</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-0.5">
          {DEMO_PRESETS.map((preset) => {
            const Icon = preset.icon;
            const isSelected = identifier.toLowerCase() === preset.username.toLowerCase();
            return (
              <div
                key={preset.id}
                className={`group flex flex-col justify-between gap-3 rounded-lg border p-3 transition-all ${
                  isSelected
                    ? "border-ocean-cyan/60 bg-shelf-3 shadow-sm ring-1 ring-ocean-cyan/30"
                    : "border-hairline bg-shelf-2/70 hover:border-hairline-bright hover:bg-shelf-2"
                }`}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-start gap-2">
                    <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-shelf-3 border border-hairline">
                      <Icon className="size-3.5 text-ink" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-ink leading-tight">
                        {preset.title}
                      </div>
                      <span
                        className={`inline-block mt-1 rounded px-1.5 py-0.5 text-[9px] font-semibold border ${preset.badgeColor}`}
                      >
                        {preset.badge}
                      </span>
                    </div>
                  </div>
                  <p className="text-[11px] text-ink-muted leading-relaxed min-h-[30px]">
                    {preset.subtitle}
                  </p>
                </div>

                {/* 2-row attribute boxes (Username, Home Port, Language, Vessel Type) */}
                <div className="grid grid-cols-2 gap-1.5">
                  <div className="flex flex-col justify-center rounded-md bg-shelf-1/80 px-2 py-1.5 border border-hairline/60">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-ink-muted">Username</span>
                    <span className="text-[11px] font-mono font-medium text-ink truncate select-all" title={preset.username}>
                      {preset.username}
                    </span>
                  </div>

                  <div className="flex flex-col justify-center rounded-md bg-shelf-1/80 px-2 py-1.5 border border-hairline/60">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-ink-muted">Home Port</span>
                    <span className="text-[11px] font-medium text-ink truncate select-all" title={preset.homePort}>
                      {preset.homePort}
                    </span>
                  </div>

                  <div className="flex flex-col justify-center rounded-md bg-shelf-1/80 px-2 py-1.5 border border-hairline/60">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-ink-muted">Language</span>
                    <span className="text-[11px] font-medium text-ink truncate select-all" title={preset.language}>
                      {preset.language}
                    </span>
                  </div>

                  <div className="flex flex-col justify-center rounded-md bg-shelf-1/80 px-2 py-1.5 border border-hairline/60">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-ink-muted">Vessel Type</span>
                    <span className="text-[11px] font-medium text-ink truncate select-all" title={preset.vesselType}>
                      {preset.vesselType}
                    </span>
                  </div>
                </div>

                <div className="pt-0.5">
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => handlePickDemo(preset, true)}
                    className="flex w-full items-center justify-center gap-1.5 rounded bg-ocean-cyan/15 px-2 py-1.5 text-[11px] font-semibold text-ocean-cyan border border-ocean-cyan/30 transition-all hover:bg-ocean-cyan/25 active:scale-95 disabled:opacity-50"
                  >
                    Sign In
                    <ArrowRight className="size-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  </div>
);
}
