import { useCallback, useRef, useState } from "react";
import { ArrowUp, Paperclip, Loader2, Mic, Square } from "lucide-react";
import clsx from "clsx";
import { speechSupported, useSpeech } from "../hooks/useSpeech";

export default function Composer({
  onSend, onUpload, disabled, uploading, remaining, limit,
}: {
  onSend: (text: string) => void;
  onUpload: (file: File) => void;
  disabled: boolean;
  uploading: boolean;
  remaining: number;
  limit: number;
}) {
  const [value, setValue] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const handleTranscript = useCallback((text: string) => {
    setValue(text);
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.height = `${Math.min(taRef.current.scrollHeight, 160)}px`;
    }
  }, []);

  const speech = useSpeech(handleTranscript);
  const canSpeak = speechSupported();

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    if (speech.listening) speech.stop();
    onSend(text);
    setValue("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3.5">
      <div className="mx-auto max-w-3xl">
        {speech.listening && (
          <div className="mb-2 flex items-center justify-center gap-2 text-xs font-medium text-brand-text">
            <span className="flex h-2 w-2 animate-pulseSoft rounded-full bg-accent-red" />
            Listening — speak your question, then press the stop button
          </div>
        )}
        {speech.error && (
          <p className="mb-2 text-center text-xs text-accent-red">{speech.error}</p>
        )}

        <div className={clsx(
          "flex items-end gap-2 rounded-2xl border bg-surface px-3 py-2 shadow-soft",
          disabled ? "border-border opacity-60"
                   : speech.listening ? "border-accent-red shadow-focus"
                   : "border-border-strong focus-within:border-brand focus-within:shadow-focus",
        )}>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading || disabled}
            title="Upload a specification PDF"
            className="shrink-0 rounded-lg p-2 text-ink-faint hover:bg-surface-sunken hover:text-ink-muted disabled:opacity-40"
          >
            {uploading ? <Loader2 size={17} className="animate-spin text-brand" />
                       : <Paperclip size={17} />}
          </button>
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }} />

          <textarea
            ref={taRef} rows={1} value={value} disabled={disabled}
            placeholder={disabled ? "Question limit reached for this demo"
                                  : "Ask about the indexed specifications…"}
            onChange={(e) => {
              setValue(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-base text-ink placeholder:text-ink-faint focus:outline-none"
          />

          {canSpeak && (
            <button
              onClick={speech.toggle}
              disabled={disabled}
              title={speech.listening ? "Stop listening" : "Ask by voice"}
              className={clsx(
                "shrink-0 rounded-lg p-2 disabled:opacity-40",
                speech.listening
                  ? "bg-accent-redSoft text-accent-red"
                  : "text-ink-faint hover:bg-surface-sunken hover:text-ink-muted",
              )}
            >
              {speech.listening ? <Square size={16} fill="currentColor" /> : <Mic size={17} />}
            </button>
          )}

          <button
            onClick={submit}
            disabled={!value.trim() || disabled}
            className="shrink-0 rounded-lg bg-brand p-2 text-ink-inverse hover:bg-brand-hover disabled:bg-surface-sunken disabled:text-ink-faint"
          >
            <ArrowUp size={17} strokeWidth={2.5} />
          </button>
        </div>

        <p className="mt-2 text-center text-micro text-ink-faint">
          {remaining} of {limit} questions remaining · shared free-tier key ·
          attach a PDF or use the microphone
        </p>
      </div>
    </div>
  );
}
