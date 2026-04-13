import type { SourceDraft, SourceType } from "../../types";
import { SourceInputItem } from "./SourceInputItem";

const OPTIONS: Array<{ type: SourceType; label: string }> = [
  { type: "web", label: "웹 페이지 URL" },
  { type: "confluence", label: "Confluence 페이지" },
  { type: "local_md", label: "로컬 MD 파일" },
];

interface SourceInputListProps {
  sources: SourceDraft[];
  onAdd: (type: SourceType) => void;
  onChange: (next: SourceDraft) => void;
  onRemove: (id: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export function SourceInputList({
  sources,
  onAdd,
  onChange,
  onRemove,
  onSubmit,
  isSubmitting,
}: SourceInputListProps) {
  const canSubmit = sources.some((source) => source.value.trim().length > 0) && !isSubmitting;

  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Phase 1 Ingest</p>
          <h2>소스 입력</h2>
        </div>
        <div className="add-row">
          {OPTIONS.map((option) => (
            <button
              key={option.type}
              className="tag-button"
              type="button"
              onClick={() => onAdd(option.type)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="source-list">
        {sources.map((source) => (
          <SourceInputItem
            key={source.id}
            source={source}
            onChange={onChange}
            onRemove={() => onRemove(source.id)}
          />
        ))}
      </div>

      <div className="panel__footer">
        <p className="helper-text">
          여러 소스를 순차로 처리합니다. Confluence URL은 `pages/page_id` 패턴에서 page_id를 자동 추출합니다.
        </p>
        <button className="primary-button" type="button" disabled={!canSubmit} onClick={onSubmit}>
          {isSubmitting ? "처리 중..." : "처리 시작"}
        </button>
      </div>
    </section>
  );
}
