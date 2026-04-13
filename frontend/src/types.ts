export type SourceType = "web" | "confluence" | "local_md";
export type StageStatus = "pending" | "running" | "done" | "error";
export type StageName = "fetcher" | "normalizer" | "ingest" | "index_log";

export interface SourceDraft {
  id: string;
  type: SourceType;
  value: string;
}

export interface BatchResponse {
  batch_id: string;
  source_ids: string[];
  total: number;
}

export interface StageUpdateEvent {
  source_id: string;
  stage: StageName | "unknown";
  status: StageStatus;
  elapsed_ms: number;
  error?: string;
}

export interface SourceDoneEvent {
  source_id: string;
  index: number;
  total: number;
  status: "done" | "error";
  created_wiki_pages: string[];
  updated_wiki_pages: string[];
  error?: string;
}

export interface SourceStartEvent {
  source_id: string;
  index: number;
  total: number;
  source_type: SourceType;
  url: string;
}

export interface CompareMapping {
  source_paragraph_index: number;
  source_text_preview: string;
  wiki_page: string | null;
  wiki_section: string | null;
  action: string;
}

export interface CompareSource {
  source_id: string;
  content: string;
  mappings: CompareMapping[];
}

export interface CompareResponse {
  wiki_page: {
    path: string;
    content: string;
    sources: string[];
  };
  sources: CompareSource[];
}

export interface PipelineState {
  fetcher: StageStatus;
  normalizer: StageStatus;
  ingest: StageStatus;
  index_log: StageStatus;
}

export interface SourceRuntime {
  sourceId: string;
  sourceType: SourceType;
  sourceValue: string;
  stages: PipelineState;
  elapsedMs: Partial<Record<StageName, number>>;
  error: string;
  createdWikiPages: string[];
  updatedWikiPages: string[];
  status: "pending" | "running" | "done" | "error";
}
