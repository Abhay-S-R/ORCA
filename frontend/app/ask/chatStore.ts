"use client";

// Where Ask chats are kept. Two stores behind one shape: a guest's chats live
// in this browser (localStorage); a signed-in user's live in their account
// (/api/chats, backend orca/db/chats_repo.py). The thread hook and the history
// rail never branch on which one they have.
import { getAgentMeta } from "../components/AgentPill";
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

// ---------------------------------------------------------------------------
// Agent confidence that survives a reload.
//
// The strip gets its confidence from `turn.spans`, which are built from the
// `agent_span` events as the answer streams. Two things used to leave a
// reopened chat without any:
//
//   1. A query-cache hit streams NO agent_span events at all — only the final
//      answer — so the turn is saved with `spans: []`. ChatTurn papers over it
//      live by falling back to `answer.agent_confidence`, but the stored turn
//      still has nothing, and the fallback's own last resort is ten grey pills
//      with no confidence on them.
//   2. Turns saved before spans carried `confidence_tier` at all.
//
// `answer.agent_confidence` carries the same per-agent tiers and HAS been
// stored all along, so both cases are repairable from data already on disk.
// This runs on save (so new turns never depend on the fallback) and on load
// (so chats already saved are repaired the next time they are opened).
//
// Unrepairable: a turn saved with an empty `spans` AND no `agent_confidence`.
// That confidence was never written down and cannot be recovered — the strip
// falls back to plain ticks for it, as before.

// Spans and agent_confidence spell the same agent differently
// ("distress_check" vs "distress"), so they are matched on the registry's
// resolved label rather than the raw string.
function agentKey(raw: string): string {
  return getAgentMeta(raw)?.shortLabel ?? raw.toLowerCase().replace(/[^a-z0-9]/g, "");
}

// The repair for chats saved before spans carried confidence at all — which
// is most chats older than the confidence-scoring commit. Their spans exist
// but read `{agent_name, status}` with no tier, and their answers have no
// `agent_confidence` either, so there is nothing local to fill from.
//
// It is not lost, though: `_persist_audit_trace_log` has been writing every
// agent's scored confidence to Postgres all along, keyed by the same
// `query_id` the turn already stores. So the tiers come back from
// /trace/{query_id} — the same rows /reasoning draws its inspector from.
//
// Best-effort and one-shot per turn: a pruned or missing trace just leaves the
// strip as it was. The caller saves the repaired turn, so this costs one fetch
// the first time an old chat is opened and nothing on every open after that.
export async function confidenceFromTrace(turn: Turn): Promise<AgentSpan[] | null> {
  const queryId = turn.answer?.query_id;
  if (!queryId || !turn.spans.length) return null;
  try {
    const res = await fetch(`${API_BASE}/trace/${encodeURIComponent(queryId)}`);
    if (!res.ok) return null;
    const graph = (await res.json()) as { nodes?: { agent_name?: string; confidence_tier?: string }[] };
    const byKey = new Map<string, string>();
    for (const node of graph.nodes ?? []) {
      if (node.agent_name && node.confidence_tier) byKey.set(agentKey(node.agent_name), node.confidence_tier);
    }
    if (!byKey.size) return null;
    let repaired = false;
    const spans = turn.spans.map((span) => {
      if (span.confidence_tier) return span;
      const tier = byKey.get(agentKey(span.agent_name));
      if (!tier) return span;
      repaired = true;
      return { ...span, confidence_tier: tier as AgentSpan["confidence_tier"] };
    });
    return repaired ? spans : null;
  } catch {
    return null; // the strip keeps its plain ticks; nothing else depends on this
  }
}

export function withCachedConfidence(turn: Turn): Turn {
  const fromAnswer = turn.answer?.agent_confidence ?? [];
  if (!fromAnswer.length) return turn;
  if (!turn.spans.length) return { ...turn, spans: fromAnswer };
  if (turn.spans.every((s) => s.confidence_tier)) return turn;

  const byKey = new Map(fromAnswer.map((s) => [agentKey(s.agent_name), s]));
  return {
    ...turn,
    spans: turn.spans.map((s) =>
      s.confidence_tier ? s : { ...s, confidence_tier: byKey.get(agentKey(s.agent_name))?.confidence_tier },
    ),
  };
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

// Carries the status so a caller can tell "try again later" from "this will
// never succeed" — a 404 on save means the chat is not this account's, and
// retrying it forever is what "Not saved yet — retrying" used to do.
export class ChatRequestError extends Error {
  constructor(readonly status: number) {
    super(`chat request failed: ${status}`);
  }
}

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new ChatRequestError(res.status);
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
      // Keyed on the TURN's id, not the answer's query_id. Every re-run mints
      // a new query_id, so keying on that filed the re-run as a second turn
      // and the chat showed the same question twice. `turn.id` is stable: a
      // new turn's own uuid, and for a loaded turn the id it was stored under.
      await authFetch(`/api/chats/${chatId}/turns/${turn.id}`, {
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
    .slice(-20); // the backend keeps the last 20 turns (session.MAX_TURNS)
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
    `- Exported from Sagar Sarathi: ${new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST`,
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
