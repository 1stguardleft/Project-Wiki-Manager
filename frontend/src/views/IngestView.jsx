import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client.js'

const POLICIES = [
  { value: 'manual', label: '사용자 처리 — 두 페이지 보존 후 수동 검토' },
  { value: 'prefer_incoming', label: '후반영건 자동 반영 — 신규 우선 (기존은 superseded)' },
  { value: 'prefer_existing', label: '선반영건 유지 — 기존 우선 (신규는 rejected 보관)' },
]

export default function IngestView() {
  const [mode, setMode] = useState('browse')
  const [url, setUrl] = useState('')
  const [filename, setFilename] = useState('')
  const [content, setContent] = useState('')
  const [policy, setPolicy] = useState('manual')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)

  // file browser
  const [root, setRoot] = useState('')
  const [cwd, setCwd] = useState('')
  const [parent, setParent] = useState(null)
  const [dirs, setDirs] = useState([])
  const [files, setFiles] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [loadErr, setLoadErr] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.health().then((h) => {
      setHealth(h)
      setPolicy(h.conflict_policy || 'manual')
    }).catch(() => {})
  }, [])

  const loadFiles = (subdir = '') => {
    setLoadErr('')
    api.sourceFiles(subdir)
      .then((d) => {
        setRoot(d.root); setCwd(d.cwd || ''); setParent(d.parent)
        setDirs(d.dirs || []); setFiles(d.files || [])
      })
      .catch((e) => setLoadErr(e.message))
  }
  useEffect(() => { if (mode === 'browse') loadFiles('') }, [mode]) // eslint-disable-line

  const toggle = (path) => setSelected((s) => {
    const n = new Set(s)
    n.has(path) ? n.delete(path) : n.add(path)
    return n
  })
  const curPaths = files.map((f) => f.path)
  const allSelected = curPaths.length > 0 && curPaths.every((p) => selected.has(p))
  const toggleAll = () => setSelected((s) => {
    const n = new Set(s)
    curPaths.forEach((p) => (allSelected ? n.delete(p) : n.add(p)))
    return n
  })
  const crumbs = cwd ? cwd.split('/') : []

  function gotoRuns(runs) {
    const ids = runs.map((r) => r.run_id)
    const [first, ...rest] = ids
    nav(`/runs/${first}${rest.length ? `?queue=${rest.join(',')}` : ''}`)
  }

  async function startBrowse() {
    setBusy(true)
    try {
      const paths = Array.from(selected)
      const { runs } = await api.ingestBatch(paths, policy)
      gotoRuns(runs)
    } catch (e) {
      alert('적재 시작 실패: ' + e.message)
      setBusy(false)
    }
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
              <button className="secondary" onClick={() => loadFiles(cwd)}>↻ 새로고침</button>
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
                  {files.map((f) => (
                    <tr key={f.path}
                      className={`src-row ${selected.has(f.path) ? 'selected' : ''}`}
                      onClick={() => toggle(f.path)}>
                      <td><input type="checkbox" className="cb" checked={selected.has(f.path)} readOnly /></td>
                      <td className="src-title">📄 {f.title}</td>
                      <td>{f.author || <span className="muted">—</span>}</td>
                      <td className="kv">{f.created || '—'}</td>
                      <td className="kv">{f.modified || '—'}</td>
                      <td className="kv">{f.path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {selected.size > 0 && (
              <p className="muted" style={{ marginTop: 10 }}>선택됨: {selected.size}건 (다른 폴더 포함)</p>
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
      <p className="muted">
        {mode === 'browse'
          ? '여러 건을 선택하면 순차적으로 적재되며, 각 파일의 워크플로우를 차례로 보여줍니다.'
          : '적재를 시작하면 멀티 에이전트 워크플로우 뷰로 이동합니다.'}
      </p>
    </div>
  )
}
