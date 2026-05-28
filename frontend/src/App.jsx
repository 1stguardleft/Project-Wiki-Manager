import { useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import IngestView from './views/IngestView.jsx'
import WorkflowView from './views/WorkflowView.jsx'
import WikiBrowser from './views/WikiBrowser.jsx'
import GraphExplorer from './views/GraphExplorer.jsx'
import DiffView from './views/DiffView.jsx'
import KpiDashboard from './views/KpiDashboard.jsx'

const NAV = [
  { to: '/ingest', icon: '⬆', label: '적재 / 소스 입력', desc: 'Ingest' },
  { to: '/wiki', icon: '◎', label: '위키 뷰어 · 검색', desc: 'Explore' },
  { to: '/graph', icon: '🕸', label: '지식 그래프', desc: 'Graph' },
  { to: '/merges', icon: '⚡', label: '충돌 / diff', desc: 'Conflicts' },
  { to: '/kpi', icon: '◐', label: 'KPI 대시보드', desc: 'KPI' },
]

export default function App() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('lnbCollapsed') === '1'
  )
  const toggleLnb = () => setCollapsed((c) => {
    localStorage.setItem('lnbCollapsed', c ? '0' : '1')
    return !c
  })
  const loc = useLocation()

  return (
    <div className={`app ${collapsed ? 'lnb-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">📚</div>
          <div className="brand-text">
            <div className="brand-name">Wiki Manager</div>
            <div className="brand-sub">LLM Knowledge Portal</div>
          </div>
        </div>

        <nav>
          <div className="nav-section">워크스페이스</div>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} title={n.label}>
              <span className="nav-ico">{n.icon}</span>
              <span className="nav-body">
                <span className="nav-label">{n.label}</span>
                <span className="nav-desc">{n.desc}</span>
              </span>
            </NavLink>
          ))}
        </nav>

        <div className="side-foot">
          <div className="stack-chips">
            <span className="tech-chip">LangGraph</span>
            <span className="tech-chip">Chroma</span>
            <span className="tech-chip">OpenAI</span>
          </div>
          <p className="hint">멀티 에이전트 LLM 위키 — 수집부터 충돌 판정까지 자동화된 SDLC 지식 베이스</p>
        </div>
      </aside>

      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-title">
            <button className="lnb-toggle" onClick={toggleLnb}
              title={collapsed ? '내비게이션 펼치기' : '내비게이션 접기'}
              aria-label="내비게이션 토글">☰</button>
            Project Wiki Manager
            <span className="topbar-tag">SDLC</span>
          </div>
          <div className="topbar-meta">멀티 에이전트 지식 그래프</div>
        </header>
        <main className="content">
          <ErrorBoundary key={loc.pathname}>
            <Routes>
              <Route path="/" element={<IngestView />} />
              <Route path="/ingest" element={<IngestView />} />
              <Route path="/runs/:runId" element={<WorkflowView />} />
              <Route path="/wiki" element={<WikiBrowser />} />
              <Route path="/graph" element={<GraphExplorer />} />
              <Route path="/merges" element={<DiffView />} />
              <Route path="/merges/:mergeId" element={<DiffView />} />
              <Route path="/kpi" element={<KpiDashboard />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
