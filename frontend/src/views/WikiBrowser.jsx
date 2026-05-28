import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import MarkdownView from '../components/Markdown.jsx'
import { api } from '../api/client.js'

// SDLC phase key -> Korean label (folder structure in the page panel)
const PHASE_LABELS = {
  requirements: '요구사항',
  design: '설계',
  implementation: '구현',
  test: '테스트',
  deployment: '배포',
  operation: '운영',
}
const ENTITIES_KEY = '_entities'

// 페이지의 (raw) 도메인/서브도메인 문자열을 분류 체계 이름과 느슨히 매칭
const _norm = (s) => (s || '').replace(/\s+/g, '')
const looseMatch = (a, b) => {
  const x = _norm(a)
  const y = _norm(b)
  return !!x && !!y && (x.includes(y) || y.includes(x))
}
const RECENT_LIMIT = 6

export default function WikiBrowser() {
  const [params, setParams] = useSearchParams()
  const [pages, setPages] = useState([])
  const [page, setPage] = useState(null)
  const [mode, setMode] = useState('page') // page | search | query
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [structure, setStructure] = useState([]) // numbered taxonomy tree
  const [expanded, setExpanded] = useState(() => new Set()) // open folders (by node key)
  const [recentLog, setRecentLog] = useState([])
  const [logState, setLogState] = useState('loading') // loading | ok | error
  // 페이지별 이력 — 사이드바 recentLog(최신 50건)에는 잘려나갈 수 있어 별도 fetch
  const [pageLog, setPageLog] = useState([])
  const [pageLogState, setPageLogState] = useState('idle') // idle | loading | ok | error
  const [resetState, setResetState] = useState('idle') // idle | confirm | busy
  const resetBtnRef = useRef(null)
  const activeRef = useRef(null) // currently-open page row, for scroll-into-view
  const wantScrollRef = useRef(false) // scroll only on intentional focus, not on manual folder toggles
  // move focus to the destructive button when the confirm row appears (a11y)
  useEffect(() => { if (resetState === 'confirm') resetBtnRef.current?.focus() }, [resetState])

  const refresh = () => api.pages().then((d) => setPages(d.pages))
  const loadLog = () => {
    setLogState('loading')
    return api.log()
      .then((d) => { setRecentLog((d.entries || []).map(parseLogEntry)); setLogState('ok') })
      .catch(() => setLogState('error'))
  }
  useEffect(() => {
    refresh()
    loadLog()
    api.structure().then((d) => setStructure(d.phases || [])).catch(() => {})
  }, [])

  // 단계 > 도메인 > 서브도메인 트리 (도메인맵 스켈레톤) + 실제 페이지 오버레이.
  // 빈 폴더도 노출되도록 트리는 분류 체계에서 그리고, 페이지는 느슨히 매칭해 끼운다.
  const tree = useMemo(() => {
    const byPhase = {}
    for (const p of pages) (byPhase[p.sdlc_phase || ENTITIES_KEY] ??= []).push(p)

    const phases = structure.map((ph) => {
      const pp = byPhase[ph.phase] || []
      const used = new Set()
      const domains = ph.domains.map((d) => {
        const subs = d.subdomains.map((s) => {
          const sp = pp.filter((p) => !used.has(p.slug) && looseMatch(p.domain, d.name) && looseMatch(p.subdomain, s.name))
          sp.forEach((p) => used.add(p.slug))
          return { key: `${ph.phase}|${d.name}|${s.name}`, dir: s.dir, pages: sp }
        })
        const dp = pp.filter((p) => !used.has(p.slug) && looseMatch(p.domain, d.name))
        dp.forEach((p) => used.add(p.slug))
        return { key: `${ph.phase}|${d.name}`, dir: d.dir, subs, pages: dp }
      })
      const orphan = pp.filter((p) => !used.has(p.slug))
      return { key: ph.phase, dir: ph.dir, domains, orphan }
    })
    // pages under a phase not in the taxonomy (entities, unknown)
    for (const k of Object.keys(byPhase)) {
      if (!structure.some((ph) => ph.phase === k)) {
        phases.push({ key: k, dir: k === ENTITIES_KEY ? '_entities' : k,
                      label: k === ENTITIES_KEY ? '엔터티' : (PHASE_LABELS[k] || k),
                      domains: [], orphan: byPhase[k] })
      }
    }
    return phases
  }, [structure, pages])

  const allKeys = useMemo(() => {
    const keys = []
    for (const ph of tree) {
      keys.push(ph.key)
      for (const d of ph.domains) { keys.push(d.key); for (const s of d.subs) keys.push(s.key) }
    }
    return keys
  }, [tree])

  const toggleFolder = (key) => setExpanded((s) => {
    const n = new Set(s)
    n.has(key) ? n.delete(key) : n.add(key)
    return n
  })
  const allExpanded = allKeys.length > 0 && allKeys.every((k) => expanded.has(k))
  const toggleAllFolders = () =>
    setExpanded(allExpanded ? new Set() : new Set(allKeys))

  // folder keys (단계>도메인>서브도메인) on the path leading to a page
  const pathKeysFor = (slug) => {
    const keys = new Set()
    for (const ph of tree) {
      for (const d of ph.domains) {
        if (d.pages.some((x) => x.slug === slug)) { keys.add(ph.key); keys.add(d.key) }
        for (const s of d.subs) {
          if (s.pages.some((x) => x.slug === slug)) { keys.add(ph.key); keys.add(d.key); keys.add(s.key) }
        }
      }
      if (ph.orphan.some((x) => x.slug === slug)) keys.add(ph.key)
    }
    return keys
  }

  const openPage = (slug) => {
    setMode('page')
    setParams({ slug })
    wantScrollRef.current = true
    const keys = pathKeysFor(slug)
    if (keys.size) setExpanded((s) => new Set([...s, ...keys]))
    api.page(slug).then(setPage).catch(() => setPage(null))
  }
  const onSaved = (updated) => { setPage(updated); refresh(); loadLog() }
  const onDeleted = () => { setPage(null); setParams({}); refresh(); loadLog() }

  const renderPage = (p) => {
    const active = page?.slug === p.slug
    return (
      <div key={p.slug} ref={active ? activeRef : null}
        className={`list-item ${active ? 'active' : ''}`}
        onClick={() => openPage(p.slug)}>
        📄 {p.title}{' '}
        {p.source_count > 1 && <span className="badge">×{p.source_count}</span>}
      </div>
    )
  }
  const pageItem = renderPage // alias

  // shared props for a clickable + keyboard-operable folder row (트리 노드)
  const folderHeadProps = (key, open, count) => ({
    className: `folder-head ${open ? 'open' : ''} ${count === 0 ? 'is-empty' : ''}`,
    role: 'button', tabIndex: 0, 'aria-expanded': open,
    onClick: () => toggleFolder(key),
    onKeyDown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFolder(key) }
    },
  })
  // Direct entry via ?slug= (e.g. the workflow "생성된 페이지 보기 →" button):
  // load the page, and once the tree is built, expand the folder path to it.
  const slugParam = params.get('slug')
  useEffect(() => {
    if (slugParam) api.page(slugParam).then(setPage).catch(() => {})
  }, []) // eslint-disable-line
  useEffect(() => {
    if (!slugParam || tree.length === 0) return
    const keys = pathKeysFor(slugParam)
    if (!keys.size) return
    wantScrollRef.current = true
    setExpanded((s) => {
      const missing = [...keys].some((k) => !s.has(k))
      return missing ? new Set([...s, ...keys]) : s
    })
  }, [slugParam, tree]) // eslint-disable-line

  // bring the focused page into view once its folders are expanded — only after
  // an intentional focus (page open / ?slug= entry), never on manual folder toggles
  useEffect(() => {
    if (mode !== 'page' || !wantScrollRef.current || !activeRef.current) return
    activeRef.current.scrollIntoView({ block: 'nearest' })
    wantScrollRef.current = false
  }, [page, expanded, mode])

  // the history rail only makes sense alongside an open page; it shows that
  // page's own change history fetched server-side from the FULL log (the
  // sidebar's recentLog caps at 50 newest, so a page ingested early would
  // otherwise look empty even though its log entry exists).
  const showRail = mode === 'page' && !!page

  const loadPageLog = useCallback((slug) => {
    if (!slug) { setPageLog([]); setPageLogState('idle'); return Promise.resolve() }
    setPageLogState('loading')
    return api.log({ slug })
      .then((d) => { setPageLog((d.entries || []).map(parseLogEntry)); setPageLogState('ok') })
      .catch(() => setPageLogState('error'))
  }, [])
  useEffect(() => { loadPageLog(page?.slug) }, [page?.slug, loadPageLog])

  async function doSearch() {
    setMode('search')
    setResults((await api.search(q)).results)
  }
  async function doQuery() {
    setMode('query')
    setAnswer(null)
    setAnswer(await api.query(question))
  }

  async function doReset() {
    setResetState('busy')
    try {
      await api.resetWiki()
      setPage(null); setResults([]); setAnswer(null); setMode('page')
      setParams({})
      await refresh()
      await loadLog()
    } catch (e) {
      alert('초기화 실패: ' + e.message)
    }
    setResetState('idle')
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>위키 뷰어 · 검색</h2>
        {resetState === 'confirm' ? (
          <div className="row" role="alert" style={{ gap: 8, flexWrap: 'wrap' }}>
            <span className="muted" style={{ fontSize: 13 }}>
              모든 위키 데이터를 삭제합니다. 되돌릴 수 없으며, 소스 문서는 유지됩니다.
            </span>
            <button className="btn-danger" ref={resetBtnRef} onClick={doReset}>초기화</button>
            <button className="secondary" onClick={() => setResetState('idle')}>취소</button>
          </div>
        ) : (
          <button className="secondary" disabled={resetState === 'busy'}
            onClick={() => setResetState('confirm')}
            title="생성된 위키 데이터(페이지·그래프·벡터·로그)를 모두 지웁니다. 소스 문서는 유지됩니다.">
            {resetState === 'busy' ? '초기화 중…' : '데이터 초기화'}
          </button>
        )}
      </div>
      <div className="card">
        <div className="search-row">
          <input className="grow" placeholder="하이브리드 검색 (BM25 + 벡터)..." value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
          <div className="search-actions">
            <button onClick={doSearch}>검색</button>
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

      <div className={`layout-2 wiki-layout ${showRail ? 'has-rail' : ''}`}>
        <div className="card wiki-tree">
          <div className="panel-head">
            <strong>페이지 ({pages.length})</strong>
            <div className="row" style={{ gap: 6 }}>
              <button className="icon-btn" onClick={toggleAllFolders}
                title={allExpanded ? '모두 접기' : '모두 펼치기'}
                aria-label={allExpanded ? '모두 접기' : '모두 펼치기'}>{allExpanded ? '⊟' : '⊞'}</button>
              <button className="icon-btn" onClick={refresh} title="새로고침" aria-label="새로고침">↻</button>
            </div>
          </div>
          {tree.map((ph) => {
            const phOpen = expanded.has(ph.key)
            const phCount = ph.orphan.length + ph.domains.reduce(
              (a, d) => a + d.pages.length + d.subs.reduce((b, s) => b + s.pages.length, 0), 0)
            return (
              <div key={ph.key} className="wiki-folder">
                <div {...folderHeadProps(ph.key, phOpen, phCount)}>
                  <span className="folder-caret" aria-hidden="true">{phOpen ? '▾' : '▸'}</span>
                  <span className="folder-ico" aria-hidden="true">{phOpen ? '📂' : '📁'}</span>
                  <span className="folder-name">{ph.dir}</span>
                  <span className={`folder-count ${phCount === 0 ? 'zero' : ''}`}>{phCount}</span>
                </div>
                {phOpen && (
                  <div className="folder-body">
                    {ph.domains.map((d) => {
                      const dOpen = expanded.has(d.key)
                      const dCount = d.pages.length + d.subs.reduce((b, s) => b + s.pages.length, 0)
                      return (
                        <div key={d.key} className="wiki-folder">
                          <div {...folderHeadProps(d.key, dOpen, dCount)}>
                            <span className="folder-caret" aria-hidden="true">{dOpen ? '▾' : '▸'}</span>
                            <span className="folder-ico" aria-hidden="true">{dOpen ? '📂' : '📁'}</span>
                            <span className="folder-name">{d.dir}</span>
                            <span className={`folder-count ${dCount === 0 ? 'zero' : ''}`}>{dCount}</span>
                          </div>
                          {dOpen && (
                            <div className="folder-body">
                              {d.subs.map((s) => {
                                const sOpen = expanded.has(s.key)
                                return (
                                  <div key={s.key} className="wiki-folder">
                                    <div {...folderHeadProps(s.key, sOpen, s.pages.length)}>
                                      <span className="folder-caret" aria-hidden="true">{sOpen ? '▾' : '▸'}</span>
                                      <span className="folder-ico" aria-hidden="true">{sOpen ? '📂' : '📁'}</span>
                                      <span className="folder-name">{s.dir}</span>
                                      <span className={`folder-count ${s.pages.length === 0 ? 'zero' : ''}`}>{s.pages.length}</span>
                                    </div>
                                    {sOpen && (
                                      <div className="folder-body">
                                        {s.pages.length === 0
                                          ? <div className="muted folder-empty">페이지 없음</div>
                                          : s.pages.map(pageItem)}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                              {d.pages.map(pageItem)}
                            </div>
                          )}
                        </div>
                      )
                    })}
                    {ph.orphan.map(pageItem)}
                    {ph.domains.length === 0 && ph.orphan.length === 0 && (
                      <div className="muted folder-empty">페이지 없음</div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="card">
          {mode === 'page' && page && (
            <PageView page={page} onOpen={openPage} onSaved={onSaved} onDeleted={onDeleted} />
          )}
          {mode === 'page' && !page && <p className="muted">왼쪽에서 페이지를 선택하세요.</p>}
          {mode === 'search' && <SearchResults results={results} onOpen={openPage} />}
          {mode === 'query' && <QueryAnswer answer={answer} onOpen={openPage} />}
        </div>

        {showRail && (
        <aside className="card recent-log">
          <div className="panel-head">
            <div>
              <strong>페이지 이력</strong>
              <p className="recent-sub">이 페이지의 변경 기록</p>
            </div>
            <button className="icon-btn" onClick={() => loadPageLog(page?.slug)} title="새로고침">↻</button>
          </div>
          <LogTimeline
            entries={pageLog}
            loading={pageLogState === 'loading'}
            error={pageLogState === 'error'}
            emptyText="이 페이지의 기록이 아직 없습니다."
            hideTitle
            compact
          />
        </aside>
        )}
      </div>
    </div>
  )
}

const STATUSES = ['active', 'draft', 'superseded', 'deprecated', 'rejected']

function PageView({ page, onOpen, onSaved, onDeleted }) {
  const fm = page.frontmatter || {}
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(fm.title || '')
  const [status, setStatus] = useState(fm.status || 'active')
  const [body, setBody] = useState(page.body || '')
  const [busy, setBusy] = useState(false)

  // reset the editor whenever a different page is opened
  useEffect(() => {
    setEditing(false)
    setTitle(fm.title || '')
    setStatus(fm.status || 'active')
    setBody(page.body || '')
  }, [page.slug]) // eslint-disable-line

  async function save() {
    setBusy(true)
    try {
      const updated = await api.updatePage(page.slug, { title, status, body })
      onSaved(updated)
      setEditing(false)
    } catch (e) {
      alert('저장 실패: ' + e.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm(`'${fm.title || page.slug}' 페이지를 삭제할까요? 되돌릴 수 없습니다.`)) return
    setBusy(true)
    try {
      await api.deletePage(page.slug)
      onDeleted(page.slug)
    } catch (e) {
      alert('삭제 실패: ' + e.message)
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="panel-head" style={{ border: 'none', paddingBottom: 0 }}>
        <h3 className="detail-title" style={{ margin: 0 }}>
          {editing ? '페이지 수정' : (fm.title || page.slug)}
          {!editing && fm.status && (
            <span className={`badge ${fm.status === 'active' ? 'succeeded' : fm.status}`}>{fm.status}</span>
          )}
        </h3>
        {!editing ? (
          <div className="row" style={{ gap: 8 }}>
            <button className="icon-btn" onClick={() => setEditing(true)} title="수정">
              <span aria-hidden="true">✏️</span> 수정
            </button>
            <button className="icon-btn" onClick={remove} disabled={busy} title="삭제">
              <span aria-hidden="true">🗑</span> 삭제
            </button>
          </div>
        ) : (
          <div className="row" style={{ gap: 8 }}>
            <button onClick={save} disabled={busy}>{busy ? '저장 중…' : '저장'}</button>
            <button className="secondary" onClick={() => setEditing(false)} disabled={busy}>취소</button>
          </div>
        )}
      </div>

      <div className="detail-meta">
        단계: {fm.sdlc_phase || '—'} · 출처 {fm.source_count ?? 0}개 · {page.path}
      </div>

      {editing ? (
        <div>
          <label>제목</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
          <label>상태</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {(STATUSES.includes(status) ? STATUSES : [status, ...STATUSES]).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <label>본문 (Markdown)</label>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} style={{ minHeight: 340 }} />
        </div>
      ) : (
        <MarkdownView>{page.body}</MarkdownView>
      )}

      {!editing && page.backlinks?.length > 0 && (
        <div className="link-row" style={{ marginTop: 18 }}>
          <span>백링크 ({page.backlinks.length}):</span>
          {page.backlinks.map((b) => (
            <button key={b} className="link-btn" onClick={() => onOpen(b)}>[[{b}]]</button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Activity log (wiki/log.md) ──────────────────────────────────────────────
const LOG_KIND = {
  ingest: { label: '적재', cls: 'succeeded' },
  edit: { label: '수정', cls: 'pending' },
  delete: { label: '삭제', cls: 'failed' },
}

function parseLogEntry(entry) {
  const m = entry.match(/^##\s*\[(.*?)\]\s*(\S+)\s*\|\s*(.*)$/m)
  const time = m ? m[1] : ''
  const kind = m ? m[2] : ''
  const title = m ? m[3] : entry.split('\n')[0]
  const detail = entry.replace(/^##.*$/m, '').trim()
  const slugM = entry.match(/\[\[([^\]]+)\]\]/)
  // detail is "key=value ..." — turn into chips, dropping the redundant page=[[..]]
  const chips = detail.split(/\s+/).filter((t) => t.includes('=') && !t.startsWith('page='))
  return { time, kind, title, chips, slug: slugM ? slugM[1] : '' }
}

function LogTimeline({ entries, loading, error, onOpen, activeSlug, compact }) {
  if (loading) return <p className="muted" style={{ marginTop: 12 }}>불러오는 중…</p>
  if (error) return <p className="muted" style={{ marginTop: 12, color: 'var(--fail)' }}>로그를 불러오지 못했습니다.</p>
  if (!entries.length) return <p className="muted" style={{ marginTop: 12 }}>아직 활동 기록이 없습니다.</p>
  return (
    <ul className={`timeline ${compact ? 'compact' : ''}`}>
      {entries.map((e, i) => {
        const k = LOG_KIND[e.kind] || { label: e.kind, cls: '' }
        const clickable = onOpen && e.slug
        const current = activeSlug && e.slug === activeSlug
        return (
          <li key={i} className={`tl-item ${e.kind} ${current ? 'current' : ''}`}>
            <span className="tl-dot" />
            <div className="tl-head">
              <span className={`badge ${k.cls}`}>{k.label}</span>
              <span className="tl-time">{e.time}</span>
            </div>
            <div className="tl-title">
              {clickable
                ? <button className="link-btn" onClick={() => onOpen(e.slug)}>{e.title}</button>
                : e.title}
            </div>
            {!compact && e.chips.length > 0 && (
              <div className="tl-detail">
                {e.chips.map((c, j) => <span key={j} className="kv-chip">{c}</span>)}
              </div>
            )}
          </li>
        )
      })}
    </ul>
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
      <MarkdownView>{answer.answer}</MarkdownView>
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

