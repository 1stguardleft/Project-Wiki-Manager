import type { SourceRuntime, StageName } from "../../types";
import { AgentNode } from "./AgentNode";

const ORDER: StageName[] = ["fetcher", "normalizer", "ingest", "index_log"];

interface PipelineFlowProps {
  runtime: SourceRuntime | null;
  onSelectStage: (stage: StageName) => void;
}

export function PipelineFlow({ runtime, onSelectStage }: PipelineFlowProps) {
  if (!runtime) {
    return <div className="empty-state">아직 실행된 소스가 없습니다.</div>;
  }

  return (
    <div className="pipeline-flow">
      {ORDER.map((stage) => (
        <AgentNode
          key={stage}
          stage={stage}
          status={runtime.stages[stage]}
          elapsedMs={runtime.elapsedMs[stage]}
          onClick={() => onSelectStage(stage)}
        />
      ))}
    </div>
  );
}
