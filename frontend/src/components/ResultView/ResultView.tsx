import { useEffect, useState } from "react";

import { createLineDiff } from "../../lib/diff";
import type { CompareResponse, SourceRuntime } from "../../types";
import { DiffPanel } from "./DiffPanel";
import { MappingLayer } from "./MappingLayer";
import { SourcePanel } from "./SourcePanel";

interface ResultViewProps {
  runtimes: SourceRuntime[];
  activeSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  onOpenWorkflow: () => void;
  compareData: CompareResponse | null;
  isLoading: boolean;
  emptyMessage: string;
}

export function ResultView({
  runtimes,
  activeSourceId,
  onSelectSource,
  onOpenWorkflow,
  compareData,
  isLoading,
  emptyMessage,
}: ResultViewProps) {
  const [selectedParagraphIndex, setSelectedParagraphIndex] = useState<number | null>(null);

  useEffect(() => {
    setSelectedParagraphIndex(null);
  }, [activeSourceId, compareData?.wiki_page.path]);

  const source = compareData?.sources[0] ?? null;
  const diffLines = compareData ? createLineDiff(source?.content ?? "", compareData.wiki_page.content) : [];
  const pages = runtimes.find((runtime) => runtime.sourceId === activeSourceId);
  const wikiPath = compareData?.wiki_page.path ?? pages?.createdWikiPages[0] ?? pages?.updatedWikiPages[0] ?? "";

  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Result View</p>
          <h2>소스별 처리 결과</h2>
        </div>
        <div className="panel__actions">
          <button className="ghost-button ghost-button--small" type="button" onClick={onOpenWorkflow} disabled={runtimes.length === 0}>
            워크플로우 열기
          </button>
          <MappingLayer />
        </div>
      </div>

      <div className="source-tabs">
        {runtimes.map((runtime) => (
          <button
            key={runtime.sourceId}
            type="button"
            className={`source-tab${runtime.sourceId === activeSourceId ? " source-tab--active" : ""}`}
            onClick={() => onSelectSource(runtime.sourceId)}
          >
            <strong>{runtime.sourceType}</strong>
            <span>{runtime.sourceValue}</span>
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="empty-state">결과를 불러오는 중입니다.</div>
      ) : !compareData ? (
        <div className="empty-state">{emptyMessage}</div>
      ) : (
        <div className="result-grid">
          <SourcePanel source={source} selectedIndex={selectedParagraphIndex} onSelectIndex={setSelectedParagraphIndex} />
          <DiffPanel wikiPath={wikiPath} lines={diffLines} />
        </div>
      )}
    </section>
  );
}
