interface BatchProgressProps {
  total: number;
  completed: number;
  currentLabel: string;
}

export function BatchProgress({ total, completed, currentLabel }: BatchProgressProps) {
  const ratio = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;

  return (
    <div className="batch-progress">
      <div className="batch-progress__header">
        <span>{completed} / {total} 완료</span>
        <span>{ratio}%</span>
      </div>
      <div className="progress-bar">
        <span style={{ width: `${ratio}%` }} />
      </div>
      <p className="helper-text">{currentLabel}</p>
    </div>
  );
}
