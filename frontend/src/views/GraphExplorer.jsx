import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ReactFlow, { Background, Controls, Handle, MarkerType, Position } from 'reactflow'
import 'reactflow/dist/style.css'
import { api } from '../api/client.js'

// 그래프 라벨/패널에 쓰는 한글 표기 (백엔드 schema/edges.yaml 의 edge_types 와 1:1)
const EDGE_LABELS = {
  references: '참조',
  relates_to: '연관',
  implements: '구현',
  verifies: '검증',
  refines: '구체화',
  duplicate_of: '중복',
  merged_from: '병합 출처',
  supersedes: '대체',
  conflicts_with: '충돌',
}
const CONF_LABELS = { high: '높음', medium: '보통', low: '낮음' }
// confidence 전용 배지 변형 — status 배지(완료=초록/대기=노랑)와 의미가 섞이지 않도록 분리
const CONF_CLASS = { high: 'conf-high', medium: '', low: 'conf-low' }

// 도메인은 개방형(자기조직화)이라 고정 목록이 없다. status 배지(초록/앰버/빨강)와
// 겹치지 않는 카테고리 색상환에서, 활성 도메인의 등장 순서 인덱스로 색을 배정한다
// (≤9개는 충돌 없음, 초과 시 순환). 페이지 정렬이 결정적이라 리로드 간 색도 안정적.
const DOMAIN_COLORS = ['#818cf8', '#a855f7', '#38bdf8', '#fb923c', '#2dd4bf',
  '#f472b6', '#a3e635', '#facc15', '#22d3ee']
const NO_DOMAIN = '_other'
const NO_DOMAIN_COLOR = '#8b91a8'
const domainKeyOf = (node) => node.domain || NO_DOMAIN
const domainLabel = (key) => (key === NO_DOMAIN ? '기타' : key)

// domain key -> color, assigned by active-domain index ('기타'는 항상 muted)
function colorMapOf(graph) {
  const map = {}
  let i = 0
  for (const k of activeDomainsOf(graph)) {
    map[k] = k === NO_DOMAIN ? NO_DOMAIN_COLOR : DOMAIN_COLORS[i++ % DOMAIN_COLORS.length]
  }
  return map
}

// layout constants (px)
// LANE_X tightened: at 340 + 7 lanes, the row was ~2090px wide and fitView
// zoomed down to ~0.4× so the chips became 9px tall and crammed at the bottom
// of the canvas. 260 keeps a comfortable gap and lets the chips render closer
// to their natural size at fitView's maxZoom.
// TODO: this layout assumes ~7 domains; past N≈8 the row gets too wide for the
// canvas and fitView drops back below ~0.5× (chips ~15px). When that becomes a
// real case, either wrap into two rows or stop fitting horizontally past N≈7
// (lower maxZoom to ~0.9 and let the user pan via .react-flow__controls).
const LANE_X = 260
const GROUP_TOP = 28
const CARD_W = 210
const CARD_H = 46
const CARD_GAP = 12
const HEADER_H = 44
const PAD = 14
// shared fitView options — duration is added per call site
const FIT_OPTS = { padding: 0.15, minZoom: 0.3, maxZoom: 1.1 }

// SDLC 단계 옵션 (WikiBrowser PHASE 라벨과 동일하게 유지 — 프로젝트 컨벤션)
const PHASE_OPTIONS = [
  { key: 'requirements', label: '요구사항' },
  { key: 'design', label: '설계' },
  { key: 'implementation', label: '구현' },
  { key: 'test', label: '테스트' },
  { key: 'deployment', label: '배포' },
  { key: 'operation', label: '운영' },
]

// 활성 도메인을 노드 등장 순서로 모으되 '기타'는 맨 뒤로
function activeDomainsOf(graph) {
  const seen = []
  for (const n of graph.nodes) {
    const k = domainKeyOf(n)
    if (!seen.includes(k)) seen.push(k)
  }
  return seen.sort((a, b) => (a === NO_DOMAIN) - (b === NO_DOMAIN))
}

// Build ReactFlow nodes/edges from the raw graph + which domains are collapsed.
// 도메인 = 접이식 그룹(레인), 서브도메인 페이지 = 그룹 안 자식 노드.
// userPositions: { 'g:domainKey' → {x,y} } — 사용자가 직접 드래그해 옮긴 위치를
// 자동 레이아웃보다 우선 적용한다. 비어 있으면 기본 레인 배치를 그대로 사용.
function buildFlow(graph, collapsed, handlers, colorMap, userPositions = {}) {
  const labelById = {}
  const domainById = {}
  const byDomain = new Map()
  for (const n of graph.nodes) {
    const k = domainKeyOf(n)
    labelById[n.id] = n.label
    domainById[n.id] = k
    if (!byDomain.has(k)) byDomain.set(k, [])
    byDomain.get(k).push(n)
  }
  const active = activeDomainsOf(graph)
  // a node's visible representative: itself when its domain is open, else the group
  const repOf = (id) => (collapsed.has(domainById[id]) ? `g:${domainById[id]}` : id)
  // lane (x order) of a rep, so edges connect on the FACING sides (no outer loop)
  const laneOf = (rep) => active.indexOf(rep.startsWith('g:') ? rep.slice(2) : domainById[rep])
  // an edge is colored by its SOURCE domain so cross-domain links are traceable
  const domainColorOfRep = (rep) =>
    colorMap[rep.startsWith('g:') ? rep.slice(2) : domainById[rep]] || NO_DOMAIN_COLOR
  const repLabel = (id) =>
    id.startsWith('g:') ? `${domainLabel(id.slice(2))} 도메인` : labelById[id] || id

  // ── nodes ──
  const rfNodes = []
  active.forEach((k, laneIdx) => {
    const list = byDomain.get(k)
    const color = colorMap[k]
    const label = domainLabel(k)
    const x = laneIdx * LANE_X
    if (collapsed.has(k)) {
      const pos = userPositions[`g:${k}`] || { x, y: GROUP_TOP }
      rfNodes.push({
        id: `g:${k}`, type: 'domainGroup', position: pos, draggable: true,
        data: { groupKey: k, label, color, count: list.length, internal: 0,
                collapsed: true, onActivate: () => handlers.toggle(k) },
      })
    } else {
      const n = list.length
      const height = HEADER_H + PAD + n * CARD_H + Math.max(0, n - 1) * CARD_GAP + PAD
      const pos = userPositions[`g:${k}`] || { x, y: 0 }
      rfNodes.push({
        // pointerEvents:none → the open lane box never steals hover from the
        // child cards stacked on top of it (the header re-enables it in CSS),
        // which was the source of the child↔group hover flicker.
        // dragHandle limits drag to the header (the only part with pointer
        // events), so the user can grab the group without conflicts with the
        // child wiki cards stacked on top.
        id: `g:${k}`, type: 'domainGroup', position: pos,
        draggable: true, dragHandle: '.phase-group__head',
        style: { width: CARD_W + PAD * 2, height, pointerEvents: 'none' },
        data: { groupKey: k, label, color, count: n, collapsed: false,
                onActivate: () => handlers.toggle(k) },
      })
      list.forEach((node, i) => {
        rfNodes.push({
          id: node.id, type: 'wikiNode', parentNode: `g:${k}`, extent: 'parent',
          position: { x: PAD, y: HEADER_H + PAD + i * (CARD_H + CARD_GAP) },
          style: { width: CARD_W, height: CARD_H },
          data: { label: node.label, onActivate: () => handlers.open(node.id) },
        })
      })
    }
  })

  // ── edges (aggregate to the visible representatives) ──
  const internal = {}
  const agg = new Map()
  for (const e of graph.edges) {
    if (e.from === e.to) continue // self-loop (merged_from 출처) — not drawn
    const s = repOf(e.from)
    const t = repOf(e.to)
    if (s === t) {
      // both ends collapse into the same group → count as an internal link
      internal[domainById[e.from]] = (internal[domainById[e.from]] || 0) + 1
      continue
    }
    const key = `${s}__${t}`
    if (!agg.has(key)) agg.set(key, { source: s, target: t, underlying: [] })
    agg.get(key).underlying.push({
      ...e, fromLabel: labelById[e.from] || e.from, toLabel: labelById[e.to] || e.to,
    })
  }
  for (const node of rfNodes) {
    if (node.type === 'domainGroup' && node.data.collapsed) {
      node.data.internal = internal[node.data.groupKey] || 0
    }
  }

  const rfEdges = [...agg.values()].map((a, i) => {
    const types = [...new Set(a.underlying.map((u) => u.type))]
    const n = a.underlying.length
    const label = types.length === 1
      ? (EDGE_LABELS[types[0]] || '연결') + (n > 1 ? ` (${n})` : '')
      : `관계 (${n})`
    const aggregated = a.source.startsWith('g:') || a.target.startsWith('g:') || n > 1
    const strong = a.underlying.some((u) => u.type === 'conflicts_with' || u.type === 'supersedes')
    const lowOnly = n === 1 && a.underlying[0].confidence === 'low'
    // connect on facing sides: source left of target → source.right → target.left
    const fwd = laneOf(a.source) <= laneOf(a.target)
    const stroke = domainColorOfRep(a.source)
    return {
      id: `e${i}`, source: a.source, target: a.target, label, animated: strong,
      sourceHandle: fwd ? 'sr' : 'sl', targetHandle: fwd ? 'tl' : 'tr',
      markerEnd: { type: MarkerType.ArrowClosed, color: stroke },
      style: { stroke, strokeWidth: 1.6, ...(lowOnly ? { strokeDasharray: '5 4', opacity: 0.55 } : {}) },
      data: { domain: a.source, aggregated, underlying: a.underlying,
              fromLabel: repLabel(a.source), toLabel: repLabel(a.target) },
    }
  })
  return { rfNodes, rfEdges }
}

const onKeyActivate = (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    e.currentTarget.__activate?.()
  }
}

// source+target handles on BOTH sides (ids tl/tr/sl/sr) so an edge can attach to
// the facing side of each node → straight line instead of looping around.
const EdgeHandles = () => (
  <>
    <Handle id="tl" type="target" position={Position.Left} />
    <Handle id="tr" type="target" position={Position.Right} />
    <Handle id="sl" type="source" position={Position.Left} />
    <Handle id="sr" type="source" position={Position.Right} />
  </>
)

function DomainGroupNode({ data }) {
  const activate = (el) => { if (el) el.__activate = data.onActivate }
  const aria = `${data.label} 도메인 · ${data.count}개 · ${data.collapsed ? '펼치기' : '접기'}`
  if (data.collapsed) {
    return (
      <div className="phase-group phase-chip" style={{ borderLeft: `3px solid ${data.color}` }}
           ref={activate} role="button" tabIndex={0} aria-expanded={false}
           aria-label={aria} onKeyDown={onKeyActivate}>
        <EdgeHandles />
        <span className="phase-toggle" aria-hidden="true">▸</span>
        <strong>{data.label}</strong>
        <span className="badge phase-count">{data.count}</span>
        {data.internal > 0 && (
          <span className="phase-internal" title={`그룹 내부 연결 ${data.internal}건`}
                aria-label={`그룹 내부 연결 ${data.internal}건`}>↻{data.internal}</span>
        )}
      </div>
    )
  }
  return (
    <div className="phase-group phase-group--open" style={{ borderTop: `3px solid ${data.color}` }}>
      <EdgeHandles />
      <div className="phase-group__head" ref={activate} role="button" tabIndex={0}
           aria-expanded aria-label={aria} onKeyDown={onKeyActivate}>
        <span className="phase-toggle" aria-hidden="true">▾</span>
        <strong>{data.label}</strong>
        <span className="badge phase-count">{data.count}</span>
      </div>
    </div>
  )
}

function WikiNode({ data }) {
  const activate = (el) => { if (el) el.__activate = data.onActivate }
  return (
    <div className="wiki-node" title={data.label} ref={activate} role="button" tabIndex={0}
         aria-label={`위키 문서 열기: ${data.label}`} onKeyDown={onKeyActivate}>
      <EdgeHandles />
      <span>{data.label}</span>
    </div>
  )
}

// Edge evidence renderer — structured object (new crossref output) or legacy
// string (older edges.jsonl rows). Sections render only when their field is
// present, so a sparse offline/legacy edge still degrades gracefully.
function EvidenceBlock({ evidence }) {
  if (!evidence) {
    return <p className="edge-detail-evidence muted">이 연결에 대한 근거 정보가 없습니다.</p>
  }
  if (typeof evidence === 'string') {
    // legacy flat evidence — show as a single paragraph
    return <p className="edge-detail-evidence">{evidence}</p>
  }
  const { summary, why, anchors, shared, usage, snippet, similarity, distance } = evidence
  const hasAny = summary || why || (anchors && anchors.length) || (shared && shared.length) || usage || snippet
  if (!hasAny && similarity == null) {
    return <p className="edge-detail-evidence muted">이 연결에 대한 근거 정보가 없습니다.</p>
  }
  return (
    <div className="edge-detail-evidence">
      {summary && <p className="evi-summary">{summary}</p>}
      {why && (
        <div className="evi-section">
          <div className="evi-label">연관 사유</div>
          <p className="evi-text">{why}</p>
        </div>
      )}
      {anchors && anchors.length > 0 && (
        <div className="evi-section">
          <div className="evi-label">근거 인용</div>
          {/* 라벨은 *시간* 기준(언제 인입됐는가)이지 그래프 화살표 *방향*이
             아님 — 풀어 쓴 카피와 aria-label로 두 의미를 분리. */}
          <ul className="evi-anchors">
            {anchors.map((a, i) => {
              const isNew = a.side === 'new'
              return (
                <li key={i}>
                  <span className={`evi-side evi-side-${isNew ? 'new' : 'existing'}`}
                        aria-label={isNew ? '방금 적재된 문서에서 인용' : '기존 위키 문서에서 인용'}>
                    {isNew ? '방금 적재' : '기존 위키'}
                  </span>
                  <span className="evi-quote">“{a.quote}”</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      {shared && shared.length > 0 && (
        <div className="evi-section">
          <div className="evi-label">공유 개념</div>
          <div className="evi-chips">
            {shared.map((s, i) => <span key={i} className="evi-chip">{s}</span>)}
          </div>
        </div>
      )}
      {usage && (
        <div className="evi-section evi-usage">
          <span className="evi-label-inline">함께 볼 때</span> {usage}
        </div>
      )}
      {!summary && !why && snippet && (
        // offline path with no LLM rationale — surface the matched chunk text
        <div className="evi-section">
          <div className="evi-label">유사 청크</div>
          <p className="evi-text muted">“{snippet}…”</p>
        </div>
      )}
      {/* signals-only 케이스(LLM 합리화 없음)에는 짧은 캡션을 더해, 사용자가
         "근거 누락"이 아니라 "임베딩 유사도 기반 추천"임을 알 수 있게 함 */}
      {(similarity != null || distance != null) && (
        <>
          {!summary && !why && !(anchors && anchors.length) && !(shared && shared.length) && !usage && !snippet && (
            <div className="evi-label" style={{ marginTop: 10 }}>임베딩 유사도만 표시 · 상세 분석 미수행</div>
          )}
          <div className="evi-signals muted">
            {similarity != null && Number.isFinite(similarity) && (
              <span>의미 유사도 {Math.round(similarity * 100)}%</span>
            )}
            {similarity != null && distance != null && <span> · </span>}
            {distance != null && Number.isFinite(distance) && (
              <span>코사인 거리 {distance.toFixed(2)}</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

const nodeTypes = { domainGroup: DomainGroupNode, wikiNode: WikiNode }

export default function GraphExplorer() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] })
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [collapsed, setCollapsed] = useState(() => new Set())
  const [selected, setSelected] = useState(null)
  const [selEdge, setSelEdge] = useState(null) // selected edge id (kept lit while panel open)
  const [hover, setHover] = useState(null)      // {kind:'node'|'edge', id}
  // 필터: 도메인 숨김(legend 토글) + SDLC 단계 단일 선택(null=전체)
  const [hiddenDomains, setHiddenDomains] = useState(() => new Set())
  const [phaseFilter, setPhaseFilter] = useState(null)
  // 도메인 내부(같은 도메인 두 페이지 간) 연결을 숨겨, 도메인 간 관계만 보고 싶을 때
  const [crossDomainOnly, setCrossDomainOnly] = useState(false)
  // 사용자가 드래그로 옮긴 도메인 그룹 위치. key = 'g:도메인키', value = {x,y}.
  // 자동 레인 레이아웃보다 우선 적용되고 localStorage에 저장돼 새로고침에도 유지된다.
  const POS_LS_KEY = 'wiki-graph-positions:v1'
  const [userPositions, setUserPositions] = useState(() => {
    try { return JSON.parse(localStorage.getItem(POS_LS_KEY) || '{}') } catch { return {} }
  })
  useEffect(() => {
    try { localStorage.setItem(POS_LS_KEY, JSON.stringify(userPositions)) } catch { /* ignore */ }
  }, [userPositions])
  // 드래그 가능함을 한 번만 안내. 첫 드래그가 일어나거나 사용자가 닫으면 영구 숨김.
  const HINT_LS_KEY = 'wiki-graph-drag-hint-dismissed:v1'
  const [hintDismissed, setHintDismissed] = useState(() => {
    try { return localStorage.getItem(HINT_LS_KEY) === '1' } catch { return false }
  })
  const dismissHint = useCallback(() => {
    setHintDismissed(true)
    try { localStorage.setItem(HINT_LS_KEY, '1') } catch { /* ignore */ }
  }, [])
  const onNodeDragStop = useCallback((_, node) => {
    if (!node.id.startsWith('g:')) return // 도메인 그룹만 저장 — 자식 카드 위치는 그룹 상대 좌표
    setUserPositions((p) => ({ ...p, [node.id]: { x: node.position.x, y: node.position.y } }))
    dismissHint() // 첫 드래그가 곧 발견 신호 — 힌트 영구 숨김
  }, [dismissHint])
  const resetPositions = useCallback(() => setUserPositions({}), [])
  const hasUserPositions = Object.keys(userPositions).length > 0
  const showDragHint = !hintDismissed && !hasUserPositions

  const nav = useNavigate()
  const rf = useRef(null)
  const canvasRef = useRef(null)   // for ResizeObserver-driven re-fit

  const load = useCallback(() => {
    setStatus('loading')
    api.graph().then((g) => {
      setGraph(g)
      setSelected(null)
      setHiddenDomains(new Set())
      setPhaseFilter(null)
      // 첫 인상에서 도메인 구조 + 페이지 목록을 한 번에 보여주기 위해 전부 펼친 상태로 시작.
      // 사용자가 그룹 헤더로 개별 접기는 가능.
      setCollapsed(new Set())
      setStatus('ready')
    }).catch(() => setStatus('error'))
  }, [])
  useEffect(() => { load() }, [load])

  // 필터된 그래프: legend로 숨긴 도메인 + 단계 필터 + '도메인 간만' 옵션을
  // 모두 적용. 양 끝 노드가 모두 살아있는 엣지만 남긴다. 필터 없으면 원본 graph
  // 그대로 (참조 안정).
  const visibleGraph = useMemo(() => {
    if (!hiddenDomains.size && !phaseFilter && !crossDomainOnly) return graph
    const nodes = graph.nodes.filter((n) =>
      !hiddenDomains.has(domainKeyOf(n)) &&
      (!phaseFilter || (n.phase || '') === phaseFilter))
    const ids = new Set(nodes.map((n) => n.id))
    // 같은 도메인 여부 판정용: 항상 전체 graph 기준으로 매핑(필터로 가려진
    // 노드가 양 끝일 수도 있어 일관된 도메인 판정을 위해).
    const domByNode = new Map(graph.nodes.map((n) => [n.id, domainKeyOf(n)]))
    const edges = graph.edges.filter((e) => {
      if (!ids.has(e.from) || !ids.has(e.to)) return false
      if (crossDomainOnly && domByNode.get(e.from) === domByNode.get(e.to)) return false
      return true
    })
    return { nodes, edges }
  }, [graph, hiddenDomains, phaseFilter, crossDomainOnly])

  // 단계별 카운트 (필터 칩에 노출). 항상 전체 graph 기준이라 필터를 바꿔도 안 흔들림.
  const phaseCounts = useMemo(() => {
    const m = {}
    for (const n of graph.nodes) m[n.phase || ''] = (m[n.phase || ''] || 0) + 1
    return m
  }, [graph])

  const toggleDomain = useCallback((k) => setHiddenDomains((p) => {
    const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n
  }), [])
  const selectPhase = useCallback((p) => setPhaseFilter((prev) => prev === p ? null : p), [])
  const resetFilters = useCallback(() => {
    setHiddenDomains(new Set()); setPhaseFilter(null); setCrossDomainOnly(false)
  }, [])
  const filtersActive = hiddenDomains.size > 0 || phaseFilter !== null || crossDomainOnly

  const close = useCallback(() => { setSelected(null); setSelEdge(null) }, [])
  useEffect(() => {
    if (!selected) return
    const onKey = (e) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, close])

  const toggle = useCallback((key) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    }), [])
  const open = useCallback((id) => nav(`/wiki?slug=${encodeURIComponent(id)}`), [nav])
  const handlers = useMemo(() => ({ toggle, open }), [toggle, open])

  // colorMap·legend는 전체 graph 기준 — 도메인을 숨겨도 색이 재배정되지 않고
  // legend에는 모든 도메인이 남아 다시 켤 수 있어야 한다.
  const colorMap = useMemo(() => colorMapOf(graph), [graph])
  const flow = useMemo(
    () => buildFlow(visibleGraph, collapsed, handlers, colorMap, userPositions),
    [visibleGraph, collapsed, handlers, colorMap, userPositions],
  )
  const legend = useMemo(
    () => activeDomainsOf(graph).map((k) => ({ key: k, label: domainLabel(k), color: colorMap[k] })),
    [graph, colorMap],
  )

  const focus = hover || (selEdge ? { kind: 'edge', id: selEdge } : null)
  // Hover/selection ONLY emphasizes the focused connection (thicker, brighter
  // edges) — it never dims the rest. On this sparse layout, dimming the other
  // nodes/edges read as "the whole graph disappeared". Nodes are passed through
  // untouched (same array reference), so the node layer can never flicker or
  // vanish on hover; only the handful of connected edges get new style objects.
  const display = useMemo(() => {
    if (!focus) return flow
    const keepE = new Set()
    if (focus.kind === 'edge') keepE.add(focus.id)
    else for (const e of flow.rfEdges)
      if (e.source === focus.id || e.target === focus.id) keepE.add(e.id)
    if (keepE.size === 0) return flow
    const rfEdges = flow.rfEdges.map((e) => {
      if (!keepE.has(e.id)) return e   // untouched → stable identity, no re-render
      const base = e.style?.opacity ?? 1
      // emphasize: thicker + brighter, and solid (drop the low-confidence dash)
      // so a followed connection reads clearly even for a low-conf edge.
      return { ...e, style: { ...e.style, opacity: Math.max(base, 0.95),
                              strokeWidth: 3, strokeDasharray: undefined } }
    })
    return { rfNodes: flow.rfNodes, rfEdges }
  }, [flow, focus])

  // re-fit the viewport whenever groups collapse/expand or filters change so the
  // new content layout stays in view.
  useEffect(() => { rf.current?.fitView({ ...FIT_OPTS, duration: 300 }) },
    [collapsed, hiddenDomains, phaseFilter, crossDomainOnly])

  // Re-fit on container size changes. The canvas is in a flex column that grows
  // after mount; without this, the initial fit ran at a smaller height and the
  // graph stayed crammed at the bottom even after the card settled to its full
  // size. rAF debounce + `alive` flag keep StrictMode-safe and avoid stacking
  // tweens during the LNB collapse/expand transition (instant fit on resize).
  useEffect(() => {
    const el = canvasRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let alive = true, raf = 0
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        if (alive) rf.current?.fitView({ ...FIT_OPTS, duration: 0 })
      })
    })
    ro.observe(el)
    return () => { alive = false; cancelAnimationFrame(raf); ro.disconnect() }
  }, [])

  const onNodeClick = (_, node) => node.data.onActivate?.()
  // idempotent: re-entering the SAME target keeps the previous state object so
  // React bails out of a re-render — prevents hover churn / flicker.
  const setNodeHover = useCallback((_, node) => setHover((p) =>
    p && p.kind === 'node' && p.id === node.id ? p : { kind: 'node', id: node.id }), [])
  const setEdgeHover = useCallback((_, e) => setHover((p) =>
    p && p.kind === 'edge' && p.id === e.id ? p : { kind: 'edge', id: e.id }), [])
  const clearHover = useCallback(() => setHover(null), [])

  return (
    <div className="fill-h">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>지식 그래프</h2>
        <div className="row">
          <span className="badge">
            노드 {visibleGraph.nodes.length}
            {filtersActive && visibleGraph.nodes.length !== graph.nodes.length
              ? ` / ${graph.nodes.length}` : ''}
            {' '}· 연결 {flow.rfEdges.length}
          </span>
          {filtersActive && (
            <button type="button" className="legend-reset" onClick={resetFilters}
                    title="단계·도메인 필터 모두 해제">필터 초기화</button>
          )}
          {hasUserPositions && (
            <button type="button" className="legend-reset" onClick={resetPositions}
                    title="드래그로 옮긴 도메인 그룹 위치를 자동 레이아웃으로 되돌립니다">레이아웃 초기화</button>
          )}
          <button className="icon-btn" onClick={load} title="새로고침" aria-label="새로고침">↻</button>
        </div>
      </div>

      {status === 'ready' && graph.nodes.length > 0 && (
        <>
          {/* SDLC 단계 단일 선택 — '전체'는 phaseFilter=null (활성 표시 없음:
             선택된 phase 칩이 없으면 '전체'가 활성인 의미. 그래서 '전체'는
             reset-역할 anchor 칩으로 항상 동일한 outline-only 톤). */}
          <div className="wf-legend">
            <span className="legend-title">단계</span>
            <button type="button"
                    className="legend-item is-toggle phase-pill phase-all"
                    aria-pressed={phaseFilter === null}
                    title="모든 단계 보기"
                    onClick={() => setPhaseFilter(null)}>
              전체
            </button>
            {PHASE_OPTIONS.map((p) => {
              // n.phase 의 값은 백엔드 wiki frontmatter 의 sdlc_phase 영문 키
              // (requirements/design/implementation/test/deployment/operation)
              // 와 1:1. 키가 어긋나면 모든 카운트가 0이 되어 칩이 모두 disabled.
              const active = phaseFilter === p.key
              const count = phaseCounts[p.key] || 0
              const disabled = count === 0
              // aria-disabled + click guard 로 disabled 칩도 탭 도달·낭독 가능
              return (
                <button type="button" key={p.key}
                        className={`legend-item is-toggle phase-pill${active ? ' is-active' : ''}${disabled ? ' is-empty' : ''}`}
                        aria-pressed={active} aria-disabled={disabled}
                        title={disabled ? `${p.label}: 이 단계 문서 없음` : `${p.label} 단계만 보기`}
                        onClick={() => { if (!disabled) selectPhase(p.key) }}>
                  {p.label}
                  <span className="legend-count">· {count}</span>
                </button>
              )
            })}
          </div>

          {/* 도메인 legend — 항목 클릭 시 해당 도메인 노드/엣지 숨김(토글) */}
          <div className="wf-legend">
            <span className="legend-title">도메인</span>
            {legend.map((d) => {
              const hidden = hiddenDomains.has(d.key)
              return (
                <button type="button" key={d.key}
                        className={`legend-item is-toggle${hidden ? ' is-hidden' : ''}`}
                        aria-pressed={!hidden}
                        title={hidden ? `${d.label} 다시 표시` : `${d.label} 숨기기`}
                        onClick={() => toggleDomain(d.key)}>
                  {/* 도메인은 개방형이라 색을 클래스가 아닌 인라인으로 동적 지정 (유일 지점).
                      숨김 상태에서도 색 정체성을 희미하게 남겨 어느 도메인인지 식별 가능. */}
                  <span className="legend-dot"
                        style={{ background: hidden ? `${d.color}33` : d.color,
                                 borderColor: d.color }} />
                  {d.label}
                </button>
              )
            })}
            {/* '도메인 간 연결만' 옵션 — 같은 도메인 내부 엣지는 가려서 도메인
               레벨 관계만 깔끔하게 본다. 색 활성(grad-soft)로 phase 활성과
               동일한 시각 언어 사용. */}
            <button type="button"
                    className={`legend-item is-toggle option-pill${crossDomainOnly ? ' is-active' : ''}`}
                    aria-pressed={crossDomainOnly}
                    title="같은 도메인 안의 페이지끼리 연결은 숨기고 도메인 간 연결만 보기"
                    onClick={() => setCrossDomainOnly((v) => !v)}>
              <span className="option-mark" aria-hidden="true">{crossDomainOnly ? '✓' : '◻'}</span>
              도메인 간 연결만
            </button>
          </div>
        </>
      )}

      <div ref={canvasRef} className="card grow-canvas"
           style={{ padding: 0, marginTop: 14, position: 'relative' }}>
        {status === 'error' ? (
          <div className="canvas-empty">
            <div className="canvas-empty-ico">⚠️</div>
            <p style={{ color: 'var(--fail)' }}>그래프를 불러오지 못했습니다.</p>
            <button onClick={load}>다시 시도</button>
          </div>
        ) : status === 'loading' && graph.nodes.length === 0 ? (
          <div className="canvas-empty">
            <p className="muted">그래프를 불러오는 중…</p>
          </div>
        ) : graph.nodes.length === 0 ? (
          <div className="canvas-empty">
            <div className="canvas-empty-ico">🕸</div>
            <p className="muted">아직 그래프에 노드가 없습니다.</p>
            <Link to="/ingest">문서 적재하러 가기 →</Link>
          </div>
        ) : visibleGraph.nodes.length === 0 ? (
          <div className="canvas-empty">
            <div className="canvas-empty-ico">🔍</div>
            <p className="muted">필터 조건에 맞는 노드가 없습니다.</p>
            <button type="button" onClick={resetFilters}>필터 초기화</button>
          </div>
        ) : (
          <>
            <ReactFlow
              nodes={display.rfNodes}
              edges={display.rfEdges}
              nodeTypes={nodeTypes}
              nodesDraggable={false}
              fitView
              // maxZoom caps the auto-fit upward so the compact collapsed row
              // doesn't blow up to 200%+. minZoom is left wide so fitView can
              // still zoom OUT enough to show a tall expanded lane in full —
              // otherwise the bottom of a long lane gets clipped off-screen.
              fitViewOptions={FIT_OPTS}
              // wheel zoom-out is held tighter (0.4) than auto-fit's 0.3 so a
              // user can't zoom out far enough to make chip labels unreadable.
              minZoom={0.4}
              maxZoom={1.6}
              onInit={(inst) => { rf.current = inst }}
              onNodeDragStop={onNodeDragStop}
              onNodeClick={onNodeClick}
              onNodeMouseEnter={setNodeHover}
              onNodeMouseLeave={clearHover}
              onEdgeMouseEnter={setEdgeHover}
              onEdgeMouseLeave={clearHover}
              onEdgeClick={(_, e) => { setSelected(e.data); setSelEdge(e.id) }}
              onPaneClick={close}
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              {/* top-left so it never collides with the bottom-left .edge-detail panel */}
              <Controls position="top-left" />
            </ReactFlow>

            {flow.rfEdges.length === 0 && (
              <div className="canvas-hint muted">
                {filtersActive
                  ? '이 필터 범위 안의 연결이 없습니다 · 단계 필터를 풀거나 다른 도메인을 보여주세요'
                  : collapsed.size > 0
                    ? '모든 그룹이 접혀 있습니다 · 그룹 헤더를 눌러 펼쳐 주세요'
                    : '표시할 연결이 없습니다'}
              </div>
            )}

            {showDragHint && (
              <div className="canvas-hint canvas-hint--drag muted" role="status">
                도메인 박스를 끌어 옮길 수 있어요
                <button type="button" className="canvas-hint__close"
                        onClick={dismissHint} aria-label="안내 닫기">✕</button>
              </div>
            )}

            {selected && (
              // tabIndex+autoFocus 로 패널 오픈 시 키보드 포커스가 이동해
              // ESC(useEffect 상단의 keydown 핸들러)·Tab 탐색이 즉시 가능.
              <div className="edge-detail" role="region" aria-label="연결 상세"
                   tabIndex={-1} autoFocus
                   ref={(el) => el?.focus({ preventScroll: true })}>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                  <strong>
                    {selected.aggregated
                      ? '연결 상세'
                      : `${EDGE_LABELS[selected.underlying[0].type] || '연결'} 관계`}
                  </strong>
                  <button className="icon-btn" onClick={close} title="닫기" aria-label="닫기">✕</button>
                </div>
                <div className="edge-detail-path">
                  <span>{selected.fromLabel}</span>
                  <span className="muted"> → </span>
                  <span>{selected.toLabel}</span>
                </div>
                <div className="edge-detail-list">
                  {selected.underlying.map((u, i) => (
                    <div className="edge-detail-item" key={i}>
                      {selected.aggregated && (
                        <div className="edge-detail-sub">{u.fromLabel} → {u.toLabel}</div>
                      )}
                      <div className="row" style={{ gap: 6 }}>
                        <span className="badge">{EDGE_LABELS[u.type] || '연결'}</span>
                        {u.confidence && (
                          <span className={['badge', CONF_CLASS[u.confidence]].filter(Boolean).join(' ')}>
                            {CONF_LABELS[u.confidence] || u.confidence}
                          </span>
                        )}
                      </div>
                      <EvidenceBlock evidence={u.evidence} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
