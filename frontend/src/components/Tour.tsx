import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import clsx from "clsx";

/**
 * Spotlight tour pointing at real controls.
 *
 * The static overview explains WHAT the system does; this shows WHERE. It
 * targets elements by `data-tour` attribute and measures their position at
 * runtime, so it cannot drift out of sync with the layout the way
 * hard-coded coordinates would.
 *
 * Targets that are not on screen are SKIPPED rather than pointed at blindly -
 * the sidebar is hidden below the `lg` breakpoint, so on a phone the sidebar
 * steps simply do not appear (E-033 would have been: a tooltip anchored to
 * nothing, floating in the corner).
 */

const LS_KEY = "telecomrag.tour";

interface Step {
  target: string;
  title: string;
  body: string;
  placement: "right" | "top" | "bottom";
}

const STEPS: Step[] = [
  {
    target: "new-conversation",
    title: "Start a new conversation",
    body:
      "Conversations are saved automatically and listed below this button. " +
      "Starting a new one files the current chat rather than deleting it.",
    placement: "right",
  },
  {
    target: "corpus",
    title: "What the assistant can answer from",
    body:
      "The indexed specifications and their clause counts. Anything outside " +
      "these is declined by design — so this panel tells you, in advance, " +
      "which questions will get an answer.",
    placement: "right",
  },
  {
    target: "examples",
    title: "Example questions",
    body:
      "Click any of these to try it. The last one is deliberately outside " +
      "the corpus, so you can see a refusal and the evidence behind it.",
    placement: "right",
  },
  {
    target: "upload",
    title: "Add your own specification",
    body:
      "Attach a PDF and it is parsed, split by clause and indexed in about " +
      "thirty seconds, then searchable alongside the base corpus. It stays " +
      "scoped to your conversation.",
    placement: "top",
  },
  {
    target: "mic",
    title: "Ask by voice",
    body:
      "Speak your question instead of typing. Words appear as you talk; " +
      "press stop when you are done.",
    placement: "top",
  },
  {
    target: "composer",
    title: "Ask anything here",
    body:
      "Every answer arrives with the clause it came from, and the passages " +
      "it was drawn from are one click away underneath.",
    placement: "top",
  },
];

export function shouldShowTour(): boolean {
  try {
    return localStorage.getItem(LS_KEY) !== "1";
  } catch {
    return false;
  }
}

interface Rect { top: number; left: number; width: number; height: number; }

function measure(target: string): Rect | null {
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  // Zero-sized means hidden (e.g. the sidebar below the lg breakpoint).
  if (r.width === 0 || r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

export default function Tour({ onClose }: { onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);

  // Only steps whose target is actually on screen.
  const [steps] = useState<Step[]>(() =>
    STEPS.filter((s) => measure(s.target) !== null),
  );

  const finish = useCallback(() => {
    try {
      localStorage.setItem(LS_KEY, "1");
    } catch {
      /* storage unavailable */
    }
    onClose();
  }, [onClose]);

  useLayoutEffect(() => {
    if (index >= steps.length) {
      finish();
      return;
    }
    setRect(measure(steps[index].target));
  }, [index, steps, finish]);

  useEffect(() => {
    const onResize = () => {
      if (index < steps.length) setRect(measure(steps[index].target));
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      if (e.key === "Enter" || e.key === "ArrowRight") setIndex((i) => i + 1);
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
    };
  }, [index, steps, finish]);

  if (index >= steps.length || !rect) return null;

  const step = steps[index];
  const pad = 8;
  const tipW = 300;

  // Position the tooltip beside the highlighted element, clamped to viewport.
  let tipTop = rect.top;
  let tipLeft = rect.left + rect.width + 16;

  if (step.placement === "top") {
    tipTop = rect.top - 16;
    tipLeft = rect.left + rect.width / 2 - tipW / 2;
  } else if (step.placement === "bottom") {
    tipTop = rect.top + rect.height + 16;
    tipLeft = rect.left + rect.width / 2 - tipW / 2;
  }

  tipLeft = Math.max(12, Math.min(tipLeft, window.innerWidth - tipW - 12));
  const tipStyle: React.CSSProperties =
    step.placement === "top"
      ? { left: tipLeft, bottom: window.innerHeight - tipTop, width: tipW }
      : { left: tipLeft, top: Math.max(12, tipTop), width: tipW };

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true">
      {/* Dim everything, then punch a hole over the target using a huge
          outline rather than four separate overlay rectangles. */}
      <div className="absolute inset-0 animate-fadeIn" onClick={finish}>
        <div
          className="absolute rounded-xl transition-all duration-300"
          style={{
            top: rect.top - pad,
            left: rect.left - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            boxShadow: "0 0 0 9999px rgba(18,20,28,0.55)",
            outline: "2px solid #2454E0",
            outlineOffset: "2px",
          }}
        />
      </div>

      <div
        className="absolute animate-fadeUp rounded-xl border border-border bg-surface p-4 shadow-raised"
        style={tipStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">{step.title}</h3>
          <button
            onClick={finish}
            aria-label="Skip tour"
            className="-mr-1 -mt-1 rounded p-1 text-ink-faint hover:bg-surface-sunken hover:text-ink-muted"
          >
            <X size={13} />
          </button>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">{step.body}</p>

        <div className="mt-3.5 flex items-center justify-between">
          <div className="flex gap-1">
            {steps.map((_, i) => (
              <span
                key={i}
                className={clsx(
                  "h-1 rounded-full transition-all",
                  i === index ? "w-4 bg-brand" : "w-1 bg-border-strong",
                )}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={finish}
              className="text-micro font-medium text-ink-faint hover:text-ink-muted"
            >
              Skip
            </button>
            <button
              onClick={() => setIndex((i) => i + 1)}
              className="flex items-center gap-1 rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-ink-inverse hover:bg-brand-hover"
            >
              {index === steps.length - 1 ? "Done" : "Next"}
              {index < steps.length - 1 && <ArrowRight size={12} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
