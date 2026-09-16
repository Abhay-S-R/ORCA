"use client";

// Past chats, beside the Ask thread: open, search, rename, pin, export,
// delete. The same component is a collapsible rail on wide screens and a
// drawer on narrow ones, so there is one list to keep correct, not two.
// Storage is the ChatStore's business (./chatStore) — this component only
// says where chats are kept, because that differs by sign-in and matters.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Check,
  Cloud,
  CloudUpload,
  Download,
  HardDrive,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Skeleton } from "../components/States";
import type { AuthState } from "../lib/auth";
import {
  BROWSER_CHAT_LIMIT,
  browserChatCount,
  chatTitle,
  chatToMarkdown,
  downloadMarkdown,
  importBrowserChats,
  type ChatStore,
  type ChatSummary,
} from "./chatStore";

const GROUPS = ["Pinned", "Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"] as const;
type Group = (typeof GROUPS)[number];

function groupOf(chat: ChatSummary, now: Date): Group {
  if (chat.pinned) return "Pinned";
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const at = new Date(chat.last_seen_at).getTime();
  const day = 86_400_000;
  if (at >= startOfToday) return "Today";
  if (at >= startOfToday - day) return "Yesterday";
  if (at >= startOfToday - 7 * day) return "Previous 7 days";
  if (at >= startOfToday - 30 * day) return "Previous 30 days";
  return "Older";
}

function whenLabel(iso: string, group: Group): string {
  const date = new Date(iso);
  return group === "Today" || group === "Pinned"
    ? date.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
}

const LANGUAGE_TAG: Record<string, string> = {
  ta: "தமிழ்", hi: "हिंदी", te: "తెలుగు", ml: "മലയാളം", kn: "ಕನ್ನಡ", bn: "বাংলা", mr: "मराठी", gu: "ગુજરાતી", or: "ଓଡ଼ିଆ",
};

const labelClass = "text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim";
const iconButtonClass =
  "grid size-7 shrink-0 place-items-center rounded-lg border border-hairline/80 bg-shelf-1/90 text-ink-dim shadow-sm transition-colors hover:border-ocean-cyan/60 hover:text-ocean-cyan";

export function ChatHistoryRail({
  store,
  auth,
  activeChatId,
  version,
  variant,
  onOpen,
  onNew,
  onDeleted,
  onCollapse,
  onClose,
}: {
  store: ChatStore | null;
  auth: AuthState;
  activeChatId: string | null;
  version: number;
  variant: "rail" | "drawer";
  onOpen: (id: string) => Promise<boolean | undefined>;
  onNew: () => void;
  onDeleted: (id: string) => void;
  onCollapse?: () => void;
  onClose?: () => void;
}) {
  const [chats, setChats] = useState<ChatSummary[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!store) return;
    let cancelled = false;
    store
      .list(debounced)
      .then((next) => {
        if (cancelled) return;
        setChats(next);
        setLoadFailed(false);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [store, debounced, version, reload]);

  // A signed-in user never sees the other store's chats in this list —
  // reset rather than flash the previous store's rows.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing a list that belongs to the previous store
    setChats(null);
  }, [store]);

  function flash(message: string) {
    setNotice(message);
    setTimeout(() => setNotice((n) => (n === message ? null : n)), 4000);
  }

  async function mutate(change: (list: ChatSummary[]) => ChatSummary[], action: () => Promise<void>, failure: string) {
    setChats((list) => (list ? change(list) : list));
    try {
      await action();
    } catch {
      flash(failure);
    }
    setReload((n) => n + 1);
  }

  const rename = (chat: ChatSummary, title: string) =>
    mutate(
      (list) => list.map((c) => (c.id === chat.id ? { ...c, title: title.trim() || null } : c)),
      () => store!.update(chat.id, { title: title.trim() || null }),
      "Couldn't rename that chat.",
    );

  const togglePin = (chat: ChatSummary) =>
    mutate(
      (list) => list.map((c) => (c.id === chat.id ? { ...c, pinned: !c.pinned } : c)),
      () => store!.update(chat.id, { pinned: !chat.pinned }),
      chat.pinned ? "Couldn't unpin that chat." : "Couldn't pin that chat.",
    );

  const remove = (chat: ChatSummary) =>
    mutate(
      (list) => list.filter((c) => c.id !== chat.id),
      async () => {
        await store!.remove(chat.id);
        onDeleted(chat.id);
      },
      "Couldn't delete that chat.",
    );

  async function exportChat(chat: ChatSummary) {
    try {
      const loaded = await store!.load(chat.id);
      if (!loaded) throw new Error("gone");
      downloadMarkdown(loaded.summary, chatToMarkdown(loaded.summary, loaded.turns));
    } catch {
      flash("Couldn't export that chat.");
    }
  }

  async function open(chat: ChatSummary) {
    try {
      const found = await onOpen(chat.id);
      if (found === false) {
        flash("That chat no longer exists.");
        setReload((n) => n + 1);
      }
      onClose?.();
    } catch {
      flash("Couldn't open that chat.");
    }
  }

  const now = new Date();
  const grouped = GROUPS.map((group) => ({
    group,
    items: (chats ?? []).filter((c) => groupOf(c, now) === group),
  })).filter((g) => g.items.length > 0);

  return (
    <nav
      aria-label="Chat history"
      className={`flex min-h-0 flex-col gap-3 ${
        variant === "rail"
          ? "h-full w-56 shrink-0 rounded-2xl border border-hairline bg-shelf-1/60 p-3 shadow-lg xl:w-64"
          : "h-full w-full p-4"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-ocean-cyan/70" aria-hidden="true" />
          <span className={labelClass}>Chats</span>
        </span>
        {variant === "rail" ? (
          <button type="button" onClick={onCollapse} aria-label="Collapse chat history" className={iconButtonClass}>
            <PanelLeftClose className="size-3.5" aria-hidden="true" />
          </button>
        ) : (
          <button type="button" onClick={onClose} aria-label="Close chat history" className={iconButtonClass}>
            <X className="size-3.5" aria-hidden="true" />
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={() => {
          onNew();
          onClose?.();
        }}
        className="inline-flex items-center justify-center gap-2 rounded-lg border border-hairline bg-shelf-2/70 px-3 py-2 text-xs font-semibold tracking-wide text-ink-muted transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/80 hover:text-ink"
      >
        <Plus className="size-3.5" aria-hidden="true" />
        New chat
      </button>

      <label className="relative block">
        <span className="sr-only">Search chats</span>
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-dim" aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search chats"
          className="w-full rounded-lg border border-hairline bg-shelf-1/90 py-1.5 pr-2 pl-8 text-xs text-ink shadow-inner placeholder:text-ink-dim/60 transition-all hover:border-hairline-strong focus:border-ocean-cyan/70"
        />
      </label>

      <ImportPrompt auth={auth} onImported={(n) => {
        flash(n === 1 ? "Saved 1 chat to your account." : `Saved ${n} chats to your account.`);
        setReload((r) => r + 1);
      }} />

      <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
        {chats === null && !loadFailed && (
          <div className="flex flex-col gap-2 pt-1" aria-hidden="true">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-4/5" />
          </div>
        )}

        {loadFailed && (
          <div className="rounded-lg border border-hairline/60 bg-shelf-2/60 p-3 text-[11px] text-ink-muted">
            Couldn&apos;t load your chats.{" "}
            <button type="button" onClick={() => setReload((n) => n + 1)} className="font-semibold text-ocean-cyan hover:underline">
              Try again
            </button>
          </div>
        )}

        {chats?.length === 0 && !loadFailed && (
          <p className="px-1 pt-1 text-[11px] leading-relaxed text-ink-dim">
            {debounced.trim() ? `No chats match “${debounced.trim()}”.` : "Your chats will appear here once you ask a question."}
          </p>
        )}

        {grouped.map(({ group, items }) => (
          <section key={group} className="mb-3">
            <h3 className={`${labelClass} mb-1 px-1 font-mono`}>{group}</h3>
            <ul className="flex flex-col gap-0.5">
              {items.map((chat) => (
                <ChatRow
                  key={chat.id}
                  chat={chat}
                  group={group}
                  active={chat.id === activeChatId}
                  onOpen={() => void open(chat)}
                  onRename={(title) => void rename(chat, title)}
                  onTogglePin={() => void togglePin(chat)}
                  onExport={() => void exportChat(chat)}
                  onDelete={() => void remove(chat)}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>

      {notice && (
        <p role="status" className="rounded-lg border border-hairline/60 bg-shelf-3/80 px-2.5 py-1.5 text-[11px] text-ink-muted">
          {notice}
        </p>
      )}

      <StorageNote auth={auth} />
    </nav>
  );
}

// Collapsed rail: just enough to get the history back or start over.
export function CollapsedChatRail({ onExpand, onNew }: { onExpand: () => void; onNew: () => void }) {
  return (
    <div className="flex h-full w-11 shrink-0 flex-col items-center gap-2 rounded-2xl border border-hairline bg-shelf-1/60 py-3 shadow-lg">
      <button type="button" onClick={onExpand} aria-label="Show chat history" title="Chats" className={iconButtonClass}>
        <PanelLeftOpen className="size-3.5" aria-hidden="true" />
      </button>
      <button type="button" onClick={onNew} aria-label="New chat" title="New chat" className={iconButtonClass}>
        <Plus className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

function ChatRow({
  chat,
  group,
  active,
  onOpen,
  onRename,
  onTogglePin,
  onExport,
  onDelete,
}: {
  chat: ChatSummary;
  group: Group;
  active: boolean;
  onOpen: () => void;
  onRename: (title: string) => void;
  onTogglePin: () => void;
  onExport: () => void;
  onDelete: () => void;
}) {
  const [mode, setMode] = useState<"view" | "menu" | "rename" | "confirm-delete">("view");
  const [draft, setDraft] = useState("");
  const root = useRef<HTMLLIElement>(null);
  const title = chatTitle(chat);

  useEffect(() => {
    if (mode !== "menu") return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setMode("view");
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMode("view");
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [mode]);

  if (mode === "rename") {
    const commit = () => {
      if (draft.trim() !== (chat.title ?? "")) onRename(draft);
      setMode("view");
    };
    return (
      <li ref={root} className="rounded-lg border border-ocean-cyan/50 bg-shelf-3 p-1.5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            commit();
          }}
          className="flex items-center gap-1"
        >
          <label className="sr-only" htmlFor={`rename-${chat.id}`}>
            Chat name
          </label>
          <input
            id={`rename-${chat.id}`}
            autoFocus
            value={draft}
            maxLength={120}
            placeholder={chat.first_question ?? "Chat name"}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                setMode("view");
              }
            }}
            className="min-w-0 flex-1 rounded-md border border-hairline bg-shelf-1 px-2 py-1 text-xs text-ink focus:border-ocean-cyan/70"
          />
          <button type="submit" aria-label="Save name" className="grid size-6 place-items-center rounded-md text-ocean-cyan hover:bg-shelf-2">
            <Check className="size-3.5" aria-hidden="true" />
          </button>
        </form>
        <p className="mt-1 px-0.5 text-[10px] text-ink-dim">Leave blank to use the first question.</p>
      </li>
    );
  }

  if (mode === "confirm-delete") {
    return (
      <li ref={root} className="rounded-lg border border-no-go/40 bg-shelf-3 p-2">
        <p className="text-[11px] text-ink">
          Delete <span className="font-semibold">“{title}”</span>? This can&apos;t be undone.
        </p>
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            autoFocus
            onClick={() => {
              setMode("view");
              onDelete();
            }}
            className="rounded-md border border-no-go/60 bg-no-go px-2 py-1 text-[11px] font-bold text-on-accent hover:bg-no-go/90"
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => setMode("view")}
            className="rounded-md border border-hairline px-2 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink"
          >
            Cancel
          </button>
        </div>
      </li>
    );
  }

  const language = LANGUAGE_TAG[chat.language];
  return (
    <li ref={root} className="group relative">
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? "true" : undefined}
        className={`relative flex w-full flex-col gap-0.5 rounded-lg border px-2.5 py-1.5 pr-8 text-left transition-colors ${
          active
            ? "border-ocean-cyan/50 bg-shelf-3 shadow-sm"
            : "border-transparent hover:border-hairline hover:bg-shelf-2/70"
        }`}
      >
        {active && <span aria-hidden="true" className="absolute top-2 bottom-2 -left-px w-0.5 rounded-r bg-ocean-cyan" />}
        <span className="flex min-w-0 items-center gap-1.5">
          {chat.pinned && <Pin className="size-3 shrink-0 text-accent" aria-label="Pinned" />}
          <span className={`truncate text-xs ${active ? "font-semibold text-ink" : "text-ink"}`}>{title}</span>
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-ink-dim">
          <span data-readout>{whenLabel(chat.last_seen_at, group)}</span>
          <span aria-hidden="true">·</span>
          <span>
            {chat.turn_count} {chat.turn_count === 1 ? "question" : "questions"}
          </span>
          {language && (
            <span lang={chat.language} className="truncate rounded border border-hairline px-1 font-tamil text-[9px] text-ink-muted">
              {language}
            </span>
          )}
        </span>
      </button>

      <button
        type="button"
        aria-label={`Actions for ${title}`}
        aria-haspopup="menu"
        aria-expanded={mode === "menu"}
        onClick={() => setMode(mode === "menu" ? "view" : "menu")}
        className={`absolute top-1.5 right-1 grid size-6 place-items-center rounded-md text-ink-dim transition-opacity hover:bg-shelf-1 hover:text-ink focus-visible:opacity-100 ${
          active || mode === "menu" ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
        }`}
      >
        <MoreHorizontal className="size-3.5" aria-hidden="true" />
      </button>

      {mode === "menu" && (
        <div role="menu" className="glass absolute top-8 right-1 z-30 w-40 rounded-lg p-1 text-xs shadow-xl">
          <MenuItem
            icon={<Pencil className="size-3.5" aria-hidden="true" />}
            label="Rename"
            onClick={() => {
              setDraft(chat.title ?? "");
              setMode("rename");
            }}
          />
          <MenuItem
            icon={chat.pinned ? <PinOff className="size-3.5" aria-hidden="true" /> : <Pin className="size-3.5" aria-hidden="true" />}
            label={chat.pinned ? "Unpin" : "Pin to top"}
            onClick={() => {
              setMode("view");
              onTogglePin();
            }}
          />
          <MenuItem
            icon={<Download className="size-3.5" aria-hidden="true" />}
            label="Export (.md)"
            onClick={() => {
              setMode("view");
              onExport();
            }}
          />
          <MenuItem
            icon={<Trash2 className="size-3.5" aria-hidden="true" />}
            label="Delete"
            danger
            onClick={() => setMode("confirm-delete")}
          />
        </div>
      )}
    </li>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-ink-muted hover:bg-shelf-2 ${
        danger ? "hover:text-no-go" : "hover:text-ink"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

const DISMISS_PREFIX = "orca-ask-import-dismissed:";

// After sign-in: guest chats from this browser are offered to the account,
// never moved without consent.
function ImportPrompt({ auth, onImported }: { auth: AuthState; onImported: (count: number) => void }) {
  const userId = auth.status === "signed_in" ? auth.profile?.id : undefined;
  const [count, setCount] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!userId) return;
    let wasDismissed = false;
    try {
      wasDismissed = localStorage.getItem(DISMISS_PREFIX + userId) === "1";
    } catch {
      /* storage disabled — nothing to import from it either */
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reads localStorage, which only exists after mount
    setDismissed(wasDismissed);
    setCount(browserChatCount());
  }, [userId]);

  if (!userId || count === 0) return null;

  async function runImport() {
    setBusy(true);
    setFailed(false);
    try {
      const imported = await importBrowserChats();
      setCount(browserChatCount());
      onImported(imported);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const chats = count === 1 ? "1 chat" : `${count} chats`;

  // "Not now" is not "never": the guest chats are still only in this browser
  // and hidden while signed in, so a one-line way to save them stays put.
  // Hiding it for good once left people unable to find chats they had asked.
  if (dismissed) {
    return (
      <p className="flex items-start gap-1.5 rounded-lg border border-hairline/60 bg-shelf-2/60 px-2 py-1.5 text-[10px] leading-relaxed text-ink-dim">
        <CloudUpload className="mt-px size-3 shrink-0" aria-hidden="true" />
        <span>
          {chats} from before you signed in {count === 1 ? "is" : "are"} only in this browser.{" "}
          <button type="button" disabled={busy} onClick={runImport} className="font-semibold text-ocean-cyan hover:underline disabled:opacity-60">
            {busy ? "Saving…" : "Save to account"}
          </button>
          {failed && <span className="text-no-go"> Couldn&apos;t save — try again.</span>}
        </span>
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-ocean-cyan/40 bg-shelf-3/80 p-2.5 text-[11px] text-ink-muted">
      <p className="flex items-start gap-1.5 text-ink">
        <CloudUpload className="mt-px size-3.5 shrink-0 text-ocean-cyan" aria-hidden="true" />
        <span>
          You have {chats} from before you signed in. Save {count === 1 ? "it" : "them"} to your account?
        </span>
      </p>
      {failed && <p className="mt-1 text-no-go">Couldn&apos;t save them — try again.</p>}
      <div className="mt-2 flex gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={runImport}
          className="rounded-md border border-ocean-cyan/50 bg-ocean-cyan px-2 py-1 font-bold text-on-accent hover:bg-ocean-cyan/90 disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save to account"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            try {
              localStorage.setItem(DISMISS_PREFIX + userId, "1");
            } catch {
              /* then it asks again in full next time */
            }
            setDismissed(true);
          }}
          className="rounded-md border border-hairline px-2 py-1 font-semibold hover:text-ink"
        >
          Not now
        </button>
      </div>
    </div>
  );
}

function StorageNote({ auth }: { auth: AuthState }) {
  if (auth.status === "loading") return null;
  if (auth.status === "signed_in") {
    return (
      <p className="flex items-center gap-1.5 border-t border-hairline/60 pt-2 text-[10px] text-ink-dim">
        <Cloud className="size-3 shrink-0 text-ocean-cyan" aria-hidden="true" />
        Saved to your account
      </p>
    );
  }
  return (
    <p className="flex items-start gap-1.5 border-t border-hairline/60 pt-2 text-[10px] leading-relaxed text-ink-dim">
      <HardDrive className="mt-px size-3 shrink-0" aria-hidden="true" />
      <span>
        Saved in this browser only (last {BROWSER_CHAT_LIMIT}).{" "}
        <Link href="/login?next=/ask" className="font-semibold text-ocean-cyan hover:underline">
          Sign in
        </Link>{" "}
        to keep chats on every device.
      </span>
    </p>
  );
}
