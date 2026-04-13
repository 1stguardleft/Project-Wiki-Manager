import { useRef, useState } from "react";
import type { SourceDraft, SourceType } from "../../types";
import { uploadLocalFile } from "../../lib/api";

const LABELS: Record<SourceType, string> = {
  web: "웹 페이지 URL",
  confluence: "Confluence 페이지",
  local_md: "로컬 MD 파일",
};

const ICONS: Record<SourceType, string> = {
  web: "W",
  confluence: "C",
  local_md: "M",
};

function extractPageId(value: string) {
  return value.match(/\/pages\/(\d+)/)?.[1] ?? "";
}

interface SourceInputItemProps {
  source: SourceDraft;
  onChange: (next: SourceDraft) => void;
  onRemove: () => void;
}

export function SourceInputItem({ source, onChange, onRemove }: SourceInputItemProps) {
  const pageId = source.type === "confluence" ? extractPageId(source.value) : "";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError("");

    try {
      const result = await uploadLocalFile(file);
      onChange({ ...source, value: result.path });
      setUploadedFilename(result.filename);
    } catch {
      setUploadError("업로드 실패. 다시 시도해주세요.");
    } finally {
      setUploading(false);
      // input 초기화 (같은 파일 재선택 허용)
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <article className="source-card">
      <div className="source-card__badge">{ICONS[source.type]}</div>
      <div className="source-card__body">
        <label className="field-label" htmlFor={source.id}>
          {LABELS[source.type]}
        </label>

        {source.type === "local_md" ? (
          <div className="local-md-input">
            {/* 파일 선택 버튼 */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".md"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <button
              type="button"
              className="ghost-button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? "업로드 중…" : "파일 선택"}
            </button>

            {/* 선택된 파일명 표시 */}
            {uploadedFilename && !uploadError && (
              <span className="local-md-filename">{uploadedFilename}</span>
            )}
            {uploadError && (
              <span className="local-md-error">{uploadError}</span>
            )}

            {/* 경로 직접 입력 (선택 사항) */}
            <input
              id={source.id}
              className="field-input"
              value={source.value}
              onChange={(event) => {
                setUploadedFilename("");
                onChange({ ...source, value: event.target.value });
              }}
              placeholder="/Users/me/notes/example.md"
            />
          </div>
        ) : (
          <input
            id={source.id}
            className="field-input"
            value={source.value}
            onChange={(event) => onChange({ ...source, value: event.target.value })}
            placeholder={
              source.type === "web"
                ? "https://example.com/article"
                : "https://your-domain.atlassian.net/wiki/spaces/.../pages/123456"
            }
          />
        )}

        {source.type === "confluence" && (
          <div className="source-meta">
            {pageId ? `page_id: ${pageId}` : "Confluence URL에서 page_id를 자동 추출합니다."}
          </div>
        )}
      </div>
      <button className="ghost-button" onClick={onRemove} type="button">
        삭제
      </button>
    </article>
  );
}
