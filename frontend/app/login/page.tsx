"use client";

// Sign-in (D1 auth, plan §5.4). Posts straight to lib/auth's signIn(), which
// already owns the token — this page is just the form around it.
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { Card } from "../components/Panel";
import { OrcaMark } from "../nav";
import { signIn } from "../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const ok = await signIn(identifier, password);
    setPending(false);
    if (ok) router.push("/ask");
    else setError("Wrong phone/email or password.");
  }

  return (
    <div className="mx-auto flex h-full max-w-sm flex-col justify-center gap-6 p-5">
      <div className="flex flex-col items-center gap-2">
        <OrcaMark className="size-8" />
        <h1 className="text-lg font-semibold tracking-tight text-ink">Sign in to ORCA</h1>
      </div>
      <Card>
        <form onSubmit={handleSubmit}>
          <Field label="Phone or email">
            {(id) => (
              <input
                id={id}
                className={inputClass}
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                autoComplete="username"
                required
              />
            )}
          </Field>
          <Field label="Password">
            {(id) => (
              <input
                id={id}
                type="password"
                className={inputClass}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                minLength={8}
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
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
