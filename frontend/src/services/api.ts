import type {
  ChatResponse, ConversationSummary, CorpusInfo, StoredTurn,
} from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

// A request that never resolves leaves the UI spinning forever. Every call
// gets a ceiling; the backend's own pipeline budget is 75s, so 120s here is
// the outer bound (ERROR_LOG E-017).
const TIMEOUT_MS = 120_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      credentials: "include",
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON */ }
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(
        "The request took too long. The shared free-tier API key is likely " +
        "rate limited — please try again in a moment.",
      );
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  chat: (question: string, sessionId: string | null) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    }),

  corpus: (sessionId?: string | null) =>
    request<CorpusInfo>(`/corpus${sessionId ? `?session_id=${sessionId}` : ""}`),

  conversations: () => request<ConversationSummary[]>("/conversations"),

  conversation: (id: string) => request<StoredTurn[]>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<{ deleted: string }>(`/conversations/${id}`, { method: "DELETE" }),

  upload: (file: File, sessionId: string | null) => {
    const form = new FormData();
    form.append("file", file);
    if (sessionId) form.append("session_id", sessionId);
    return request<{
      spec_id: string; spec_version: string; pages: number;
      chunks_added: number; seconds: number; warnings: string[];
      session_id: string;
    }>("/upload", { method: "POST", body: form });
  },
};
