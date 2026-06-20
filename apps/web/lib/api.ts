export type DigestEvent = {
  id: number;
  title: string;
  issuing_body: string | null;
  jurisdiction: "central" | "state" | null;
  issue_date: string | null;
  event_type: "NEW" | "CHANGED" | "REPLACEMENT" | "DUPLICATE";
  topic_tags: string[];
  raw_summary: string | null;
  source_url: string;
  detected_at: string;
};

export type DigestResponse = {
  digest_date: string;
  event_count: number;
  events: DigestEvent[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getLatestDigest(token?: string) {
  return apiFetch<DigestResponse>("/digests/latest", token);
}
