import type { BatchResponse, CompareResponse, SourceDraft, SourceType, StageName } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";

function buildSourcePayload(source: SourceDraft) {
  if (source.type === "local_md") {
    return { type: source.type, path: source.value };
  }

  if (source.type === "confluence") {
    const match = source.value.match(/\/pages\/(\d+)/);
    return { type: source.type, url: source.value, page_id: match?.[1] ?? "" };
  }

  return { type: source.type, url: source.value };
}

export function getApiBase() {
  return API_BASE;
}

export async function fetchHealth(): Promise<{ status: string; timestamp: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ status: string; timestamp: string }>;
}

export async function startBatch(sources: SourceDraft[]): Promise<BatchResponse> {
  const response = await fetch(`${API_BASE}/ingest/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sources: sources.map(buildSourcePayload),
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<BatchResponse>;
}

export async function fetchCompare(sourceId: string, wikiPath: string): Promise<CompareResponse> {
  const query = new URLSearchParams({
    source_ids: sourceId,
    wiki_path: wikiPath,
  });
  const response = await fetch(`${API_BASE}/compare?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<CompareResponse>;
}

export async function uploadLocalFile(file: File): Promise<{ path: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/upload/local`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ path: string; filename: string }>;
}

export async function fetchMarkdownFile(path: string): Promise<string> {
  const query = new URLSearchParams({ path });
  const response = await fetch(`${API_BASE}/files/content?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = (await response.json()) as { content: string };
  return payload.content;
}

export function createStreamUrl(batchId: string) {
  return `${API_BASE}/ingest/batch/${batchId}/stream`;
}

export function getArtifactPath(sourceType: SourceType, sourceId: string, stage: StageName) {
  if (stage === "normalizer") {
    const directory = sourceType === "local_md" ? "local" : sourceType;
    return `output/normalizer/${directory}/${sourceId}.md`;
  }

  if (stage === "fetcher" && sourceType === "local_md") {
    return `output/fetcher/local/${sourceId}.md`;
  }

  return null;
}
