import { startTransition, useEffect, useMemo, useState } from "react";

import {
  createStreamUrl,
  fetchCompare,
  fetchHealth,
  fetchMarkdownFile,
  getApiBase,
  getArtifactPath,
  startBatch,
} from "../lib/api";
import { ResultView } from "../components/ResultView/ResultView";
import { SourceInputList } from "../components/SourceInput/SourceInputList";
import { WorkflowModal } from "../components/WorkflowModal/WorkflowModal";
import type {
  SourceDraft,
  SourceRuntime,
  SourceType,
  StageName,
  StageStatus,
  CompareResponse,
  SourceDoneEvent,
  SourceStartEvent,
  StageUpdateEvent,
} from "../types";

const EMPTY_PIPELINE = {
  fetcher: "pending",
  normalizer: "pending",
  ingest: "pending",
  index_log: "pending",
} as const;

function createSource(type: SourceType): SourceDraft {
  return {
    id: crypto.randomUUID(),
    type,
    value: "",
  };
}

function createRuntime(sourceId: string, sourceType: SourceType, sourceValue: string): SourceRuntime {
  return {
    sourceId,
    sourceType,
    sourceValue,
    stages: { ...EMPTY_PIPELINE },
    elapsedMs: {},
    error: "",
    createdWikiPages: [],
    updatedWikiPages: [],
    status: "pending",
  };
}

export function IngestPage() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [backendMessage, setBackendMessage] = useState("백엔드 상태 확인 중");
  const [sources, setSources] = useState<SourceDraft[]>([createSource("web")]);
  const [runtimes, setRuntimes] = useState<SourceRuntime[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isWorkflowOpen, setIsWorkflowOpen] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<StageName>("fetcher");
  const [previewContent, setPreviewContent] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [isCompareLoading, setIsCompareLoading] = useState(false);

  const selectedRuntime = runtimes.find((runtime) => runtime.sourceId === selectedSourceId) ?? null;
  const previewTitle = selectedRuntime
    ? `${selectedRuntime.sourceType} · ${selectedStage}`
    : "산출물 미리보기";

  async function checkBackendHealth() {
    setBackendStatus("checking");
    setBackendMessage("백엔드 상태 확인 중");
    try {
      const health = await fetchHealth();
      setBackendStatus(health.status === "ok" ? "connected" : "disconnected");
      setBackendMessage(health.status === "ok" ? "백엔드 연결됨" : "백엔드 응답 이상");
    } catch {
      setBackendStatus("disconnected");
      setBackendMessage("백엔드 연결 실패");
    }
  }

  function openAnthropicBilling() {
    window.open("https://console.anthropic.com/settings/billing", "_blank", "noopener,noreferrer");
  }

  useEffect(() => {
    void checkBackendHealth();
  }, []);

  useEffect(() => {
    if (!selectedRuntime) {
      setPreviewContent("");
      setPreviewError("");
      return;
    }

    const selectedStageStatus = selectedRuntime.stages[selectedStage];
    if (selectedStageStatus !== "done") {
      setPreviewContent("");
      if (selectedStage === "ingest" || selectedStage === "index_log") {
        setPreviewError("현재 단계는 markdown 미리보기를 제공하지 않습니다.");
      } else if (selectedStageStatus === "error") {
        setPreviewError("이 단계는 오류로 종료되어 산출물을 불러올 수 없습니다.");
      } else {
        setPreviewError("이 단계의 산출물이 아직 준비되지 않았습니다.");
      }
      return;
    }

    const artifactPath = getArtifactPath(selectedRuntime.sourceType, selectedRuntime.sourceId, selectedStage);
    if (!artifactPath) {
      setPreviewContent("");
      setPreviewError("현재 단계는 markdown 미리보기를 제공하지 않습니다.");
      return;
    }

    let cancelled = false;
    fetchMarkdownFile(artifactPath)
      .then((content) => {
        if (!cancelled) {
          setPreviewContent(content);
          setPreviewError("");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setPreviewContent("");
          setPreviewError(error instanceof Error ? error.message : "산출물 미리보기를 불러오지 못했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRuntime, selectedStage]);

  const selectedWikiPath = useMemo(() => {
    if (!selectedRuntime) {
      return "";
    }
    return selectedRuntime.createdWikiPages[0] ?? selectedRuntime.updatedWikiPages[0] ?? "";
  }, [selectedRuntime]);

  const resultEmptyMessage = useMemo(() => {
    if (!selectedRuntime) {
      return "결과를 보려면 소스를 먼저 처리하세요.";
    }
    if (selectedRuntime.status === "error") {
      return selectedRuntime.error || "이번 소스는 처리 중 오류가 발생해 비교 결과를 만들지 못했습니다.";
    }
    if (!selectedWikiPath) {
      return "이번 소스는 새로 생성되거나 갱신된 wiki 페이지가 없어 비교할 대상이 없습니다.";
    }
    return "비교 결과를 불러오지 못했습니다.";
  }, [selectedRuntime, selectedWikiPath]);

  useEffect(() => {
    if (!selectedSourceId || !selectedWikiPath) {
      setCompareData(null);
      return;
    }

    let cancelled = false;
    setIsCompareLoading(true);
    fetchCompare(selectedSourceId, selectedWikiPath)
      .then((data) => {
        if (!cancelled) {
          setCompareData(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCompareData(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsCompareLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSourceId, selectedWikiPath]);

  function updateRuntime(sourceId: string, updater: (runtime: SourceRuntime) => SourceRuntime) {
    startTransition(() => {
      setRuntimes((current) => current.map((runtime) => (runtime.sourceId === sourceId ? updater(runtime) : runtime)));
    });
  }

  async function handleStartBatch() {
    const activeSources = sources.filter((source) => source.value.trim().length > 0);
    if (activeSources.length === 0) {
      return;
    }

    setIsSubmitting(true);
    setIsWorkflowOpen(true);
    setCompareData(null);

    try {
      const batch = await startBatch(activeSources);
      const nextRuntimes = batch.source_ids.map((sourceId, index) =>
        createRuntime(sourceId, activeSources[index].type, activeSources[index].value),
      );
      setRuntimes(nextRuntimes);
      setSelectedSourceId(batch.source_ids[0] ?? null);

      const eventSource = new EventSource(createStreamUrl(batch.batch_id));

      eventSource.addEventListener("source_start", (event) => {
        const payload = JSON.parse((event as MessageEvent<string>).data) as SourceStartEvent;
        updateRuntime(payload.source_id, (runtime) => ({
          ...runtime,
          status: "running",
        }));
        setSelectedSourceId(payload.source_id);
      });

      eventSource.addEventListener("stage_update", (event) => {
        const payload = JSON.parse((event as MessageEvent<string>).data) as StageUpdateEvent;
        if (payload.stage === "unknown") {
          updateRuntime(payload.source_id, (runtime) => ({
            ...runtime,
            status: "error",
            error: payload.error ?? runtime.error,
          }));
          return;
        }

        updateRuntime(payload.source_id, (runtime) => ({
          ...runtime,
          status: payload.status === "error" ? "error" : runtime.status === "done" ? "done" : "running",
          stages: {
            ...runtime.stages,
            [payload.stage]: payload.status as StageStatus,
          },
          elapsedMs: {
            ...runtime.elapsedMs,
            [payload.stage]: payload.elapsed_ms,
          },
          error: payload.error ?? runtime.error,
        }));
      });

      eventSource.addEventListener("source_done", (event) => {
        const payload = JSON.parse((event as MessageEvent<string>).data) as SourceDoneEvent;
        updateRuntime(payload.source_id, (runtime) => ({
          ...runtime,
          createdWikiPages: payload.created_wiki_pages,
          updatedWikiPages: payload.updated_wiki_pages,
          error: payload.error ?? "",
          status: payload.status,
        }));
      });

      eventSource.addEventListener("batch_done", () => {
        setIsSubmitting(false);
        eventSource.close();
      });

      eventSource.onerror = () => {
        eventSource.close();
        setIsSubmitting(false);
      };
    } catch (error) {
      setIsSubmitting(false);
      setPreviewContent("");
      setPreviewError(error instanceof Error ? error.message : "배치 요청을 시작하지 못했습니다.");
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero__copy">
          <p className="eyebrow">Project Wiki Manager</p>
          <h1>소스를 넣으면, wiki가 스스로 구조를 잡게 만듭니다.</h1>
          <p className="hero__body">
            배치 ingest, 실시간 파이프라인 추적, source-to-wiki 비교까지 한 화면에서 확인할 수 있는
            Phase 1 프론트엔드입니다.
          </p>
        </div>
        <div className="hero__meta">
          <div className="hero__meta-top">
            <span>API Base</span>
            <div className="hero__meta-actions">
              <button className="ghost-button ghost-button--small" type="button" onClick={openAnthropicBilling}>
                Claude 잔액 확인
              </button>
              <button className="ghost-button ghost-button--small" type="button" onClick={checkBackendHealth}>
                새로고침
              </button>
            </div>
          </div>
          <strong>{getApiBase()}</strong>
          <div className={`status-badge status-badge--${backendStatus}`}>
            <span className="status-badge__dot" />
            <span>{backendMessage}</span>
          </div>
        </div>
      </section>

      <SourceInputList
        sources={sources}
        isSubmitting={isSubmitting}
        onAdd={(type) => setSources((current) => [...current, createSource(type)])}
        onChange={(next) => setSources((current) => current.map((source) => (source.id === next.id ? next : source)))}
        onRemove={(id) => setSources((current) => current.filter((source) => source.id !== id))}
        onSubmit={handleStartBatch}
      />

      <ResultView
        runtimes={runtimes}
        activeSourceId={selectedSourceId}
        onSelectSource={setSelectedSourceId}
        onOpenWorkflow={() => setIsWorkflowOpen(true)}
        compareData={compareData}
        isLoading={isCompareLoading}
        emptyMessage={resultEmptyMessage}
      />

      <WorkflowModal
        isOpen={isWorkflowOpen}
        total={runtimes.length}
        runtimes={runtimes}
        selectedSourceId={selectedSourceId}
        selectedStage={selectedStage}
        previewTitle={previewTitle}
        previewContent={previewContent}
        previewError={previewError}
        onClose={() => setIsWorkflowOpen(false)}
        onSelectSource={setSelectedSourceId}
        onSelectStage={setSelectedStage}
      />
    </main>
  );
}
