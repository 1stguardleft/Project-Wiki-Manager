interface ArtifactPreviewProps {
  title: string;
  content: string;
  error: string;
}

export function ArtifactPreview({ title, content, error }: ArtifactPreviewProps) {
  return (
    <section className="artifact-preview">
      <div className="artifact-preview__header">
        <h3>{title}</h3>
        {error ? <span className="status-pill status-pill--error">{error}</span> : null}
      </div>
      <pre>{content || "이 단계에서는 미리보기 가능한 markdown 산출물이 없거나 아직 준비되지 않았습니다."}</pre>
    </section>
  );
}
