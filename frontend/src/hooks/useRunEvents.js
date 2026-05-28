import { useEffect, useRef, useState } from 'react'

// Subscribes to the per-run SSE stream and accumulates node states.
// Returns { nodes: {id -> {status, label, summary, duration}}, order, runStatus, result }
// flip to false to silence the workflow SSE diagnostics
const DEBUG = true
let _seq = 0
const log = (...a) => { if (DEBUG) console.log('%c[runEvents]', 'color:#818cf8', ...a) }

export function useRunEvents(runId) {
  const [nodes, setNodes] = useState({})
  const [order, setOrder] = useState([])
  const [runStatus, setRunStatus] = useState('connecting')
  const [result, setResult] = useState(null)
  const [source, setSource] = useState(null)
  const orderRef = useRef([])
  const instRef = useRef(null)

  useEffect(() => {
    if (!runId) return
    const inst = ++_seq
    instRef.current = inst
    log(`#${inst} EFFECT SETUP runId=${runId} — resetting state (mount/remount/runId change)`)
    setNodes({})
    setOrder([])
    orderRef.current = []
    setRunStatus('connecting')
    setResult(null)
    setSource(null)

    const es = new EventSource(`/api/runs/${runId}/events`)
    es.onopen = () => log(`#${inst} OPEN readyState=${es.readyState}`)

    const onNode = (e) => {
      const d = JSON.parse(e.data)
      const isNew = !orderRef.current.includes(d.node_id)
      if (isNew) {
        orderRef.current = [...orderRef.current, d.node_id]
        setOrder(orderRef.current)
      }
      setNodes((prev) => ({
        ...prev,
        [d.node_id]: {
          label: d.node_label,
          status: d.status,
          summary: d.output_summary ?? prev[d.node_id]?.summary,
          detail: d.output_detail ?? prev[d.node_id]?.detail,
          duration: d.duration_ms ?? prev[d.node_id]?.duration,
          usesLlm: d.uses_llm ?? prev[d.node_id]?.usesLlm,
        },
      }))
    }

    es.addEventListener('run_started', (e) => {
      log(`#${inst} run_started`)
      setRunStatus('running')
      try { setSource(JSON.parse(e.data).source || null) } catch { /* ignore */ }
    })
    es.addEventListener('node_update', onNode)
    es.addEventListener('run_completed', (e) => {
      log(`#${inst} run_completed → close`)
      setResult(JSON.parse(e.data))
      setRunStatus('completed')
      es.close()
    })
    es.addEventListener('run_failed', (e) => {
      log(`#${inst} run_failed → close`)
      setResult(JSON.parse(e.data))
      setRunStatus('failed')
      es.close()
    })
    es.onerror = () => {
      // CONNECTING → transient; browser auto-reconnects and backend replays history,
      // so we keep state and the canvas rebuilds seamlessly. CLOSED → fatal (e.g. 404).
      log(`#${inst} ERROR readyState=${es.readyState} (${es.readyState === 2 ? 'CLOSED/fatal' : 'CONNECTING/will-retry'})`)
      if (es.readyState === EventSource.CLOSED) {
        setRunStatus((s) => (s === 'completed' || s === 'failed' ? s : 'error'))
      }
    }

    return () => { log(`#${inst} CLEANUP close runId=${runId}`); es.close() }
  }, [runId])

  return { nodes, order, runStatus, result, source }
}
