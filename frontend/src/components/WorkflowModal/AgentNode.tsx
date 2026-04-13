import type { StageName, StageStatus } from "../../types";

const LABELS: Record<StageName, string> = {
  fetcher: "Fetcher",
  normalizer: "Normalizer",
  ingest: "Ingest",
  index_log: "Index/Log",
};

interface AgentNodeProps {
  stage: StageName;
  status: StageStatus;
  elapsedMs?: number;
  onClick?: () => void;
}

export function AgentNode({ stage, status, elapsedMs = 0, onClick }: AgentNodeProps) {
  return (
    <button className={`agent-node agent-node--${status}`} type="button" onClick={onClick}>
      <strong>{LABELS[stage]}</strong>
      <span>{status}</span>
      <small>{elapsedMs > 0 ? `${(elapsedMs / 1000).toFixed(1)}s` : "-"}</small>
    </button>
  );
}
