import { useEffect, useState } from "react";
import {
  ShieldCheck, FileUp, AlertTriangle, Search, X, ArrowRight, Radio,
} from "lucide-react";
import clsx from "clsx";

/**
 * First-visit orientation.
 *
 * A visitor arriving cold sees a chat box and has to infer that the paperclip
 * indexes their own specifications, that refusals are deliberate rather than
 * failures, and that the evidence panel is the point of the whole interface.
 * Those are the three things most likely to be misread, so those are what
 * this explains.
 *
 * Dismissal is remembered in localStorage - an overlay that reappears on
 * every visit is worse than none at all.
 */

const LS_KEY = "telecomrag.onboarded";

const CARDS = [
  {
    icon: ShieldCheck,
    tone: "green" as const,
    title: "Every claim cites a clause",
    body:
      "Answers are assembled only from retrieved specification text, and each " +
      "claim is checked against the clause it cites before you see it. Claims " +
      "that fail that check are removed, and the response tells you how many.",
  },
  {
    icon: AlertTriangle,
    tone: "amber" as const,
    title: "It refuses rather than guessing",
    body:
      "When the indexed specifications do not support an answer, the system " +
      "declines. That is the designed behaviour, not a failure — and it shows " +
      "you what it retrieved so you can judge the refusal yourself.",
  },
  {
    icon: FileUp,
    tone: "brand" as const,
    title: "Bring your own specification",
    body:
      "Attach a PDF and it is parsed, chunked by clause and indexed in about " +
      "thirty seconds, then searchable alongside the base corpus. Uploads are " +
      "scoped to your conversation — no other visitor can retrieve from them.",
  },
  {
    icon: Search,
    tone: "slate" as const,
    title: "Follow-ups are rewritten, visibly",
    body:
      "Ask “what about for the AMF?” and it is expanded into a standalone " +
      "question before retrieval, because a fragment cannot be searched for. " +
      "The rewritten query is shown, so you can see what was actually asked.",
  },
];

const TONES = {
  green: "bg-accent-greenSoft text-accent-green",
  amber: "bg-accent-amberSoft text-accent-amber",
  brand: "bg-brand-soft text-brand",
  slate: "bg-surface-sunken text-ink-muted",
};

export function shouldShowOnboarding(): boolean {
  try {
    return localStorage.getItem(LS_KEY) !== "1";
  } catch {
    return true;      // private browsing with storage disabled
  }
}

export default function Onboarding({ onClose }: { onClose: () => void }) {
  const [closing, setClosing] = useState(false);

  const dismiss = () => {
    try {
      localStorage.setItem(LS_KEY, "1");
    } catch {
      /* storage unavailable - the overlay simply reappears next visit */
    }
    setClosing(true);
    setTimeout(onClose, 160);
  };

  // Escape closes it. An overlay you cannot dismiss with the keyboard is a
  // small accessibility failure that is trivial to avoid.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dismiss();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={clsx(
        "fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm",
        closing ? "opacity-0" : "animate-fadeIn",
      )}
      onClick={dismiss}
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-surface shadow-raised"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-border px-6 py-5">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand">
              <Radio size={18} className="text-ink-inverse" />
            </span>
            <div>
              <h2 id="onboarding-title" className="font-display text-lg text-ink">
                TelecomRAG
              </h2>
              <p className="mt-1 text-sm text-ink-muted">
                Grounded question answering over 3GPP specifications.
              </p>
            </div>
          </div>
          <button
            onClick={dismiss}
            aria-label="Close"
            className="rounded-lg p-1.5 text-ink-faint hover:bg-surface-sunken hover:text-ink-muted"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          {CARDS.map(({ icon: Icon, tone, title, body }) => (
            <div key={title} className="flex gap-3">
              <span
                className={clsx(
                  "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                  TONES[tone],
                )}
              >
                <Icon size={15} />
              </span>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-ink">{title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{body}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border px-6 py-4">
          <p className="text-micro leading-relaxed text-ink-faint">
            Runs on a shared free-tier API key, so questions are capped per
            visitor.
          </p>
          <button
            onClick={dismiss}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-ink-inverse hover:bg-brand-hover"
          >
            Start asking <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
