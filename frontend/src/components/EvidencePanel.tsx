import { useState } from "react";
import { ChevronDown, FileText, Check } from "lucide-react";
import clsx from "clsx";
import type { Source } from "../types";

/**
 * The evidence panel is the point of the interface.
 *
 * An answer without its source is a claim you have to trust. With the clause
 * text one click away, a reviewer can falsify any statement in seconds
 * without opening a 400-page specification. Cited passages are marked and
 * open by default; retrieved-but-uncited ones stay collapsed, so you can
 * also see what the model chose not to use.
 */
export default function EvidencePanel({
  sources, citations,
}: { sources: Source[]; citations: string[] }) {
  const [open, setOpen] = useState<string | null>(
    sources.find((s) => citations.includes(s.chunk_id))?.chunk_id ?? null,
  );
  if (!sources.length) return null;

  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-border bg-surface-subtle">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <FileText size={13} className="text-ink-faint" />
        <span className="text-xs font-semibold text-ink-muted">
          Retrieved evidence · {sources.length} clause{sources.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="divide-y divide-border">
        {sources.map((s) => {
          const cited = citations.includes(s.chunk_id);
          const isOpen = open === s.chunk_id;
          return (
            <div key={s.chunk_id} className={clsx(cited && "bg-brand-softer")}>
              <button
                onClick={() => setOpen(isOpen ? null : s.chunk_id)}
                className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-sunken/60"
              >
                <ChevronDown
                  size={14}
                  className={clsx("mt-0.5 shrink-0 text-ink-faint transition-transform",
                    isOpen && "rotate-180")}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-medium text-ink">
                      {s.spec_id} {s.spec_version}
                    </span>
                    <span className="rounded-md bg-surface-sunken px-1.5 py-0.5 font-mono text-micro text-ink-muted">
                      clause {s.clause_id}
                    </span>
                    {cited && (
                      <span className="flex items-center gap-1 rounded-md bg-accent-greenSoft px-1.5 py-0.5 text-micro font-semibold text-accent-green">
                        <Check size={9} strokeWidth={3} /> CITED
                      </span>
                    )}
                    <span className="ml-auto font-mono text-micro text-ink-faint">
                      {s.reranker_score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-ink-muted">
                    {s.clause_title || s.heading_path}
                  </p>
                </div>
              </button>

              {isOpen && (
                <div className="animate-fadeIn px-4 pb-4 pl-11">
                  <p className="mb-2 text-micro leading-relaxed text-ink-faint">
                    {s.heading_path}
                  </p>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-ink-muted">
                    {s.body}
                  </pre>
                  <p className="mt-2 font-mono text-micro text-ink-faint">
                    pages {s.page_start}–{s.page_end} · {s.chunk_id}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
