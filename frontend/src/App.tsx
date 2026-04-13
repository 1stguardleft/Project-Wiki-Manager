import { useState } from "react";
import { IngestPage } from "./pages/IngestPage";
import { WikiExplorerPage } from "./pages/WikiExplorerPage";

type Page = "ingest" | "wiki";

export default function App() {
  const [page, setPage] = useState<Page>("ingest");

  return (
    <>
      <nav className="app-nav">
        <span className="app-nav__logo">Wiki Manager</span>
        <div className="app-nav__tabs">
          <button
            type="button"
            className={`app-nav__tab${page === "ingest" ? " app-nav__tab--active" : ""}`}
            onClick={() => setPage("ingest")}
          >
            소스 Ingest
          </button>
          <button
            type="button"
            className={`app-nav__tab${page === "wiki" ? " app-nav__tab--active" : ""}`}
            onClick={() => setPage("wiki")}
          >
            Wiki 탐색기
          </button>
        </div>
      </nav>

      {page === "ingest" ? <IngestPage /> : <WikiExplorerPage />}
    </>
  );
}
