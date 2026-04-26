import type {
  AnalyzeResponse,
  BusinessProfile,
  NaicsResolution,
  QuoteCompareRequestPayload,
  QuoteCompareResponse,
  RiskoChatResponse,
  RiskoMessage,
} from "./types";

const API = "/api";

export async function analyzeBusiness(
  profile: BusinessProfile,
  policyText: string | null,
  useSamplePolicy: boolean,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${API}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile,
      policy_text: policyText || null,
      use_sample_policy: useSamplePolicy,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json() as Promise<AnalyzeResponse>;
}

export async function extractPdfText(file: File): Promise<string> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API}/upload-policy`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  const data = (await res.json()) as { text: string };
  return data.text;
}

export async function lookupNaics(code: string): Promise<NaicsResolution> {
  const q = encodeURIComponent(code.trim());
  const res = await fetch(`${API}/naics/lookup?code=${q}`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json() as Promise<NaicsResolution>;
}

export async function riskoChat(messages: RiskoMessage[]): Promise<RiskoChatResponse> {
  const res = await fetch(`${API}/risko/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    let err = await res.text();
    try {
      const j = JSON.parse(err) as { detail?: string };
      if (typeof j.detail === "string") err = j.detail;
    } catch {
      /* use raw */
    }
    throw new Error(err || res.statusText);
  }
  return res.json() as Promise<RiskoChatResponse>;
}

export type RagHistoryTurn = { role: "user" | "assistant"; content: string };

export async function ragHealth(): Promise<{
  ok?: boolean;
  indexed?: boolean;
  chunks?: number;
  pdfs_dirs?: string[];
  vector_dir?: string;
  ollama_model?: string;
  persona?: string;
  use_risko?: boolean;
  copilot?: Record<string, string>;
}> {
  const res = await fetch(`${API}/health`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{
    ok?: boolean;
    indexed?: boolean;
    chunks?: number;
    pdfs_dirs?: string[];
    vector_dir?: string;
    ollama_model?: string;
    persona?: string;
    use_risko?: boolean;
    copilot?: Record<string, string>;
  }>;
}

export async function ragIngest(): Promise<{ ok?: boolean; chunks?: number; detail?: unknown; message?: string }> {
  const res = await fetch(`${API}/ingest`, { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      typeof (data as { detail?: unknown }).detail === "string"
        ? (data as { detail: string }).detail
        : JSON.stringify((data as { detail?: unknown }).detail ?? data);
    throw new Error(msg || res.statusText);
  }
  return data as { ok?: boolean; chunks?: number };
}

/** Stream tokens from `POST /api/chat/stream` (FAISS + BM25 RAG). */
export async function ragChatStream(
  message: string,
  history: RagHistoryTurn[],
  onDelta: (token: string) => void,
): Promise<void> {
  const res = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : res.statusText);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (!payload) continue;
      try {
        const data = JSON.parse(payload) as { token?: string; done?: boolean; error?: string };
        if (data.error) throw new Error(data.error);
        if (data.token) onDelta(data.token);
        if (data.done) return;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

export async function submitQuoteCompare(body: QuoteCompareRequestPayload): Promise<QuoteCompareResponse> {
  const res = await fetch(`${API}/quotes/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let err = await res.text();
    try {
      const j = JSON.parse(err) as { detail?: string };
      if (typeof j.detail === "string") err = j.detail;
    } catch {
      /* use raw */
    }
    throw new Error(err || res.statusText);
  }
  return res.json() as Promise<QuoteCompareResponse>;
}
