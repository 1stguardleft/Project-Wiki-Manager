import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ReactFlow, { Background, Controls } from 'reactflow'
import 'reactflow/dist/style.css'
import { api } from '../api/client.js'

export default function WikiBrowser() {
  const [params, setParams] = useSearchParams()
  const [pages, setPages] = useState([])
  const [page, setPage] = useState(null)
  const [mode, setMode] = useState('page') // page | search | query | graph
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [graph, setGraph] = useState({ nodes: [], edges: [] })

  const refresh = () => api.pages().then((d) => setPages(d.pages))
  useEffect(() => { refresh() }, [])

  const openPage = (slug) => {
    setMode('page')
    setParams({ slug })
    api.page(slug).then(setPage).catch(() => setPage(null))
  }
  useEffect(() => {
    const slug = params.get('slug')
    if (slug) api.page(slug).then(setPage).catch(() => {})
  }, []) // eslint-disable-line

  const grouped = useMemo(() => {
    const g = {}
    for (const p of pages) (g[p.sdlc_phase || '_entities'] ??= []).push(p)
    return g
  }, [pages])

  async function doSearch() {
    setMode('search')
    setResults((await api.search(q)).results)
  }
  async function doQuery() {
    setMode('query')
    setAnswer(null)
    setAnswer(await api.query(question))
  }
  async function showGraph() {
    setMode('graph')
    setGraph(await api.graph())
  }

  return (
    <div>
      <h2>위키 뷰어 · 검색</h2>
      <div className="card">
        <div className="search-row">
          <input className="grow" placeholder="하이브리드 검색 (BM25 + 벡터)..." value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
          <div className="search-actions">
            <button onClick={doSearch}>검색</button>
            <button className="secondary" onClick={showGraph}>지식그래프</button>
          </div>
        </div>
        <div className="search-row">
          <input className="grow" placeholder="위키에 질문하기 (인용 기반 답변)..." value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doQuery()} />
          <div className="search-actions">
            <button onClick={doQuery}>질의</button>
          </div>
        </div>
      </div>

      <div className="layout-2">
        <div className="card">
          <div className="panel-head">
            <strong>페이지 ({pages.length})</strong>
            <button className="icon-btn" onClick={refresh} title="새로고침">↻</button>
          </div>
          {Object.entries(grouped).map(([phase, ps]) => (
            <div key={phase}>
              <div className="phase-head">{phase}</div>
              {ps.map((p) => (
                <div key={p.slug}
                  className={`list-item ${page?.slug === p.slug ? 'active' : ''}`}
                  onClick={() => openPage(p.slug)}>
                  {p.title}{' '}
                  {p.source_count > 1 && <span className="badge">×{p.source_count}</span>}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="card">
          {mode === 'page' && page && <PageView page={page} onOpen={openPage} />}
          {mode === 'page' && !page && <p className="muted">왼쪽에서 페이지를 선택하세요.</p>}
          {mode === 'search' && <SearchResults results={results} onOpen={openPage} />}
          {mode === 'query' && <QueryAnswer answer={answer} onOpen={openPage} />}
          {mode === 'graph' && <GraphView graph={graph} onOpen={openPage} />}
        </div>
      </div>
    </div>
  )
}

function PageView({ page, onOpen }) {
  const fm = page.frontmatter || {}
  return (
    <div>
      <h3 className="detail-title">
        {fm.title || page.slug}
        {fm.status && <span className={`badge ${fm.status === 'active' ? 'succeeded' : ''}`}>{fm.status}</span>}
      </h3>
      <div className="detail-meta">
        단계: {fm.sdlc_phase || '—'} · 출처 {fm.source_count ?? 0}개 · {page.path}
      </div>
      <pre className="body">{page.body}</pre>
      {page.backlinks?.length > 0 && (
        <div className="link-row">
          <span>백링크:</span>
          {page.backlinks.map((b) => (
            <a key={b} onClick={() => onOpen(b)}>[[{b}]]</a>
          ))}
        </div>
      )}
    </div>
  )
}

function SearchResults({ results, onOpen }) {
  if (!results.length) return <p className="muted">검색 결과 없음</p>
  return (
    <div>
      <h3>검색 결과 ({results.length})</h3>
      {results.map((r) => (
        <div key={r.slug} className="list-item" onClick={() => onOpen(r.slug)}>
          <div><strong>{r.title}</strong> <span className="kv">{r.sdlc_phase} · score {r.score}</span></div>
          <div className="result-snippet">{r.snippet}</div>
        </div>
      ))}
    </div>
  )
}

function QueryAnswer({ answer, onOpen }) {
  if (!answer) return <p className="muted">질의 중...</p>
  return (
    <div>
      <h3>답변</h3>
      <pre className="body">{answer.answer}</pre>
      {answer.citations?.length > 0 && (
        <div className="link-row">
          <span>인용:</span>
          {answer.citations.map((c) => (
            <a key={c.slug} onClick={() => onOpen(c.slug)}>[[{c.slug}]]</a>
          ))}
        </div>
      )}
    </div>
  )
}

function GraphView({ graph, onOpen }) {
  const nodes = graph.nodes.map((n, i) => ({
    id: n.id,
    data: { label: n.label },
    position: { x: (i % 4) * 200, y: Math.floor(i / 4) * 120 },
  }))
  const edges = graph.edges.map((e, i) => ({
    id: `e${i}`, source: e.from, target: e.to, label: e.type, animated: false,
  }))
  return (
    <div style={{ height: 440 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView
        onNodeClick={(_, n) => onOpen(n.id)}
        proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  )
}
