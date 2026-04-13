import type { SourceRuntime, StageName } from "../../types";
import { ArtifactPreview } from "./ArtifactPreview";
import { BatchProgress } from "./BatchProgress";
import { PipelineFlow } from "./PipelineFlow";

interface WorkflowModalProps {
  isOpen: boolean;
  total: number;
  runtimes: SourceRuntime[];
  selectedSourceId: string | null;
  selectedStage: StageName;
  previewTitle: string;
  previewContent: string;
  previewError: string;
  onClose: () => void;
  onSelectSource: (sourceId: string) => void;
  onSelectStage: (stage: StageName) => void;
}

export function WorkflowModal({
  isOpen,
  total,
  runtimes,
  selectedSourceId,
  selectedStage,
  previewTitle,
  previewContent,
  previewError,
  onClose,
  onSelectSource,
  onSelectStage,
}: WorkflowModalProps) {
  if (!isOpen) {
    return null;
  }

  const completed = runtimes.filter((runtime) => runtime.status === "done" || runtime.status === "error").length;
  const selectedRuntime = runtimes.find((runtime) => runtime.sourceId === selectedSourceId) ?? runtimes[0] ?? null;
  const currentLabel = selectedRuntime
    ? `${selectedRuntime.sourceType} · ${selectedRuntime.sourceValue}`
    : "배치 대기 중";

  return (
    <div className="modal-shell">
      <div className="modal-card">
        <div className="modal-card__header">
          <div>
            <p className="eyebrow">Workflow Stream</p>
            <h2>처리 현황</h2>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            닫기
          </button>
        </div>

        <BatchProgress total={total} completed={completed} currentLabel={currentLabel} />

        <div className="source-tabs">
          {runtimes.map((runtime) => (
            <button
              key={runtime.sourceId}
              type="button"
              className={`source-tab${runtime.sourceId === selectedRuntime?.sourceId ? " source-tab--active" : ""}`}
              onClick={() => onSelectSource(runtime.sourceId)}
            >
              <strong>{runtime.sourceType}</strong>
              <span>{runtime.status}</span>
            </button>
          ))}
        </div>

        <PipelineFlow runtime={selectedRuntime} onSelectStage={onSelectStage} />

        <div className="helper-row">
          <span>선택 단계: {selectedStage}</span>
          {selectedRuntime?.error ? <span className="status-pill status-pill--error">{selectedRuntime.error}</span> : null}
        </div>

        <ArtifactPreview title={previewTitle} content={previewContent} error={previewError} />
      </div>
    </div>
  );
}
