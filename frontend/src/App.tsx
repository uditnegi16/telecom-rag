import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Radio } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Message from "./components/Message";
import Composer from "./components/Composer";
import Onboarding, { shouldShowOnboarding } from "./components/Onboarding";
import Tour, { shouldShowTour } from "./components/Tour";
import { api } from "./services/api";
import { uid } from "./utils/id";
import type {
  ConversationSummary, CorpusInfo, Message as Msg, StoredTurn,
} from "./types";

// Fallback only. The real limit is read from /health, because it is an
// environment variable on the server and hardcoding it here meant the counter
// lied whenever it was changed (as it was, from 8 to 12).
const DEFAULT_QUESTION_LIMIT = 8;
const LS_KEY = "telecomrag.conversation";

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  // Persisted so a page refresh resumes the conversation instead of silently
  // starting a new one (D-028).
  const [conversationId, setConversationId] = useState<string | null>(
    () => localStorage.getItem(LS_KEY),
  );
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [corpus, setCorpus] = useState<CorpusInfo | null>(null);
  const [questionLimit, setQuestionLimit] = useState(DEFAULT_QUESTION_LIMIT);
  const [remaining, setRemaining] = useState(DEFAULT_QUESTION_LIMIT);
  const [showOnboarding, setShowOnboarding] = useState(shouldShowOnboarding);
  const [showTour, setShowTour] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (cid?: string | null) => {
    // These were previously wrapped in bare catches, which hid a failing
    // conversation list entirely - the sidebar simply stayed empty with no
    // clue why. Non-fatal, but never silent.
    try {
      setCorpus(await api.corpus(cid ?? conversationId));
    } catch (e) {
      console.warn("corpus fetch failed", e);
    }
    try {
      setConversations(await api.conversations());
    } catch (e) {
      console.warn("conversation list failed", e);
    }
  }, [conversationId]);

  const toMessages = (turns: StoredTurn[]): Msg[] =>
    turns.map((t) => ({
      id: uid(),
      role: t.role,
      content: t.content,
      response: t.role === "assistant" ? {
        answer: t.content, claims: t.claims, citations: t.citations,
        sources: [],                       // bodies are reproducible from the index
        confidence: t.confidence ?? 0, abstained: t.abstained,
        abstain_reason: t.abstain_reason, claims_dropped: 0,
        latency_s: t.latency_s ?? 0, rewritten_query: t.rewritten_query,
        session_id: "", questions_remaining: null,
      } : undefined,
    }));

  // Restore the stored conversation on first load.
  useEffect(() => {
    (async () => {
      if (conversationId) {
        try {
          setMessages(toMessages(await api.conversation(conversationId)));
        } catch {
          localStorage.removeItem(LS_KEY);
          setConversationId(null);
        }
      }
      try {
        const h = await api.health();
        if (h.question_limit) {
          setQuestionLimit(h.question_limit);
          setRemaining((r) => (r === DEFAULT_QUESTION_LIMIT ? h.question_limit! : r));
        }
      } catch {
        /* fall back to the default */
      }
      refresh();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async (text: string) => {
    if (busy || remaining <= 0) return;
    setError(null);
    setBusy(true);

    const pendingId = uid();
    setMessages((m) => [
      ...m,
      { id: uid(), role: "user", content: text },
      { id: pendingId, role: "assistant", content: "", pending: true },
    ]);

    try {
      const res = await api.chat(text, conversationId);
      if (res.session_id !== conversationId) {
        setConversationId(res.session_id);
        localStorage.setItem(LS_KEY, res.session_id);
      }
      if (res.questions_remaining !== null) setRemaining(res.questions_remaining);
      setMessages((m) => m.map((msg) => msg.id === pendingId
        ? { ...msg, pending: false, content: res.answer ?? "", response: res }
        : msg));
      refresh(res.session_id);
    } catch (e) {
      setMessages((m) => m.filter((msg) => msg.id !== pendingId));
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      const res = await api.upload(file, conversationId);
      if (res.session_id !== conversationId) {
        setConversationId(res.session_id);
        localStorage.setItem(LS_KEY, res.session_id);
      }
      setMessages((m) => [...m, {
        id: uid(), role: "assistant", system: true,
        content:
          `Indexed ${res.spec_id} — ${res.chunks_added} clauses from ${res.pages} ` +
          `pages in ${res.seconds}s. It is searchable alongside the base corpus ` +
          `and visible only in this conversation.` +
          (res.warnings.length ? ` Note: ${res.warnings.join(" ")}` : ""),
      }]);
      refresh(res.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const newConversation = () => {
    setMessages([]);
    setConversationId(null);
    localStorage.removeItem(LS_KEY);
    // Refresh so the conversation just left appears under "Recent" - without
    // this it looks like the previous chat was destroyed rather than filed.
    refresh(null);
  };

  const openConversation = async (id: string) => {
    try {
      setMessages(toMessages(await api.conversation(id)));
      setConversationId(id);
      localStorage.setItem(LS_KEY, id);
      refresh(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open conversation.");
    }
  };

  const removeConversation = async (id: string) => {
    await api.deleteConversation(id).catch(() => undefined);
    if (id === conversationId) newConversation();
    else refresh();
  };

  return (
    <div className="flex h-screen bg-surface">
      {showOnboarding && (
        <Onboarding
          onClose={() => {
            setShowOnboarding(false);
            // The overview says WHAT; the tour shows WHERE. Running them in
            // sequence avoids two overlays competing for the same screen.
            if (shouldShowTour()) setTimeout(() => setShowTour(true), 250);
          }}
        />
      )}
      {showTour && <Tour onClose={() => setShowTour(false)} />}
      <Sidebar
        corpus={corpus} conversations={conversations} activeId={conversationId}
        onExample={send} onNew={newConversation} onOpen={openConversation}
        onDelete={removeConversation}
        onReplayTour={() => {
          try { localStorage.removeItem("telecomrag.tour"); } catch { /* noop */ }
          setShowTour(true);
        }}
        onClearDocs={async () => {
          if (conversationId) {
            await fetch(`/api/v1/session/${conversationId}/documents`,
              { method: "DELETE", credentials: "include" });
            refresh();
          }
        }}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-border px-4 py-3 lg:hidden">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand">
            <Radio size={13} className="text-ink-inverse" />
          </span>
          <span className="font-display text-sm font-bold text-ink">TelecomRAG</span>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-8">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 && (
              <div className="animate-fadeUp pt-16 text-center">
                <h2 className="font-display text-2xl text-ink">
                  Ask about 3GPP specifications
                </h2>
                <p className="mx-auto mt-4 max-w-lg text-base text-ink-muted">
                  Every claim is checked against the clause it cites before you
                  see it. When the corpus does not contain the answer, the system
                  declines rather than guessing — and shows what it retrieved
                  either way.
                </p>
                <p className="mx-auto mt-5 max-w-lg text-xs text-ink-faint">
                  Attach a PDF to query your own specification alongside the
                  indexed corpus.
                </p>
              </div>
            )}

            {messages.map((m) => <Message key={m.id} message={m} />)}

            {error && (
              <div className="flex animate-fadeUp items-start gap-2.5 rounded-xl border border-accent-red/25 bg-accent-redSoft px-4 py-3">
                <AlertCircle size={15} className="mt-0.5 shrink-0 text-accent-red" />
                <span className="text-sm text-ink">{error}</span>
              </div>
            )}

            <div ref={endRef} />
          </div>
        </div>

        <Composer onSend={send} onUpload={upload}
          disabled={busy || remaining <= 0} uploading={uploading}
          remaining={remaining} limit={questionLimit} />
      </main>
    </div>
  );
}
