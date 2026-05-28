import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ReactFlow, {
  Background, Controls, Handle, MarkerType, Position,
  ReactFlowProvider, useEdgesState, useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useRunEvents } from '../hooks/useRunEvents.js'

// 각 단계가 하는 일 (클릭 상세 패널에서 결과 요약과 함께 보여줌)
const STEP_DESC = {
  fetch: '원본 문서를 가져옵니다 (파일 업로드 / URL).',
  parse: '문서를 파싱해 제목과 본문을 추출합니다.',
  normalize: '본문을 깔끔한 마크다운으로 정규화하고 SDLC 단계를 분류합니다.',
  chunk: '본문을 검색용 청크로 분할합니다.',
  embed: '청크를 임베딩해 벡터 DB에 저장합니다.',
  similarity: '벡터 유사도로 기존 페이지와의 중복/유사 여부를 판단합니다.',
  conflict: '기존 페이지와의 의미 관계(모순/보강/중복)를 판단합니다.',
  merge: '신규 페이지를 만들거나 기존 페이지와 병합합니다.',
  verify: '병합 결과가 양쪽 정보를 누락 없이 보존했는지 검증합니다.',
  crossref: '관련된 다른 페이지를 찾아 상호참조 관계를 만듭니다.',
  index: '위키 인덱스를 재생성합니다.',
  log: '처리 이력을 로그에 기록합니다.',
}
const STEP_STATUS = {
  queued: { label: '대기', cls: '' },
  running: { label: '진행 중', cls: 'running' },
  succeeded: { label: '완료', cls: 'succeeded' },
  failed: { label: '실패', cls: 'failed' },
}

function WfNode({ data }) {
  return (
    <div className={`wf-node ${data.status}`} role="button" tabIndex={0}
      aria-label={`${data.label} 단계 상세 보기`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); data.onActivate?.() }
      }}>
      {/* targets + sources on multiple sides; edges pick the right one per
          serpentine direction so connectors stay short and never cross */}
      <Handle id="t-left" type="target" position={Position.Left} />
      <Handle id="t-right" type="target" position={Position.Right} />
      <Handle id="t-top" type="target" position={Position.Top} />
      <Handle id="t-bottom" type="target" position={Position.Bottom} />
      {data.usesLlm && <span className="wf-llm" title="이 단계는 LLM을 사용합니다">LLM</span>}
      <div className="label">{data.label}</div>
      {data.summary && <div className="sum">{data.summary}</div>}
      {data.duration != null && <div className="dur">{data.duration}ms</div>}
      <Handle id="s-right" type="source" position={Position.Right} />
      <Handle id="s-left" type="source" position={Position.Left} />
      <Handle id="s-bottom" type="source" position={Position.Bottom} />
    </div>
  )
}
const nodeTypes = { wf: WfNode }

// run status -> compact badge for the parallel branch list
const ROW_STATUS = {
  connecting: { label: '연결', cls: '' },
  running: { label: '진행', cls: 'running' },
  completed: { label: '완료', cls: 'succeeded' },
  failed: { label: '실패', cls: 'failed' },
  error: { label: '오류', cls: 'failed' },
}

// One parallel sibling/child run. Mounting it opens its SSE stream, so all rows
// run concurrently on the backend while staying on this single screen.
const PIPELINE_STEPS = 13 // fixed node count (NODE_SPECS) → stable progress denominator

function BranchRow({ runId, onState }) {
  const { nodes, order, runStatus, result, source } = useRunEvents(runId)
  const label = source?.unit_title || source?.ref || '도메인 로딩…'
  const running = order.find((id) => nodes[id]?.status === 'running')
  const doneN = order.filter((id) => nodes[id]?.status === 'succeeded').length
  useEffect(() => { onState(runId, runStatus, result) }, [runId, runStatus, result, onState])
  const st = ROW_STATUS[runStatus] || ROW_STATUS.connecting
  const step = runStatus === 'completed' ? '완료'
    : runStatus === 'failed' ? '실패'
      : runStatus === 'error' ? '연결 끊김'
        : running ? nodes[running].label
          : runStatus === 'connecting' ? '연결 중' : '대기'
  return (
    <div className="branch-row">
      <span className={`badge ${st.cls}`}>{st.label}</span>
      <span className="branch-label" title={label}>{label}</span>
      <span className="branch-step muted">{step}</span>
      <span className="branch-prog muted">{doneN}/{PIPELINE_STEPS}</span>
      {result?.page_slug && (
        <Link className="link-btn" to={`/wiki?slug=${encodeURIComponent(result.page_slug)}`}
          aria-label={`${label} 생성 페이지 열기`}>페이지 →</Link>
      )}
    </div>
  )
}

const LEGEND = [
  { cls: 'queued', label: '대기' },
  { cls: 'running', label: '진행' },
  { cls: 'succeeded', label: '완료' },
  { cls: 'failed', label: '실패' },
]
const STATUS_LABEL = {
  connecting: '연결 중', running: '진행 중', completed: '완료',
  failed: '실패', error: '오류',
}

// serpentine grid layout: rows alternate L→R / R→L so the whole pipeline fills
// a compact area (bigger nodes) without long diagonal edges.
const COLS = 4
const H_GAP = 250
const V_GAP = 170

export default function WorkflowView() {
  const { runId } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { nodes, order, runStatus, result } = useRunEvents(runId)

  // Pinned right detail panel. It AUTO-FOLLOWS the running step by default;
  // clicking a node (or toggling off) pauses follow so a single step can be
  // inspected. Reads nodes[selId] live, so it keeps updating as the step runs.
  const [selId, setSelId] = useState(null)
  const [auto, setAuto] = useState(true)
  const pinTo = useCallback((id) => { setSelId(id); setAuto(false) }, [])
  const resumeAuto = useCallback(() => setAuto(true), [])

  const done = runStatus === 'completed' || runStatus === 'failed'

  // Step the panel tracks while auto-following: the most recently COMPLETED
  // step (succeeded/failed). The running step has no result yet — following it
  // just flickers "처리 중…", so we show the last finished step's result and
  // advance only when the next one completes. null until the first step finishes.
  const focusId = useMemo(() => {
    let last = null
    for (const id of order) {
      const s = nodes[id]?.status
      if (s === 'succeeded' || s === 'failed') last = id
    }
    return last
  }, [order, nodes])

  // keep the panel on the focus step while following
  useEffect(() => { if (auto && focusId) setSelId(focusId) }, [auto, focusId])
  // Esc re-enables auto-follow (the panel is always pinned open now)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setAuto(true) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const sel = selId ? nodes[selId] : null

  // Parallel sibling/child runs shown in ONE screen (no route switching):
  //  - 도메인 분해 → parent run's spawned_runs (one per sub-domain)
  //  - 파일 배치 → ?queue=id2,id3
  // Each is mounted as a <BranchRow> that opens its own SSE → all run in parallel.
  // branchIds grows dynamically when a row itself spawns children (분해된 배치 파일).
  const [branchIds, setBranchIds] = useState([])
  const [childStates, setChildStates] = useState({}) // runId -> {status, result}
  const addBranch = useCallback((ids) => {
    if (!ids?.length) return
    setBranchIds((prev) => {
      const seen = new Set(prev)
      const add = ids.filter((id) => id && id !== runId && !seen.has(id))
      return add.length ? [...prev, ...add] : prev
    })
  }, [runId])

  // seed from the URL queue once
  useEffect(() => {
    const queue = (sp.get('queue') || '').split(',').filter(Boolean)
    setBranchIds([])
    setChildStates({})
    setAuto(true)
    setSelId(null)
    if (queue.length) setBranchIds(queue)
  }, [runId]) // eslint-disable-line
  // when the primary run finishes decomposing, add its children
  useEffect(() => { addBranch(result?.spawned_runs) }, [result, addBranch])

  const onChildState = useCallback((id, status, res) => {
    setChildStates((prev) => ({ ...prev, [id]: { status, result: res } }))
    addBranch(res?.spawned_runs)
  }, [addBranch])

  // Re-fit the canvas whenever nodes arrive or the run/layout state changes.
  // `fitView` prop only fits once at init; later layout shifts (footer growing
  // on completion, branch-panel mounting, panel width changes, window resize)
  // leave the viewport off — the wrapper has `overflow: hidden` so off-viewport
  // nodes get clipped and the workflow appears to "vanish". We re-fit on state
  // changes AND watch the canvas container with a ResizeObserver as a safety net.
  const rf = useRef(null)
  const canvasWrapRef = useRef(null)
  // duration:0 (no animation) — overlapping animations from rapid SSE updates
  // and ResizeObserver fires can leave the viewport stuck mid-tween
  useEffect(() => {
    if (!rf.current || order.length === 0) return
    const t = setTimeout(() => rf.current?.fitView({ padding: 0.12, duration: 0 }), 90)
    return () => clearTimeout(t)
  }, [order.length, runStatus, branchIds.length, result])
  useEffect(() => {
    const el = canvasWrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let t
    const obs = new ResizeObserver(() => {
      clearTimeout(t)
      t = setTimeout(() => rf.current?.fitView({ padding: 0.12, duration: 0 }), 80)
    })
    obs.observe(el)
    return () => { obs.disconnect(); clearTimeout(t) }
  }, [])

  const branchDone = branchIds.filter(
    (id) => ['completed', 'failed'].includes(childStates[id]?.status)).length
  const allDone = done && branchIds.length > 0 && branchDone === branchIds.length
  const childPages = branchIds
    .map((id) => childStates[id]?.result)
    .filter((r) => r?.page_slug)
    .map((r) => r.page_slug)

  const rfNodes = useMemo(
    () =>
      order.map((id, i) => {
        const row = Math.floor(i / COLS)
        const col = i % COLS
        const vcol = row % 2 === 0 ? col : COLS - 1 - col // reverse odd rows
        return {
          id,
          type: 'wf',
          position: { x: vcol * H_GAP, y: row * V_GAP },
          data: {
            label: nodes[id]?.label || id,
            status: nodes[id]?.status || 'queued',
            summary: nodes[id]?.summary,
            detail: nodes[id]?.detail,
            duration: nodes[id]?.duration,
            usesLlm: nodes[id]?.usesLlm,
            onActivate: () => pinTo(id),
          },
        }
      }),
    [order, nodes],
  )

  const rfEdges = useMemo(
    () => {
      const edges = order.slice(1).map((id, i) => {
        const rowA = Math.floor(i / COLS)
        const rowB = Math.floor((i + 1) / COLS)
        let sourceHandle, targetHandle
        if (rowA !== rowB) {
          // row turn → drop straight down into the node below
          sourceHandle = 's-bottom'
          targetHandle = 't-top'
        } else if (rowA % 2 === 0) {
          sourceHandle = 's-right'
          targetHandle = 't-left'
        } else {
          sourceHandle = 's-left'
          targetHandle = 't-right'
        }
        return {
          id: `${order[i]}-${id}`,
          source: order[i],
          target: id,
          sourceHandle,
          targetHandle,
          type: 'smoothstep',
          animated: nodes[id]?.status === 'running',
        }
      })
      // feedback branch: 누락검토 Agent loops back to 병합 Agent to fill omissions
      // (graph cycle in the backend). Drawn as a distinct amber dashed arc so the
      // pipeline reads as branching/feed-forward, not strictly one-directional.
      if (order.includes('verify') && order.includes('merge')) {
        edges.push({
          id: 'verify-merge-feedback',
          source: 'verify',
          target: 'merge',
          // route under the row (bottom→bottom) so it doesn't overlap the
          // forward merge→verify connector on the same side
          sourceHandle: 's-bottom',
          targetHandle: 't-bottom',
          type: 'smoothstep',
          pathOptions: { borderRadius: 14, offset: 24 },
          label: '누락 시 재병합',
          animated: nodes.verify?.status === 'running',
          // purple — distinct from forward edges (gray/indigo) and amber status
          style: { stroke: 'var(--accent-2)', strokeDasharray: '6 4', strokeWidth: 1.5 },
          labelStyle: { fill: 'var(--accent-2)', fontSize: 10, fontWeight: 600 },
          labelBgStyle: { fill: 'var(--panel-solid)' },
          markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent-2)' },
        })
      }
      return edges
    },
    [order, nodes],
  )

  // v11 controlled pattern: drive ReactFlow with `useNodesState`/`useEdgesState`
  // and sync from our derived memos. Passing brand-new `nodes` arrays straight
  // into the prop on every SSE tick was making the internal store fall out of
  // sync — symptom: dot background still rendered but nodes/edges vanished and
  // fit-view couldn't bring them back (no nodes in RF's internal state to fit).
  const [rfStateNodes, setRfStateNodes, onNodesChange] = useNodesState([])
  const [rfStateEdges, setRfStateEdges, onEdgesChange] = useEdgesState([])
  useEffect(() => { setRfStateNodes(rfNodes) }, [rfNodes, setRfStateNodes])
  useEffect(() => { setRfStateEdges(rfEdges) }, [rfEdges, setRfStateEdges])

  return (
    <ReactFlowProvider>
    <div className="fill-h">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>워크플로우 — <span className="muted">{runId}</span></h2>
        <div className="row">
          {branchIds.length > 0 && (
            <span className={`badge ${allDone ? 'succeeded' : 'running'}`}>
              분기 {branchDone}/{branchIds.length}
            </span>
          )}
          <span className={`badge wf-status ${runStatus}`}>{STATUS_LABEL[runStatus] || runStatus}</span>
        </div>
      </div>

      {branchIds.length > 0 && (
        <div className="branch-panel">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
            <strong>병렬 처리 · 도메인 단위 {branchIds.length}건</strong>
            {allDone
              ? <span className="badge succeeded">전체 완료</span>
              : <span className="muted">{branchDone}/{branchIds.length} 완료</span>}
          </div>
          <div className="branch-list">
            {branchIds.map((id) => <BranchRow key={id} runId={id} onState={onChildState} />)}
          </div>
        </div>
      )}

      <div className="wf-legend">
        <span className="legend-title">범례</span>
        {LEGEND.map((l) => (
          <span key={l.cls} className="legend-item">
            <span className={`legend-dot ${l.cls}`} />
            {l.label}
          </span>
        ))}
        <span className="legend-item">
          <span className="wf-llm legend-llm">LLM</span> LLM 사용 단계
        </span>
        <span className="legend-item">
          <span className="legend-edge" /> 누락 시 재병합 (피드백)
        </span>
      </div>

      <div className="card grow-canvas wf-canvas-wrap" style={{ padding: 0 }}>
        <div className="wf-canvas" ref={canvasWrapRef}>
          <ReactFlow
            nodes={rfStateNodes}
            edges={rfStateEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.2}
            onInit={(inst) => { rf.current = inst }}
            onNodeClick={(_, n) => pinTo(n.id)}
            onPaneClick={resumeAuto}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
          </ReactFlow>

          {order.length > 0 && (auto
            ? !done && (
              <div className="canvas-hint muted">완료된 단계의 결과를 따라 표시 중 — 노드를 클릭하면 그 단계에 고정됩니다</div>
            )
            : (
              <div className="canvas-hint muted">단계 고정됨 — 빈 곳을 클릭하거나 Esc로 다시 자동 추적합니다</div>
            ))}
        </div>

        <div className="wf-side" role="region" aria-label="단계 상세">
          <div className="wf-side-head">
            <div className="row" style={{ gap: 8, alignItems: 'center', minWidth: 0 }}>
              <strong className="wf-side-title">{sel ? (sel.label || selId) : '단계 상세'}</strong>
              {sel?.usesLlm && <span className="wf-llm legend-llm" title="이 단계는 LLM을 사용합니다">LLM</span>}
            </div>
            <button
              className={`wf-follow ${auto ? 'on' : ''}`}
              onClick={() => setAuto((a) => !a)}
              aria-pressed={auto}
              aria-label="자동 추적"
              title={auto
                ? '실행 단계를 자동으로 따라가는 중 — 클릭하면 멈춥니다'
                : '클릭하면 현재 실행 단계를 자동으로 따라갑니다'}
            >
              <span className="wf-follow-dot" />자동 추적
            </button>
          </div>
          <div className="wf-side-body">
            {!sel ? (
              <p className="muted">{order.length ? '첫 단계 완료를 기다리는 중…' : '파이프라인 연결 중…'}</p>
            ) : (
              <>
                <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className={`badge ${(STEP_STATUS[sel.status] || {}).cls || ''}`}>
                    {(STEP_STATUS[sel.status] || {}).label || sel.status}
                  </span>
                  {sel.duration != null && <span className="edge-detail-meta">{sel.duration}ms</span>}
                </div>
                {STEP_DESC[selId] && <p className="wf-side-desc">{STEP_DESC[selId]}</p>}

                <div className="wf-side-section-title">작업 결과</div>
                {sel.status === 'queued' ? (
                  <p className="muted">아직 처리되지 않았습니다.</p>
                ) : sel.status === 'running' ? (
                  <p className="muted">처리 중…</p>
                ) : Array.isArray(sel.detail) && sel.detail.length ? (
                  <div className="wf-results">
                    {sel.detail.map((it, idx) => (
                      <div className="wf-result" key={idx}>
                        <div className="wf-result-label">{String(it?.label ?? '')}</div>
                        {it?.value != null && <div className="wf-result-value">{String(it.value)}</div>}
                        {Array.isArray(it?.items) && (
                          <ul className="wf-result-list">
                            {it.items.map((x, j) => <li key={j}>{String(x)}</li>)}
                          </ul>
                        )}
                        {it?.code != null && <pre className="wf-result-code">{String(it.code)}</pre>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="wf-result-value">
                    {String(sel.summary || (sel.status === 'failed' ? '실패' : '완료'))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="wf-footer">
        <button className="secondary" onClick={() => nav('/ingest')}>← 새 적재</button>
        <span className="spacer" />
        {runStatus === 'failed' && result && (
          <span className="wf-error"><span className="badge failed">실패</span> {result.error}</span>
        )}
        {branchIds.length > 0 && (
          <span className="muted">
            {allDone ? `페이지 ${childPages.length}건 생성` : '도메인 단위 병렬 처리 중…'}
          </span>
        )}
        {runStatus === 'completed' && result && result.page_slug && (
          <>
            {result.merge_id && (
              <button className="secondary" onClick={() => nav(`/merges/${result.merge_id}`)}>
                충돌 / diff 보기
              </button>
            )}
            <button onClick={() => nav(`/wiki?slug=${encodeURIComponent(result.page_slug)}`)}>
              생성된 페이지 보기 →
            </button>
          </>
        )}
      </div>
    </div>
    </ReactFlowProvider>
  )
}
