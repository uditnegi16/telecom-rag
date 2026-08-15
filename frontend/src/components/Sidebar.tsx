import { Database, FileUp, Trash2, Radio, Plus, MessageSquare } from "lucide-react";
import clsx from "clsx";
import type { ConversationSummary, CorpusInfo } from "../types";

const EXAMPLES = [
  "What is the unit of measurement for the number of failed event exposure subscribe at the PCF?",
  "What does the Type field in a performance data file name indicate?",
  "How is the aggregated active session time for UEs in a cell measured?",
  "What are the steps of the X2 handover procedure in LTE?",
];

export default function Sidebar({
  corpus, conversations, activeId, onExample, onNew, onOpen, onDelete, onClearDocs,
  onReplayTour,
}: {
  corpus: CorpusInfo | null;
  conversations: ConversationSummary[];
  activeId: string | null;
  onExample: (q: string) => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onClearDocs: () => void;
  onReplayTour: () => void;
}) {
  return (
    <aside className="hidden w-[19rem] shrink-0 flex-col border-r border-border bg-surface-subtle lg:flex">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand">
            <Radio size={15} className="text-ink-inverse" />
          </span>
          <h1 className="font-display text-md font-bold text-ink">TelecomRAG</h1>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          Grounded question answering over 3GPP specifications. Every claim
          cites a clause; unsupported answers are refused.
        </p>
        <button onClick={onNew} data-tour="new-conversation"
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-border-strong bg-surface px-3 py-2 text-sm font-semibold text-ink shadow-soft hover:bg-surface-sunken">
          <Plus size={14} /> New conversation
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {conversations.length > 0 ? (
          <section className="mb-6">
            <div className="text-micro font-semibold uppercase tracking-wide text-ink-faint">
              Recent · {conversations.length}
            </div>
            <div className="mt-2 space-y-0.5">
              {conversations.map((c) => (
                <div key={c.id}
                  className={clsx("group flex items-center gap-1.5 rounded-lg px-2 py-1.5",
                    c.id === activeId ? "bg-brand-soft" : "hover:bg-surface-sunken")}>
                  <MessageSquare size={12}
                    className={c.id === activeId ? "text-brand" : "text-ink-faint"} />
                  <button onClick={() => onOpen(c.id)}
                    className={clsx("min-w-0 flex-1 truncate text-left text-xs",
                      c.id === activeId ? "font-semibold text-brand-text" : "text-ink-muted")}>
                    {c.title}
                  </button>
                  <button onClick={() => onDelete(c.id)}
                    className="shrink-0 rounded p-0.5 text-ink-faint opacity-0 hover:text-accent-red group-hover:opacity-100">
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <p className="mb-6 rounded-lg bg-surface-sunken px-3 py-2 text-micro leading-relaxed text-ink-faint">
            Conversations are saved automatically and listed here. Starting a
            new one files the current chat rather than deleting it.
          </p>
        )}

        <section data-tour="corpus">
          <div className="flex items-center gap-1.5 text-micro font-semibold uppercase tracking-wide text-ink-faint">
            <Database size={11} /> Indexed corpus
          </div>
          <div className="mt-2 space-y-1.5">
            {corpus ? Object.entries(corpus.specs).map(([spec, n]) => (
              <div key={spec}
                className="flex items-baseline justify-between rounded-lg border border-border bg-surface px-3 py-2 shadow-soft">
                <span className="font-mono text-xs font-medium text-ink">{spec}</span>
                <span className="font-mono text-micro text-ink-faint">{n}</span>
              </div>
            )) : <p className="text-xs text-ink-faint">Loading…</p>}
          </div>
          {corpus && (
            <p className="mt-2 text-micro leading-relaxed text-ink-faint">
              {corpus.total_chunks.toLocaleString()} clauses indexed. Questions
              outside these specifications are refused by design.
            </p>
          )}
        </section>

        {!!corpus?.user_documents?.length && (
          <section className="mt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-micro font-semibold uppercase tracking-wide text-ink-faint">
                <FileUp size={11} /> Your documents
              </div>
              <button onClick={onClearDocs} title="Remove uploaded documents"
                className="rounded p-1 text-ink-faint hover:text-accent-red">
                <Trash2 size={11} />
              </button>
            </div>
            <div className="mt-2 space-y-1.5">
              {corpus.user_documents.map((d) => (
                <div key={d}
                  className="rounded-lg border border-brand/25 bg-brand-soft px-3 py-2 font-mono text-xs text-brand-text">
                  {d}
                </div>
              ))}
            </div>
            <p className="mt-2 text-micro leading-relaxed text-ink-faint">
              Visible only in this conversation. Other visitors cannot retrieve
              from your uploads.
            </p>
          </section>
        )}

        <section className="mt-6" data-tour="examples">
          <div className="text-micro font-semibold uppercase tracking-wide text-ink-faint">
            Try
          </div>
          <div className="mt-2 space-y-1.5">
            {EXAMPLES.map((q, i) => (
              <button key={q} onClick={() => onExample(q)}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs leading-snug text-ink-muted shadow-soft hover:border-border-strong hover:text-ink">
                {q}
                {i === EXAMPLES.length - 1 && (
                  <span className="mt-1 block font-medium text-micro text-accent-amber">
                    not in corpus — should be refused
                  </span>
                )}
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-micro leading-relaxed text-ink-faint">
            Then try a follow-up like <em>“what about for the AMF?”</em> — it is
            rewritten into a standalone query before retrieval.
          </p>
        </section>
      </div>

      <div className="border-t border-border px-5 py-3">
        <button
          onClick={onReplayTour}
          className="mb-2 block text-micro text-ink-faint hover:text-brand-text"
        >
          Show me around again
        </button>
        <a href="https://github.com/uditnegi16/telecom-rag" target="_blank" rel="noreferrer"
          className="text-micro text-ink-faint hover:text-brand-text">
          Source, evaluation results and design docs on GitHub →
        </a>
      </div>
    </aside>
  );
}
