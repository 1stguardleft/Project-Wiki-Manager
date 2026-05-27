import { useEffect, useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ReactFlow, { Background, Controls, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'
import { useRunEvents } from '../hooks/useRunEvents.js'

function WfNode({ data }) {
  return (
    <div className={`wf-node ${data.status}`}>
      <Handle type="target" position={Position.Left} />
      <div className="label">{data.label}</div>
      {data.summary && <div className="sum">{data.summary}</div>}
      {data.duration != null && <div className="sum">{data.duration}ms</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
const nodeTypes = { wf: WfNode }

export default function WorkflowView() {
  const { runId } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { nodes, order, runStatus, result } = useRunEvents(runId)

  // batch queue: remaining run ids passed via ?queue=id2,id3
  const queue = (sp.get('queue') || '').split(',').filter(Boolean)
  const done = runStatus === 'completed' || runStatus === 'failed'
  useEffect(() => {
    if (done && queue.length) {
      const [next, ...rest] = queue
      const t = setTimeout(
        () => nav(`/runs/${next}${rest.length ? `?queue=${rest.join(',')}` : ''}`),
        1400,
      )
      return () => clearTimeout(t)
    }
  }, [done, runId]) // eslint-disable-line

  const COLS = 5
  const rfNodes = useMemo(
    () =>
      order.map((id, i) => ({
        id,
        type: 'wf',
        position: { x: (i % COLS) * 200, y: Math.floor(i / COLS) * 130 },
        data: {
          label: nodes[id]?.label || id,
          status: nodes[id]?.status || 'queued',
          summary: nodes[id]?.summary,
          duration: nodes[id]?.duration,
        },
      })),
    [order, nodes],
  )

  const rfEdges = useMemo(
    () =>
      order.slice(1).map((id, i) => ({
        id: `${order[i]}-${id}`,
        source: order[i],
        target: id,
        animated: nodes[id]?.status === 'running',
      })),
    [order, nodes],
  )

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>워크플로우 — <span className="muted">{runId}</span></h2>
        <div className="row">
          {queue.length > 0 && <span className="badge">배치 대기 {queue.length}건</span>}
          <span className={`badge ${runStatus}`}>{runStatus}</span>
        </div>
      </div>
      {done && queue.length > 0 && (
        <p className="muted">다음 파일로 곧 이동합니다… ({queue.length}건 남음)</p>
      )}

      <div className="card" style={{ height: 460, padding: 0 }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      {runStatus === 'completed' && result && (
        <div className="card">
          <strong>완료 ✓</strong>{' '}
          생성/갱신된 페이지:{' '}
          <Link to={`/wiki?slug=${encodeURIComponent(result.page_slug)}`}>
            [[{result.page_slug}]]
          </Link>
          {result.merge_id && (
            <>
              {' · '}
              <Link to={`/merges/${result.merge_id}`}>병합 충돌/diff 보기 →</Link>
            </>
          )}
        </div>
      )}
      {runStatus === 'failed' && result && (
        <div className="card"><strong className="badge failed">실패</strong> {result.error}</div>
      )}

      <p className="muted">
        각 노드는 LangGraph 파이프라인 단계입니다. 색: 회색=대기, 노랑=진행, 초록=완료, 빨강=실패.
      </p>
      <Link to="/ingest" className="muted">← 새 적재</Link>
    </div>
  )
}
