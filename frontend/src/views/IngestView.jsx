import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MarkdownView from '../components/Markdown.jsx'
import { api } from '../api/client.js'

const POLICIES = [
  { value: 'llm_merge', label: '자동 화해 (추천) — LLM이 모순을 해소해 한 페이지로 통합 (사람 개입 0)' },
  { value: 'manual', label: '사용자 처리 — 두 페이지 보존 후 수동 검토' },
  { value: 'prefer_incoming', label: '후반영건 자동 반영 — 신규 우선 (기존은 superseded)' },
  { value: 'prefer_existing', label: '선반영건 유지 — 기존 우선 (신규는 rejected 보관)' },
]

export default function IngestView() {
  const [mode, setMode] = useState('browse')
  const [url, setUrl] = useState('')
  const [filename, setFilename] = useState('')
  const [content, setContent] = useState('')
  const [policy, setPolicy] = useState('llm_merge')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)

  // file browser
  const [root, setRoot] = useState('')
  const [cwd, setCwd] = useState('')
  const [parent, setParent] = useState(null)
  const [dirs, setDirs] = useState([])
  const [files, setFiles] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [hideIngested, setHideIngested] = useState(false)
  const [ingestedMap, setIngestedMap] = useState({}) // 분석됨 경로→제목 누적(폴더 이동 포함)
  const [reConfirm, setReConfirm] = useState(null) // 재분석 확인 대기 중인 분석됨 경로 목록
  const confirmRef = useRef(null)
  const [loadErr, setLoadErr] = useState('')
  // file preview (browse mode)
  const [preview, setPreview] = useState(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [previewErr, setPreviewErr] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.health().then((h) => {
      setHealth(h)
      setPolicy(h.conflict_policy || 'llm_merge')
    }).catch(() => {})
  }, [])

  const loadFiles = (subdir = '') => {
    setLoadErr('')
    api.sourceFiles(subdir)
      .then((d) => {
        setRoot(d.root); setCwd(d.cwd || ''); setParent(d.parent)
        setDirs(d.dirs || []); setFiles(d.files || [])
        // 폴더를 이동해도 분석됨 여부(+제목)를 기억(교차 폴더 선택 확인용)
        setIngestedMap((prev) => {
          const n = { ...prev }
          for (const f of d.files || []) { if (f.ingested) n[f.path] = f.title; else delete n[f.path] }
          return n
        })
      })
      .catch((e) => setLoadErr(e.message))
  }
  useEffect(() => { if (mode === 'browse') loadFiles('') }, [mode]) // eslint-disable-line

  // 확인 패널이 떠 있을 때 선택이 바뀌면 패널을 닫아 내용과 선택을 동기화
  useEffect(() => { if (reConfirm) confirmRef.current?.focus() }, [reConfirm])
  const toggle = (path) => { setReConfirm(null); setSelected((s) => {
    const n = new Set(s)
    n.has(path) ? n.delete(path) : n.add(path)
    return n
  }) }
  const doneCount = files.filter((f) => f.ingested).length
  const visibleFiles = hideIngested ? files.filter((f) => !f.ingested) : files
  const curPaths = visibleFiles.map((f) => f.path)
  const allSelected = curPaths.length > 0 && curPaths.every((p) => selected.has(p))
  const toggleAll = () => { setReConfirm(null); setSelected((s) => {
    const n = new Set(s)
    curPaths.forEach((p) => (allSelected ? n.delete(p) : n.add(p)))
    return n
  }) }
  const crumbs = cwd ? cwd.split('/') : []

  function openPreview(path) {
    setPreviewErr('')
    setPreviewBusy(true)
    setPreview({ path, loading: true })
    api.sourceFile(path)
      .then((d) => setPreview(d))
      .catch((e) => { setPreview(null); setPreviewErr(e.message) })
      .finally(() => setPreviewBusy(false))
  }

  function gotoRuns(runs) {
    const ids = runs.map((r) => r.run_id)
    const [first, ...rest] = ids
    nav(`/runs/${first}${rest.length ? `?queue=${rest.join(',')}` : ''}`)
  }

  async function runBatch() {
    setBusy(true)
    setReConfirm(null)
    try {
      const paths = Array.from(selected)
      const { runs } = await api.ingestBatch(paths, policy)
      gotoRuns(runs)
    } catch (e) {
      alert('적재 시작 실패: ' + e.message)
      setBusy(false)
    }
  }

  function startBrowse() {
    // 이미 분석된 문서가 선택에 포함되면 재분석 전에 한 번 더 확인
    const dupes = Array.from(selected).filter((p) => p in ingestedMap)
    if (dupes.length) { setReConfirm(dupes); return }
    runBatch()
  }

  async function startSingle() {
    setBusy(true)
    try {
      const base =
        mode === 'url'
          ? { source_type: 'url', url }
          : { source_type: 'file', filename: filename || 'upload.md', content }
      const { run_id } = await api.ingest({ ...base, conflict_policy: policy })
      nav(`/runs/${run_id}`)
    } catch (e) {
      alert('적재 시작 실패: ' + e.message)
      setBusy(false)
    }
  }

  function onFile(e) {
    const f = e.target.files[0]
    if (!f) return
    setFilename(f.name)
    f.text().then(setContent)
  }

  return (
    <div>
      <h2>적재 / 소스 입력</h2>
      {health && (
        <p className="muted">
          LLM: <span className={`badge ${health.llm_enabled ? 'succeeded' : ''}`}>
            {health.llm_enabled ? `ON (${health.chat_model})` : 'OFF (오프라인 폴백)'}
          </span>
        </p>
      )}

      <div className="card">
        <div className="row">
          <button className={mode === 'browse' ? '' : 'secondary'} onClick={() => setMode('browse')}>파일 브라우저</button>
          <button className={mode === 'direct' ? '' : 'secondary'} onClick={() => setMode('direct')}>직접 입력 / 업로드</button>
          <button className={mode === 'url' ? '' : 'secondary'} onClick={() => setMode('url')}>웹페이지 URL</button>
        </div>

        {mode === 'browse' && (
          <div style={{ marginTop: 14 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div className="breadcrumb">
                <span className="crumb" onClick={() => loadFiles('')}>📁 root</span>
                {crumbs.map((seg, i) => (
                  <span key={i}>
                    <span className="crumb-sep">/</span>
                    <span className="crumb" onClick={() => loadFiles(crumbs.slice(0, i + 1).join('/'))}>{seg}</span>
                  </span>
                ))}
              </div>
              <div className="row" style={{ gap: 12 }}>
                {doneCount > 0 && (
                  <label className="filter-toggle" title="현재 폴더에서 이미 분석한 문서를 목록에서 숨깁니다">
                    <input type="checkbox" className="cb" checked={hideIngested}
                      aria-label="미분석 문서만 보기" onChange={(e) => setHideIngested(e.target.checked)} />
                    미분석만 보기
                    <span className="muted">(분석됨 {doneCount}건)</span>
                  </label>
                )}
                <button className="secondary" onClick={() => loadFiles(cwd)}>↻ 새로고침</button>
              </div>
            </div>
            {loadErr && <p className="badge failed" style={{ display: 'inline-block', marginTop: 10 }}>{loadErr}</p>}
            {!loadErr && dirs.length === 0 && files.length === 0 && (
              <p className="muted">이 폴더에 하위 폴더나 md 파일이 없습니다.</p>
            )}
            {(dirs.length > 0 || files.length > 0) && (
              <table className="src-table">
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>
                      <input type="checkbox" className="cb" checked={allSelected} onChange={toggleAll}
                        title="현재 폴더 파일 전체 선택" disabled={files.length === 0} />
                    </th>
                    <th>제목 / 폴더</th>
                    <th>작성자</th>
                    <th>작성일시</th>
                    <th>최종수정일시</th>
                    <th>경로</th>
                  </tr>
                </thead>
                <tbody>
                  {parent !== null && (
                    <tr className="src-row dir-row" onClick={() => loadFiles(parent)}>
                      <td></td>
                      <td className="src-title">📁 ..</td>
                      <td colSpan={4} className="kv">상위 폴더</td>
                    </tr>
                  )}
                  {dirs.map((d) => (
                    <tr key={d.path} className="src-row dir-row" onClick={() => loadFiles(d.path)}>
                      <td></td>
                      <td className="src-title">📁 {d.name}</td>
                      <td colSpan={4} className="kv">md {d.md_count}건 · {d.path}</td>
                    </tr>
                  ))}
                  {visibleFiles.map((f) => (
                    <tr key={f.path}
                      className={`src-row ${selected.has(f.path) ? 'selected' : ''} ${preview?.path === f.path ? 'previewing' : ''}`}
                      onClick={() => toggle(f.path)}>
                      <td><input type="checkbox" className="cb" checked={selected.has(f.path)}
                        aria-label={`${f.title} 선택`}
                        onChange={() => toggle(f.path)} onClick={(e) => e.stopPropagation()} /></td>
                      <td className="src-title">
                        📄 {f.title}
                        {f.ingested && (
                          <span className="badge" title="이미 분석되어 위키에 반영된 문서입니다 (다시 선택해 재적재할 수도 있습니다)">✓ 분석됨</span>
                        )}
                        <button className="preview-btn" title="내용 미리보기"
                          onClick={(e) => { e.stopPropagation(); openPreview(f.path) }}>👁 미리보기</button>
                      </td>
                      <td>{f.author || <span className="muted">—</span>}</td>
                      <td className="kv">{f.created || '—'}</td>
                      <td className="kv">{f.modified || '—'}</td>
                      <td className="kv">{f.path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {hideIngested && files.length > 0 && visibleFiles.length === 0 && (
              <p className="muted" style={{ marginTop: 10 }}>이 폴더의 문서는 모두 분석되었습니다.</p>
            )}
            {selected.size > 0 && (
              <p className="muted" style={{ marginTop: 10 }}>선택됨: {selected.size}건 (다른 폴더 포함)</p>
            )}
            {previewErr && (
              <p className="badge failed" style={{ display: 'inline-block', marginTop: 12 }}>미리보기 실패: {previewErr}</p>
            )}
            {preview && (
              <div className="src-preview">
                <div className="panel-head">
                  <strong>📄 {preview.title || preview.path}</strong>
                  <button className="icon-btn" title="미리보기 닫기"
                    onClick={() => { setPreview(null); setPreviewErr('') }}>✕</button>
                </div>
                {previewBusy || preview.loading ? (
                  <p className="muted" style={{ marginTop: 10 }}>불러오는 중…</p>
                ) : (
                  <>
                    <p className="kv" style={{ marginTop: 8 }}>
                      {preview.path} · {preview.lines}줄 · {(preview.size / 1024).toFixed(1)} KB
                    </p>
                    <MarkdownView className="md-body preview-body">{preview.content}</MarkdownView>
                    {preview.truncated && (
                      <p className="muted" style={{ marginTop: 8 }}>… 앞부분만 표시됩니다. 전체 내용은 적재 시 처리됩니다.</p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {mode === 'direct' && (
          <div style={{ marginTop: 6 }}>
            <label>파일 업로드 (.md)</label>
            <input type="file" accept=".md,.markdown,.txt" onChange={onFile} />
            <label>또는 내용 직접 입력</label>
            <textarea value={content} onChange={(e) => setContent(e.target.value)}
              placeholder="# 제목&#10;&#10;문서 내용..." />
          </div>
        )}

        {mode === 'url' && (
          <div style={{ marginTop: 6 }}>
            <label>URL</label>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
          </div>
        )}

        <label>충돌(모순) 처리 정책</label>
        <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
          {POLICIES.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>

        {reConfirm && (
          <div className="reingest-confirm" role="alert" ref={confirmRef} tabIndex={-1}>
            <strong>⚠️ 이미 분석된 문서 {reConfirm.length}건이 포함되어 있습니다.</strong>
            <p className="muted" style={{ margin: '6px 0' }}>다시 적재하면 해당 문서를 <b>재분석</b>합니다. 계속할까요?</p>
            <ul className="reingest-list">
              {reConfirm.slice(0, 6).map((p) => (
                <li key={p}>
                  <span className="badge succeeded">✓ 분석됨</span>{' '}
                  {ingestedMap[p] || p}
                </li>
              ))}
              {reConfirm.length > 6 && <li className="kv">… 외 {reConfirm.length - 6}건</li>}
            </ul>
            <div className="row" style={{ marginTop: 8 }}>
              <button disabled={busy} onClick={runBatch}>
                {busy ? '시작 중…' : '재분석 진행'}
              </button>
              <button className="secondary" disabled={busy} onClick={() => setReConfirm(null)}>취소</button>
            </div>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          {mode === 'browse' ? (
            <button disabled={busy || selected.size === 0} onClick={startBrowse}>
              {busy ? '시작 중...' : `선택 ${selected.size}건 적재 ▶`}
            </button>
          ) : (
            <button disabled={busy || (mode === 'url' ? !url : !content)} onClick={startSingle}>
              {busy ? '시작 중...' : '적재 시작 ▶'}
            </button>
          )}
        </div>
      </div>
      {mode !== 'browse' && (
        <p className="muted">적재를 시작하면 멀티 에이전트 워크플로우 뷰로 이동합니다.</p>
      )}
    </div>
  )
}
