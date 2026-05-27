import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client.js'

export default function DiffView() {
  const { mergeId } = useParams()
  const [list, setList] = useState([])
  const [rec, setRec] = useState(null)

  const refresh = () => api.merges().then((d) => setList(d.merges))
  useEffect(() => { refresh() }, [])
  useEffect(() => { if (mergeId) api.diff(mergeId).then(setRec).catch(() => {}) }, [mergeId])

  async function act(fn) {
    await fn(rec.id)
    setRec({ ...rec, status: rec.status })
    refresh()
    api.diff(rec.id).then(setRec)
  }

  return (
    <div>
      <h2>충돌 / diff</h2>
      <div className="layout-2">
        <div className="card">
          <strong>병합 이력 ({list.length})</strong>
          {list.length === 0 && <p className="muted">아직 병합 없음</p>}
          {list.map((m) => (
            <a key={m.id} href={`/merges/${m.id}`} className="list-item" style={{ display: 'block' }}>
              [[{m.target_slug}]]{' '}
              {m.relation && <span className="kv">{m.relation}</span>}{' '}
              {m.policy && <span className="kv">· {m.policy}</span>}{' '}
              <span className={`badge ${m.conflicts > 0 ? 'failed' : 'succeeded'}`}>
                충돌 {m.conflicts}
              </span>{' '}
              <span className="kv">{m.status}</span>
            </a>
          ))}
        </div>

        <div className="card">
          {!rec && <p className="muted">병합 항목을 선택하세요.</p>}
          {rec && (
            <div>
              <h3>[[{rec.target_slug}]] <span className={`badge ${rec.status}`}>{rec.status}</span></h3>
              {rec.relation && (
                <p className="muted">
                  관계 판정: <strong>{rec.relation}</strong>
                  {rec.policy && <> · 정책: <strong>{rec.policy}</strong></>}
                </p>
              )}
              {rec.conflicts?.length > 0 ? (
                <div>
                  <strong className="badge failed">충돌 {rec.conflicts.length}건</strong>
                  {rec.conflicts.map((c, i) => <div key={i} className="conflict">{c}</div>)}
                </div>
              ) : (
                <p className="muted">표시된 충돌 없음 (자동 병합 성공)</p>
              )}
              <div className="row" style={{ margin: '12px 0' }}>
                <button onClick={() => act(api.acceptMerge)}>병합 수락</button>
                <button className="secondary" onClick={() => act(api.revertMerge)}>되돌리기</button>
              </div>
              <h4>병합 후 결과</h4>
              <pre className="body">{rec.after}</pre>
              <h4 className="muted">병합 전</h4>
              <pre className="body muted">{rec.before}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
