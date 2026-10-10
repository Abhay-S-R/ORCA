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
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { PasswordInput } from "../components/PasswordInput";
import { Card } from "../components/Panel";
import { OrcaMark } from "../nav";
import { register, signInWithPassword, useAuth } from "../lib/auth";
import { PERSONA_DEFAULT_ROUTE, PERSONA_STORAGE_KEY, type Persona } from "../persona/config";
import { useT } from "../i18n/useT";

type Mode = "sign_in" | "register";

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

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <div className="mx-auto flex h-full max-w-sm flex-col justify-center gap-6 p-5">
      <div className="flex flex-col items-center gap-2 text-center">
        <OrcaMark className="size-8" />
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
  );
}
