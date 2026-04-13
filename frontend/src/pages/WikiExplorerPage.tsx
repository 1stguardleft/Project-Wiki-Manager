import { useCallback, useEffect, useState } from "react";
import { FileTree } from "../components/WikiExplorer/FileTree";
import { fetchMarkdownFile, listFiles } from "../lib/api";

export function WikiExplorerPage() {
  const [files, setFiles] = useState<string[]>([]);
  const [filesError, setFilesError] = useState("");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState("");

  const loadFiles = useCallback(async () => {
    setFilesError("");
    try {
      const result = await listFiles("wiki");
      setFiles(result);
    } catch {
      setFilesError("파일 목록을 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    if (!selectedPath) {
      setContent("");
      setContentError("");
      return;
    }

    let cancelled = false;
    setContentLoading(true);
    setContentError("");

    fetchMarkdownFile(selectedPath)
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch(() => {
        if (!cancelled) setContentError("파일을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedPath]);

  return (
    <div className="wiki-explorer">
      {/* 사이드바 — 파일 트리 */}
      <aside className="wiki-explorer__sidebar">
        <div className="wiki-explorer__sidebar-header">
          <span className="wiki-explorer__sidebar-title">Wiki</span>
          <button
            type="button"
            className="ghost-button ghost-button--small"
            onClick={loadFiles}
            title="새로고침"
          >
            ↺
          </button>
        </div>
        {filesError ? (
          <p className="wiki-explorer__error">{filesError}</p>
        ) : (
          <FileTree files={files} selectedPath={selectedPath} onSelect={setSelectedPath} />
        )}
      </aside>

      {/* 메인 — 파일 내용 */}
      <main className="wiki-explorer__main">
        {!selectedPath ? (
          <div className="wiki-explorer__placeholder">
            <p>왼쪽 파일 트리에서 파일을 선택하세요.</p>
          </div>
        ) : contentLoading ? (
          <div className="wiki-explorer__placeholder">
            <p>불러오는 중…</p>
          </div>
        ) : contentError ? (
          <div className="wiki-explorer__placeholder">
            <p className="wiki-explorer__error">{contentError}</p>
          </div>
        ) : (
          <div className="wiki-explorer__viewer">
            <div className="wiki-explorer__viewer-header">
              <span className="wiki-explorer__viewer-path">{selectedPath}</span>
            </div>
            <pre className="wiki-explorer__viewer-body">{content}</pre>
          </div>
        )}
      </main>
    </div>
  );
}
