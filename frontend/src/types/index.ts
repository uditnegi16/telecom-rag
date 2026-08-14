export type Role = "user" | "assistant";

export interface Claim { claim: string; citation: string; }

export interface Source {
  chunk_id: string; spec_id: string; spec_version: string;
  clause_id: string; clause_title: string; heading_path: string;
  page_start: number; page_end: number; reranker_score: number; body: string;
}

export interface ChatResponse {
  answer: string | null;
  claims: Claim[];
  citations: string[];
  sources: Source[];
  confidence: number;
  abstained: boolean;
  abstain_reason: string | null;
  claims_dropped: number;
  latency_s: number;
  rewritten_query: string | null;
  session_id: string;
  questions_remaining: number | null;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  response?: ChatResponse;
  pending?: boolean;
  system?: boolean;
}

export interface CorpusInfo {
  total_chunks: number;
  specs: Record<string, number>;
  user_documents?: string[];
}

export interface ConversationSummary {
  id: string; title: string; turns: number;
  created_at: number; updated_at: number;
}

export interface StoredTurn {
  role: Role; content: string;
  abstained: boolean; abstain_reason: string | null;
  confidence: number | null; rewritten_query: string | null;
  citations: string[]; claims: Claim[];
  latency_s: number | null; created_at: number;
}
