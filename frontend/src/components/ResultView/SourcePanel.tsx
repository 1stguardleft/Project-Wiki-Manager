import type { CompareSource } from "../../types";

interface SourcePanelProps {
  source: CompareSource | null;
  selectedIndex: number | null;
  onSelectIndex: (index: number) => void;
}

export function SourcePanel({ source, selectedIndex, onSelectIndex }: SourcePanelProps) {
  if (!source) {
    return <div className="empty-state">비교할 소스를 선택하면 normalized markdown을 보여줍니다.</div>;
  }

  const paragraphs = source.content.split(/\n{2,}/).filter((paragraph) => paragraph.trim().length > 0);
  const mappingByIndex = new Map(source.mappings.map((mapping) => [mapping.source_paragraph_index, mapping]));

  return (
    <div className="result-panel">
      <div className="result-panel__header">
        <h3>원본 소스</h3>
        <span>{source.source_id}</span>
      </div>
      <div className="paragraph-list">
        {paragraphs.map((paragraph, index) => {
          const mapping = mappingByIndex.get(index);
          return (
            <button
              key={`${source.source_id}-${index}`}
              type="button"
              className={`paragraph-card${selectedIndex === index ? " paragraph-card--active" : ""}`}
              onClick={() => onSelectIndex(index)}
            >
              <span className={`mapping-badge mapping-badge--${mapping?.action ?? "없음"}`}>{mapping?.action ?? "미분류"}</span>
              <pre>{paragraph}</pre>
            </button>
          );
        })}
      </div>
    </div>
  );
}
