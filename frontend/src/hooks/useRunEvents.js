import { useEffect, useRef, useState } from 'react'

// Subscribes to the per-run SSE stream and accumulates node states.
// Returns { nodes: {id -> {status, label, summary, duration}}, order, runStatus, result }
export function useRunEvents(runId) {
  const [nodes, setNodes] = useState({})
  const [order, setOrder] = useState([])
  const [runStatus, setRunStatus] = useState('connecting')
  const [result, setResult] = useState(null)
  const orderRef = useRef([])

  useEffect(() => {
    if (!runId) return
    setNodes({})
    setOrder([])
    orderRef.current = []
    setRunStatus('connecting')
    setResult(null)

    const es = new EventSource(`/api/runs/${runId}/events`)

    const onNode = (e) => {
      const d = JSON.parse(e.data)
      if (!orderRef.current.includes(d.node_id)) {
        orderRef.current = [...orderRef.current, d.node_id]
        setOrder(orderRef.current)
      }
      setNodes((prev) => ({
        ...prev,
        [d.node_id]: {
          label: d.node_label,
          status: d.status,
          summary: d.output_summary ?? prev[d.node_id]?.summary,
          duration: d.duration_ms ?? prev[d.node_id]?.duration,
        },
      }))
    }

    es.addEventListener('run_started', () => setRunStatus('running'))
    es.addEventListener('node_update', onNode)
    es.addEventListener('run_completed', (e) => {
      setResult(JSON.parse(e.data))
      setRunStatus('completed')
      es.close()
    })
    es.addEventListener('run_failed', (e) => {
      setResult(JSON.parse(e.data))
      setRunStatus('failed')
      es.close()
    })
    es.onerror = () => {
      setRunStatus((s) => (s === 'completed' || s === 'failed' ? s : 'error'))
      es.close()
    }

    return () => es.close()
  }, [runId])

  return { nodes, order, runStatus, result }
}
