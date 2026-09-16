"use client";

// Sign in / create account (D1 auth, plan §5.4). One page, two modes — the
// fields barely differ, and a separate route would mean two places to keep
// the phone/email guidance in step. All token handling is lib/auth's.
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { PasswordInput } from "../components/PasswordInput";
import { Card } from "../components/Panel";
import { OrcaMark } from "../nav";
import { register, signInWithPassword } from "../lib/auth";

type Mode = "sign_in" | "register";

// Only same-app paths: `?next=https://evil.example` must not become an open
// redirect off the back of a successful sign-in.
function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/ask";
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("sign_in");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const registering = mode === "register";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const result = registering
      ? await register(identifier, password, displayName)
      : await signInWithPassword(identifier, password);
    setPending(false);
    if (result.ok) router.push(nextPath());
    else setError(result.error);
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
          {registering ? "Create your ORCA account" : "Sign in to ORCA"}
        </h1>
        <p className="text-xs text-ink-muted">
          {registering
            ? "Keep your chats, watches and alerts across devices."
            : "Your chats, watches and alerts, on any device."}
        </p>
      </div>

      <div role="tablist" aria-label="Account" className="grid grid-cols-2 gap-1 rounded-lg border border-hairline bg-shelf-2/60 p-1">
        {(
          [
            ["sign_in", "Sign in"],
            ["register", "Create account"],
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
            <Field label="Name" hint="optional — how ORCA greets you">
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
          <Field label="Phone or email" hint={registering ? "a 10-digit mobile number works, e.g. 98765 43210" : undefined}>
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
          <Field label="Password" hint={registering ? "at least 8 characters" : undefined}>
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
                ? "Creating account…"
                : "Signing in…"
              : registering
                ? "Create account"
                : "Sign in"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
