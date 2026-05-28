import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client.js'
import { diffRows } from '../components/lineDiff.js'
import MdEditor from '../components/MdEditor.jsx'

// merge status (영문) -> 한국어 라벨
const STATUS_KO = {
  auto_resolved: '자동 반영', accepted: '반영됨', reverted: '되돌림',
  pending: '대기', rejected: '거부', superseded: '대체됨',
}
const statusKo = (s) => STATUS_KO[s] || s

export default function DiffView() {
  const { mergeId } = useParams()
  const [list, setList] = useState([])
  const [rec, setRec] = useState(null)
  const [liveBody, setLiveBody] = useState('')   // 현재 페이지 본문 (변경 후 = 라이브)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [confirmHunk, setConfirmHunk] = useState(null) // hunk id pending revert confirm

  const refresh = () => api.merges().then((d) => setList(d.merges))
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    // 이전 항목의 rec/liveBody를 즉시 비워, 새 항목 fetch 직전에 "옛 왼쪽 + 옛
    // 오른쪽 본문이 잠시 섞여 보이는" 깜빡임을 차단. fetch는 자기 응답인지 확인
    // 후에만 반영(중간에 다시 클릭한 경우 stale 응답이 덮어쓰지 않게).
    setErr(''); setEditing(false); setConfirmHunk(null)
    setRec(null); setLiveBody('')
    if (!mergeId) return
    let alive = true
    api.diff(mergeId).then((d) => { if (alive) setRec(d) })
      .catch(() => { if (alive) setRec(null) })
    return () => { alive = false }
  }, [mergeId])

  // 우측은 스냅샷이 아니라 살아있는 페이지 본문 → 부분 롤백/수정이 즉시 반영됨.
  // rec.after를 즉시 보여주고(빈 칸 깜빡임 방지), 라이브 본문이 오면 교체.
  useEffect(() => {
    if (!rec) { setLiveBody(''); return }
    setLiveBody(rec.after || '')
    let alive = true
    api.page(rec.target_slug).then((p) => { if (alive) setLiveBody(p.body || '') })
      .catch(() => { /* page may be gone — keep rec.after */ })
    return () => { alive = false }
  }, [rec])

  // 변경 전(rec.before) ↔ 변경 후(라이브) diff + 연속 변경 묶음(hunk) 태깅
  const { rows, hunkCount } = useMemo(() => {
    const rs = rec ? diffRows(rec.before, liveBody) : []
    let id = 0
    let inHunk = false
    const seen = new Set()
    for (const r of rs) {
      if (r.type !== 'equal') {
        if (!inHunk) { id++; inHunk = true }
        r.hunk = id
        r.hunkFirst = !seen.has(id)
        seen.add(id)
      } else { inHunk = false; r.hunk = null; r.hunkFirst = false }
    }
    return { rows: rs, hunkCount: id }
  }, [rec, liveBody])

  const reverted = rec?.status === 'reverted'

  async function reloadLive() {
    refresh()
    try { const p = await api.page(rec.target_slug); setLiveBody(p.body || '') }
    catch { /* page may be gone */ }
  }

  async function save(body, after) {
    setBusy(true); setErr('')
    try {
      await api.updatePage(rec.target_slug, { body })
      await reloadLive()
      after?.()
    } catch (e) { setErr('저장 실패: ' + e.message) }
    setBusy(false)
  }

  // 변경 단위 롤백: 이 hunk만 '변경 전' 내용으로 되돌린 새 본문을 저장 (확인 후)
  function revertHunk(hunkId) {
    const lines = []
    for (const r of rows) {
      if (r.hunk === hunkId) { if (r.left != null) lines.push(r.left) }
      else if (r.right != null) lines.push(r.right)
    }
    save(lines.join('\n'), () => setConfirmHunk(null))
  }

  // 전체 병합 되돌리기
  async function revertAll() {
    setBusy(true); setErr('')
    try {
      await api.revertMerge(rec.id)
      setRec(await api.diff(rec.id))
      await reloadLive()
    } catch (e) { setErr('되돌리기 실패: ' + e.message) }
    setBusy(false)
  }

  return (
    <div>
      <h2>충돌 / Diff</h2>
      <div className="layout-2">
        <div className="card">
          <strong>병합 이력 ({list.length})</strong>
          {list.length === 0 && <p className="muted">아직 병합 없음</p>}
          {list.map((m) => (
            // Link (SPA navigation): native <a> 였을 때 클릭마다 풀 리로드가
            // 일어나 화면 전체가 깜빡였음. <Link>로 라우터만 갱신.
            <Link key={m.id} to={`/merges/${m.id}`}
                  className={`list-item${m.id === mergeId ? ' is-active' : ''}`}
                  style={{ display: 'block' }} aria-current={m.id === mergeId ? 'page' : undefined}>
              [[{m.target_slug}]]{' '}
              {m.relation && <span className="kv">{m.relation}</span>}{' '}
              {/* 충돌 0건은 굳이 표시하지 않음 — 시각 노이즈 제거 */}
              {m.conflicts > 0 && (
                <><span className="badge failed">충돌 {m.conflicts}</span>{' '}</>
              )}
              <span className={`badge ${m.status}`}>{statusKo(m.status)}</span>
            </Link>
          ))}
        </div>

        <div className="card">
          {!rec && (
            <p className="muted">
              {mergeId ? '병합 정보를 불러오는 중…' : '병합 항목을 선택하세요.'}
            </p>
          )}
          {rec && (
            <div>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <h3 style={{ margin: 0 }}>
                  [[{rec.target_slug}]] <span className={`badge ${rec.status}`}>{statusKo(rec.status)}</span>
                </h3>
                <div className="row" style={{ gap: 8 }}>
                  {!editing && (
                    <button className="secondary" disabled={busy}
                      onClick={() => { setDraft(liveBody); setEditing(true) }}>직접 수정</button>
                  )}
                  {!editing && !reverted && (
                    <button className="btn-danger" disabled={busy} onClick={revertAll}
                      title="이 병합을 통째로 취소하고 병합 전 내용으로 복원합니다">
                      {busy ? '처리 중…' : '전체 되돌리기'}
                    </button>
                  )}
                </div>
              </div>
              <p className="muted" style={{ marginTop: 6 }}>
                LLM이 자동 화해하여 이미 반영된 병합입니다. 변경 단위로 되돌리거나 직접 수정할 수 있습니다.
              </p>
              {err && <p className="conflict" style={{ marginTop: 8 }}>{err}</p>}

              {rec.relation && (
                <p className="muted">
                  관계 판정: <strong>{rec.relation}</strong>
                  {rec.policy && <> · 전략: <strong>{rec.policy}</strong></>}
                  {rec.confidence != null && <> · 확신도: <strong>{(rec.confidence * 100).toFixed(0)}%</strong></>}
                </p>
              )}
              {rec.rationale && <p className="result-snippet">🧠 화해 근거: {rec.rationale}</p>}

              {editing ? (
                <div style={{ marginTop: 10 }}>
                  <label>본문 직접 수정 (Markdown)</label>
                  <MdEditor value={draft} onChange={setDraft} minHeight={360} />
                  <div className="row" style={{ marginTop: 8 }}>
                    <button disabled={busy} onClick={() => save(draft, () => setEditing(false))}>
                      {busy ? '저장 중…' : '저장'}
                    </button>
                    <button className="secondary" disabled={busy} onClick={() => setEditing(false)}>취소</button>
                  </div>
                </div>
              ) : (
                <>
                  <h4 style={{ marginBottom: 6 }}>
                    변경 내용 <span className="muted" style={{ fontWeight: 400 }}>
                      · {hunkCount > 0 ? `${hunkCount}개 변경` : '변경 없음'}</span>
                  </h4>
                  {confirmHunk != null && (
                    <div className="row" role="alert" style={{ gap: 8, margin: '8px 0' }}>
                      <span className="muted">선택한 변경을 ‘변경 전’ 내용으로 되돌릴까요?</span>
                      <button className="btn-danger" disabled={busy} onClick={() => revertHunk(confirmHunk)}>
                        {busy ? '되돌리는 중…' : '되돌리기'}
                      </button>
                      <button className="secondary" disabled={busy} onClick={() => setConfirmHunk(null)}>취소</button>
                    </div>
                  )}
                  <div className="diff-split">
                    <table className="diff-table">
                      <thead>
                        <tr>
                          <th className="diff-act" />
                          <th colSpan={2} className="diff-th del">변경 전</th>
                          <th colSpan={2} className="diff-th add">변경 후 (현재)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r, i) => {
                          const leftMark = r.left != null && (r.type === 'del' || r.type === 'mod')
                          const rightMark = r.right != null && (r.type === 'add' || r.type === 'mod')
                          return (
                            <tr key={i}>
                              <td className={`diff-act ${r.hunk != null && !reverted ? 'in-hunk' : ''}`}>
                                {r.hunkFirst && !reverted && (
                                  <button className={`hunk-revert ${confirmHunk === r.hunk ? 'armed' : ''}`}
                                    disabled={busy} title="이 변경만 변경 전 내용으로 되돌리기"
                                    aria-label="이 변경만 되돌리기" onClick={() => setConfirmHunk(r.hunk)}>↩ 복원</button>
                                )}
                              </td>
                              <td className="diff-gutter" aria-hidden="true">{r.leftNo || ''}</td>
                              <td className={`diff-cell ${r.left == null ? 'diff-empty' : leftMark ? 'diff-del' : ''}`}>
                                {leftMark && <span className="diff-sign">−</span>}{r.left ?? ''}
                              </td>
                              <td className="diff-gutter" aria-hidden="true">{r.rightNo || ''}</td>
                              <td className={`diff-cell ${r.right == null ? 'diff-empty' : rightMark ? 'diff-add' : ''}`}>
                                {rightMark && <span className="diff-sign">+</span>}{r.right ?? ''}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
