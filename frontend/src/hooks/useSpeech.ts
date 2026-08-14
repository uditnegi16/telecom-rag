import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Voice input via the Web Speech API.
 *
 * Browser-native, so it costs nothing on the server and adds no latency to
 * the pipeline - the transcript is just text typed for you. Chrome and Edge
 * support it; Safari and Firefox largely do not, so the button hides itself
 * rather than offering something that will not work.
 *
 * `interimResults` is on so words appear as they are spoken. Without it there
 * is a disconcerting silence and people repeat themselves.
 */

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
};

function getRecognition(): SpeechRecognitionLike | null {
  const w = window as any;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? (new Ctor() as SpeechRecognitionLike) : null;
}

export const speechSupported = (): boolean => {
  const w = window as any;
  const hasApi = Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
  // Speech recognition requires a SECURE CONTEXT. On plain HTTP the
  // constructor may exist but microphone access is refused, so the button
  // would appear and then fail (same root cause as E-032). Hide it instead.
  return hasApi && window.isSecureContext;
};

export function useSpeech(onTranscript: (text: string, final: boolean) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const finalRef = useRef("");

  useEffect(() => () => { recRef.current?.stop(); }, []);

  const stop = useCallback(() => {
    recRef.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    setError(null);
    const rec = getRecognition();
    if (!rec) {
      setError("Voice input is not supported in this browser. Try Chrome or Edge.");
      return;
    }

    rec.continuous = true;
    rec.interimResults = true;
    // Indian English: telecom acronyms transcribe better than with en-US.
    rec.lang = "en-IN";
    finalRef.current = "";

    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const chunk = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalRef.current += chunk;
        else interim += chunk;
      }
      onTranscript((finalRef.current + interim).trim(), false);
    };

    rec.onerror = (e: any) => {
      const code = e?.error ?? "unknown";
      setError(
        code === "not-allowed"
          ? "Microphone access was blocked. Allow it in your browser settings."
          : code === "no-speech"
            ? "No speech detected."
            : `Voice input failed (${code}).`,
      );
      setListening(false);
    };

    rec.onend = () => {
      setListening(false);
      const text = finalRef.current.trim();
      if (text) onTranscript(text, true);
    };

    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setError("Could not start voice input.");
    }
  }, [onTranscript]);

  return { listening, error, start, stop, toggle: () => (listening ? stop() : start()) };
}
