import type { DiffLine } from "../../lib/diff";

interface DiffPanelProps {
  wikiPath: string;
  lines: DiffLine[];
}

export function DiffPanel({ wikiPath, lines }: DiffPanelProps) {
  return (
    <div className="result-panel">
      <div className="result-panel__header">
        <h3>wiki 변경</h3>
        <span>{wikiPath || "wiki 페이지를 선택하세요."}</span>
      </div>
      <div className="diff-view">
        {lines.length === 0 ? (
          <div className="empty-state">비교 결과가 아직 없습니다.</div>
        ) : (
          lines.map((line, index) => (
            <div key={`${line.kind}-${index}`} className={`diff-line diff-line--${line.kind}`}>
              <span className="diff-prefix">{line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " "}</span>
              <code>{line.value || " "}</code>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
