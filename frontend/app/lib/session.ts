// Multi-turn conversation memory (checklist P0 #1) is session-scoped by
// design, not durable history — sessionStorage matches that exactly: a
// fresh tab gets a fresh id, a refresh within the same tab keeps the same
// conversation the backend's Redis-backed orca.session module remembers.
const KEY = "orca-session-id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = sessionStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(KEY, id);
  }
  return id;
}
