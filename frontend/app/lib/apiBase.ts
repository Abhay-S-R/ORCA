// The one place the backend origin is written down. It used to be copy-pasted
// into eleven modules, so a deployment that moved the API had eleven chances
// to miss one — and a missed one silently falls back to localhost:8000, which
// looks fine in dev and 404s everything in production.
//
// Deliberately not "use client": it is a plain constant, so a server component
// can import it too. auth.ts re-exports it for the callers that already read
// it from there.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
