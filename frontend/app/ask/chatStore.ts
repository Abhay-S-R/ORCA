"use client";

// Where Ask chats are kept. Two stores behind one shape: a guest's chats live
// in this browser (localStorage); a signed-in user's live in their account
// (/api/chats, backend orca/db/chats_repo.py). The thread hook and the history
// rail never branch on which one they have.
import { authFetch } from "../lib/auth";
import { API_BASE } from "../lib/apiBase";
import type { Persona } from "../persona/config";
import type { AgentSpan, FinalResponse, Turn } from "./useAskThread";

export type ChatSummary = {
  id: string;
  title: string | null;
  pinned: boolean;
  persona: Persona;
  language: string;
  started_at: string;
  last_seen_at: string;
  turn_count: number;
  first_question: string | null;
  last_question: string | null;
};

export type LoadedChat = { summary: ChatSummary; turns: Turn[] };

export interface ChatStore {
  kind: "browser" | "account";
  list(query?: string): Promise<ChatSummary[]>;
  load(id: string): Promise<LoadedChat | null>;
  // Called whenever a turn changes. Stores decide what is worth keeping — the
  // account store only keeps answered turns.
  saveTurn(chatId: string, turn: Turn, persona: Persona): Promise<void>;
  update(id: string, patch: { title?: string | null; pinned?: boolean }): Promise<void>;
  remove(id: string): Promise<void>;
}

export function chatTitle(chat: Pick<ChatSummary, "title" | "first_question">): string {
  return chat.title || chat.first_question || "New chat";
}

// The answer fields the card never reads but that dominate its size — the
// backend strips the same two before storing (chats_repo.storable_answer).
function storableAnswer(answer: FinalResponse): FinalResponse {
  const copy: Record<string, unknown> = { ...answer };
  delete copy.audit_trace_log;
  delete copy.visualization_payload;
  return copy as FinalResponse;
}

// ---------------------------------------------------------------------------
// Browser store

const CHATS_KEY = "orca-ask-chats";
// The single-thread keys this store replaced. Read once, migrated, removed.
const LEGACY_THREAD_KEY = "orca-ask-thread";
const LEGACY_CHAT_ID_KEY = "orca-ask-chat-id";
// ponytail: fixed cap, oldest unpinned evicted first — localStorage is ~5 MB
// per origin and a chat with five answers is tens of KB. Signed-in users have
// no such cap; say so in the rail rather than raise this.
export const BROWSER_CHAT_LIMIT = 50;

type BrowserChat = {
  id: string;
  title: string | null;
  pinned: boolean;
  persona: Persona;
  created_at: string;
  updated_at: string;
  turns: Turn[];
};

function readBrowserChats(): BrowserChat[] {
  try {
    const raw = localStorage.getItem(CHATS_KEY);
    if (raw) return JSON.parse(raw) as BrowserChat[];
    return migrateLegacyThread();
  } catch {
    return [];
  }
}

function migrateLegacyThread(): BrowserChat[] {
  const raw = localStorage.getItem(LEGACY_THREAD_KEY);
  const turns = raw ? (JSON.parse(raw) as Turn[]) : [];
  const now = new Date().toISOString();
  // Same id as before, so the backend context window it already has still fits.
  const id = localStorage.getItem(LEGACY_CHAT_ID_KEY) ?? crypto.randomUUID();
  const chats: BrowserChat[] = turns.length
    ? [{ id, title: null, pinned: false, persona: "unresolved", created_at: now, updated_at: now, turns }]
    : [];
  writeBrowserChats(chats);
  // The thread that was on screen before history existed is still on screen.
  if (turns.length) writeActiveChat(id);
  localStorage.removeItem(LEGACY_THREAD_KEY);
  localStorage.removeItem(LEGACY_CHAT_ID_KEY);
  return chats;
}

// Which chat Ask reopens on load. One key for both stores: an id from the
// other store simply fails to load, and Ask starts a new chat.
const ACTIVE_KEY = "orca-ask-active-chat";

export function readActiveChat(): string | null {
  try {
    readBrowserChats(); // runs the one-time legacy migration, which may set it
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function writeActiveChat(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    /* storage disabled — Ask just opens on a new chat next time */
  }
}

function writeBrowserChats(chats: BrowserChat[]) {
  const byAge = (a: BrowserChat, b: BrowserChat) => a.updated_at.localeCompare(b.updated_at);
  let kept = [...chats];
  while (kept.length > BROWSER_CHAT_LIMIT) {
    const oldest = kept.filter((c) => !c.pinned).sort(byAge)[0] ?? kept.sort(byAge)[0];
    kept = kept.filter((c) => c !== oldest);
  }
  for (;;) {
    try {
      localStorage.setItem(CHATS_KEY, JSON.stringify(kept));
      return;
    } catch {
      // Quota: drop the oldest unpinned chat and try again, rather than lose
      // the turn that was just asked.
      const oldest = kept.filter((c) => !c.pinned).sort(byAge)[0];
      if (!oldest || kept.length <= 1) return;
      kept = kept.filter((c) => c !== oldest);
    }
  }
}

function browserSummary(chat: BrowserChat): ChatSummary {
  const asked = chat.turns.map((t) => t.askedQuery);
  return {
    id: chat.id,
    title: chat.title,
    pinned: chat.pinned,
    persona: chat.persona,
    language: chat.turns.find((t) => t.answer)?.answer?.detected_language ?? "en",
    started_at: chat.created_at,
    last_seen_at: chat.updated_at,
    turn_count: chat.turns.length,
    first_question: asked[0] ?? null,
    last_question: asked[asked.length - 1] ?? null,
  };
}

function byPinThenRecent(a: ChatSummary, b: ChatSummary) {
  return Number(b.pinned) - Number(a.pinned) || b.last_seen_at.localeCompare(a.last_seen_at);
}

export const browserStore: ChatStore = {
  kind: "browser",
  async list(query) {
    const q = query?.trim().toLowerCase();
    return readBrowserChats()
      .filter((c) => c.turns.length > 0)
      .filter((c) => !q || (c.title ?? "").toLowerCase().includes(q) || c.turns.some((t) => t.askedQuery.toLowerCase().includes(q)))
      .map(browserSummary)
      .sort(byPinThenRecent);
  },
  async load(id) {
    const chat = readBrowserChats().find((c) => c.id === id);
    return chat ? { summary: browserSummary(chat), turns: chat.turns } : null;
  },
  async saveTurn(chatId, turn, persona) {
    const now = new Date().toISOString();
    const chats = readBrowserChats();
    const chat = chats.find((c) => c.id === chatId);
    if (!chat) {
      chats.push({ id: chatId, title: null, pinned: false, persona, created_at: now, updated_at: now, turns: [turn] });
    } else {
      const i = chat.turns.findIndex((t) => t.id === turn.id);
      if (i === -1) chat.turns.push(turn);
      else chat.turns[i] = turn;
      chat.updated_at = now;
    }
    writeBrowserChats(chats);
  },
  async update(id, patch) {
    const chats = readBrowserChats();
    const chat = chats.find((c) => c.id === id);
    if (!chat) return;
    if ("title" in patch) chat.title = patch.title?.trim() || null;
    if (patch.pinned !== undefined) chat.pinned = patch.pinned;
    writeBrowserChats(chats);
  },
  async remove(id) {
    writeBrowserChats(readBrowserChats().filter((c) => c.id !== id));
  },
};

export function browserChatCount(): number {
  return readBrowserChats().filter((c) => c.turns.length > 0).length;
}

// ---------------------------------------------------------------------------
// Account store

type ServerTurn = {
  query_id: string;
  asked_query: string;
  answer: FinalResponse;
  spans: AgentSpan[];
  rendered_as: Persona | null;
  created_at: string;
};

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`chat request failed: ${res.status}`);
  return res;
}

export const accountStore: ChatStore = {
  kind: "account",
  async list(query) {
    const q = query?.trim();
    const res = await ok(await authFetch(`/api/chats${q ? `?q=${encodeURIComponent(q)}` : ""}`));
    return res.json();
  },
  async load(id) {
    const res = await authFetch(`/api/chats/${id}`);
    if (res.status === 404) return null;
    const chat = (await (await ok(res)).json()) as ChatSummary & { turns: ServerTurn[] };
    const { turns, ...summary } = chat;
    return {
      summary,
      turns: turns.map((t) => ({
        id: t.query_id,
        askedQuery: t.asked_query,
        askedAt: t.created_at,
        spans: t.spans,
        answer: t.answer,
        streaming: false,
        failed: false,
        renderedAs: t.rendered_as,
        focus: null, // derived by the thread hook, in order
      })),
    };
  },
  async saveTurn(chatId, turn, persona) {
    if (!turn.answer || turn.streaming) return;
    await ok(
      await authFetch(`/api/chats/${chatId}/turns/${turn.answer.query_id ?? turn.id}`, {
        method: "PUT",
        body: JSON.stringify({
          asked_query: turn.askedQuery,
          answer: storableAnswer(turn.answer),
          spans: turn.spans,
          rendered_as: turn.renderedAs,
          persona,
        }),
      }),
    );
  },
  async update(id, patch) {
    await ok(await authFetch(`/api/chats/${id}`, { method: "PATCH", body: JSON.stringify(patch) }));
  },
  async remove(id) {
    const res = await authFetch(`/api/chats/${id}`, { method: "DELETE" });
    if (res.status !== 404) await ok(res);
  },
};

// Guest chats → account, on consent. Batches stay under the API's 25-chat
// limit. Browser copies are removed only after their batch was accepted.
export async function importBrowserChats(): Promise<number> {
  const chats = readBrowserChats().filter((c) => c.turns.some((t) => t.answer));
  let imported = 0;
  for (let i = 0; i < chats.length; i += 10) {
    const batch = chats.slice(i, i + 10);
    const res = await ok(
      await authFetch("/api/chats/import", {
        method: "POST",
        body: JSON.stringify({
          chats: batch.map((c) => ({
            id: c.id,
            title: c.title,
            pinned: c.pinned,
            persona: c.persona,
            turns: c.turns
              .filter((t) => t.answer)
              .map((t, n) => ({
                query_id: t.answer?.query_id ?? t.id,
                asked_query: t.askedQuery,
                answer: storableAnswer(t.answer as FinalResponse),
                spans: t.spans,
                rendered_as: t.renderedAs,
                // Turns saved before askedAt existed keep their order.
                created_at: t.askedAt ?? new Date(Date.parse(c.created_at) + n * 1000).toISOString(),
              })),
          })),
        }),
      }),
    );
    imported += (await res.json()).imported;
    const done = new Set(batch.map((c) => c.id));
    writeBrowserChats(readBrowserChats().filter((c) => !done.has(c.id)));
  }
  return imported;
}

// ---------------------------------------------------------------------------
// Context window restore — a reopened chat's follow-ups continue it.

export async function restoreContext(chatId: string, turns: Turn[]): Promise<void> {
  // P2.14 — a reopened chat must not resurrect context the user deliberately
  // told ORCA to forget. Only turns after the last "forget that, start fresh"
  // go back into the backend's window; the reset turn itself is not context.
  const lastReset = turns.map((t) => t.answer?.outcome).lastIndexOf("RESET");
  const answered = turns
    .slice(lastReset + 1)
    .filter((t) => t.answer && t.answer.outcome !== "RESET")
    .slice(-5);
  if (!answered.length) return;
  await fetch(`${API_BASE}/api/session/${chatId}/context`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      turns: answered.map((t) => ({ asked_query: t.askedQuery, answer: storableAnswer(t.answer as FinalResponse) })),
    }),
  });
}

// ---------------------------------------------------------------------------
// Export — a Markdown transcript with the verdict, place and sources of each
// answer, the record a coastal authority or researcher actually keeps.

const VERDICT_LABEL: Record<string, string> = { GO: "GO", CAUTION: "CAUTION", NO_GO: "NO GO" };

export function chatToMarkdown(summary: ChatSummary, turns: Turn[]): string {
  const lines = [
    `# ${chatTitle(summary)}`,
    "",
    `- Started: ${new Date(summary.started_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST`,
    `- Persona: ${summary.persona.replace("_", " ")}`,
    `- Exported from ORCA: ${new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST`,
    "",
  ];
  turns.forEach((turn, i) => {
    const a = turn.answer;
    lines.push("---", "", `## ${i + 1}. ${turn.askedQuery}`, "");
    if (!a) {
      lines.push("_No answer was received for this question._", "");
      return;
    }
    const facts: string[] = [];
    if (a.risk_assessment) facts.push(`**Verdict:** ${VERDICT_LABEL[a.risk_assessment.go_no_go] ?? a.risk_assessment.go_no_go} — ${a.risk_assessment.reason}`);
    const place = (a as FinalResponse & { user_location?: { place_name?: string | null } }).user_location?.place_name;
    if (place) facts.push(`**Location:** ${place}`);
    facts.push(`**Confidence:** ${a.confidence_tier}`);
    lines.push(...facts.map((f) => `${f}  `), "");
    lines.push(a.final_vernacular_response || a.final_english_response, "");
    if (a.final_vernacular_response && a.final_vernacular_response !== a.final_english_response) {
      lines.push("_English:_", "", a.final_english_response, "");
    }
    if (a.citations?.length) {
      lines.push("**Sources**", "");
      for (const c of a.citations) lines.push(`- ${c.dataset} (acquired ${c.acquisition_timestamp || "—"})`);
      lines.push("");
    }
  });
  return lines.join("\n");
}

export function downloadMarkdown(summary: ChatSummary, markdown: string) {
  const slug = chatTitle(summary).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "chat";
  const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `orca-${slug}.md`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
