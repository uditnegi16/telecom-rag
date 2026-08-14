import { AlertTriangle, Search, ShieldCheck, Info } from "lucide-react";
import ReactMarkdown from "react-markdown";
import EvidencePanel from "./EvidencePanel";
import type { Message as Msg } from "../types";

/** Shared markdown renderer.
 *  Answers cite clauses and the conversational replies use bold and lists;
 *  rendering them as plain text showed literal asterisks to the user. */
function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-ink">{children}</strong>
        ),
        em: ({ children }) => <em className="text-ink-muted">{children}</em>,
        code: ({ children }) => (
          <code className="rounded bg-surface-sunken px-1 py-0.5 font-mono text-xs">
            {children}
          </code>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer"
             className="text-brand-text underline">{children}</a>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 py-1 text-sm text-ink-faint">
      <span className="flex gap-1">
        <span className="dot h-1.5 w-1.5 rounded-full bg-brand" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-brand" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-brand" />
      </span>
      <span>Retrieving · generating · verifying</span>
    </div>
  );
}

export default function Message({ message }: { message: Msg }) {
  const r = message.response;

  if (message.role === "user") {
    return (
      <div className="flex animate-fadeUp justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-base text-ink-inverse shadow-soft">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.system) {
    return (
      <div className="flex animate-fadeUp items-start gap-2.5 rounded-xl border border-brand/20 bg-brand-soft px-4 py-3">
        <Info size={15} className="mt-0.5 shrink-0 text-brand" />
        <div className="prose-telecom text-sm text-brand-text">
          <Markdown>{message.content}</Markdown>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[92%] animate-fadeUp">
      {message.pending && <Thinking />}

      {r?.rewritten_query && (
        <div className="mb-2.5 flex items-start gap-1.5 rounded-lg bg-surface-subtle px-3 py-1.5 text-xs text-ink-muted">
          <Search size={11} className="mt-0.5 shrink-0 text-ink-faint" />
          <span>
            Interpreted as <em className="not-italic font-medium text-ink">{r.rewritten_query}</em>
          </span>
        </div>
      )}

      {r?.abstained ? (
        <div className="rounded-xl border border-accent-amber/25 bg-accent-amberSoft px-4 py-3.5">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-accent-amber" />
            <div>
              <div className="prose-telecom text-base text-ink">
                <Markdown>{r.answer ?? ""}</Markdown>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-ink-muted">
                The system is fail-closed: without sufficient supporting evidence
                it declines rather than producing a plausible guess. The passages
                it retrieved are below, so you can judge the refusal yourself.
              </p>
            </div>
          </div>
        </div>
      ) : (
        r && (
          <>
            <div className="prose-telecom text-base text-ink">
              <Markdown>{r.answer ?? ""}</Markdown>
            </div>

            {r.claims.length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-1.5 text-micro font-semibold uppercase tracking-wide text-ink-muted">
                  <ShieldCheck size={12} className="text-accent-green" />
                  Verified claims
                </div>
                <div className="mt-2 space-y-1.5">
                  {r.claims.map((c, i) => (
                    <div key={i}
                      className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-subtle px-3 py-2">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent-green" />
                      <span className="flex-1 text-sm text-ink">{c.claim}</span>
                      <code className="shrink-0 rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-micro text-ink-muted">
                        {c.citation}
                      </code>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )
      )}

      {r && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-micro text-ink-faint">
          <span>confidence {r.confidence.toFixed(3)}</span>
          {r.claims_dropped > 0 && (
            <span className="text-accent-amber">
              {r.claims_dropped} unsupported claim{r.claims_dropped === 1 ? "" : "s"} removed
            </span>
          )}
          <span>{r.latency_s.toFixed(1)}s</span>
          {r.abstain_reason && <span>{r.abstain_reason}</span>}
        </div>
      )}

      {r && <EvidencePanel sources={r.sources} citations={r.citations} />}
    </div>
  );
}
