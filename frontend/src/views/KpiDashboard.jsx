import { useEffect, useState } from 'react'
import { api } from '../api/client.js'

// 상태 → 배지·진행률 톤 매핑. 배지는 디자인 시스템의 .badge.{completed|pending} 토큰을
// 재사용해 다른 화면(병합/충돌 등)의 상태 색과 일관성을 맞춘다.
const STATUS_LABEL = {
  achieved:   { text: '목표 달성',  tone: 'ok',    badge: 'completed' },
  below:      { text: '목표 미달',  tone: 'warn',  badge: 'pending' },
  empty:      { text: '데이터 없음', tone: 'muted', badge: '' },
  unmeasured: { text: '미측정',     tone: 'muted', badge: '' },
}

function deriveStatus(metric) {
  if (metric.status === 'unmeasured') return 'unmeasured'
  if (metric.status === 'empty') return 'empty'
  if (typeof metric.current !== 'number') return 'empty'
  return metric.current >= (metric.target ?? 0) ? 'achieved' : 'below'
}

function formatValue(metric) {
  if (typeof metric.current !== 'number') return '—'
  return `${metric.current}${metric.unit || ''}`
}

export default function KpiDashboard() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ok | error
  const [open, setOpen] = useState(() => new Set())

  useEffect(() => {
    let alive = true
    setStatus('loading')
    api.kpi()
      .then((d) => { if (alive) { setData(d); setStatus('ok') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
  }, [])

  const toggle = (key) => setOpen((s) => {
    const n = new Set(s)
    n.has(key) ? n.delete(key) : n.add(key)
    return n
  })

  if (status === 'loading') {
    return (
      <div className="kpi-wrap">
        <KpiHeader subtitle="불러오는 중…" />
      </div>
    )
  }
  if (status === 'error' || !data) {
    return (
      <div className="kpi-wrap">
        <KpiHeader subtitle="지표를 불러오지 못했습니다." />
        <div className="card kpi-empty">
          백엔드 응답에 실패했어요. 잠시 후 다시 시도해 주세요.
        </div>
      </div>
    )
  }

  const totals = data.totals || {}
  return (
    <div className="kpi-wrap">
      <KpiHeader
        subtitle={`적재 결정 ${totals.ingest_decisions ?? 0}건 · 병합 기록 ${totals.merge_records ?? 0}건 기준`}
      />

      <div className="kpi-grid">
        {data.metrics.map((m) => {
          const st = deriveStatus(m)
          const meta = STATUS_LABEL[st]
          const isOpen = open.has(m.key)
          const progressPct = typeof m.current === 'number'
            ? Math.min(100, (m.current / Math.max(m.target || 1, 0.01)) * 100)
            : 0
          return (
            <article key={m.key} className={`card kpi-card kpi-${meta.tone}`}>
              <header className="kpi-card-head">
                <div className="kpi-name">{m.name}</div>
                <span className={`badge ${meta.badge}`}>{meta.text}</span>
              </header>

              <div className="kpi-values">
                <div className="kpi-current">
                  <span className="kpi-current-num">{formatValue(m)}</span>
                  <span className="kpi-current-label">현재</span>
                </div>
                <div className="kpi-arrow" aria-hidden>→</div>
                <div className="kpi-target">
                  <span className="kpi-target-num">{m.target}{m.unit}</span>
                  <span className="kpi-target-label">목표</span>
                </div>
              </div>

              <div className={`kpi-progress kpi-progress--${meta.tone}`}
                   role="progressbar" aria-label="목표 대비 달성률"
                   aria-valuenow={typeof m.current === 'number' ? m.current : 0}
                   aria-valuemin={0} aria-valuemax={m.target || 100}>
                <div className="kpi-progress-fill"
                     style={{ width: `${progressPct}%` }} />
              </div>

              <p className="kpi-summary muted">{m.summary}</p>

              <button
                type="button"
                className="secondary kpi-toggle"
                aria-expanded={isOpen}
                onClick={() => toggle(m.key)}
              >
                {isOpen ? '산출 근거 접기' : '산출 근거 보기'}
                <span className="kpi-caret" aria-hidden>{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && (
                <section className="kpi-explain" aria-label="산출 근거">
                  <div className="kpi-explain-row">
                    <div className="kpi-explain-label">수식</div>
                    <code className="kpi-formula">{m.formula}</code>
                  </div>

                  <div className="kpi-explain-row">
                    <div className="kpi-explain-label">계산 과정</div>
                    <ol className="kpi-steps">
                      {m.steps.map((s, i) => (
                        <li key={i}>
                          <span className="kpi-step-label">{s.label}</span>
                          <span className="kpi-step-value">{String(s.value)}</span>
                          {s.detail && (
                            <span className="kpi-step-detail muted">{s.detail}</span>
                          )}
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div className="kpi-explain-row">
                    <div className="kpi-explain-label">데이터 소스</div>
                    <ul className="kpi-sources">
                      {(m.sources || []).map((src, i) => (
                        <li key={i}><code>{src}</code></li>
                      ))}
                    </ul>
                  </div>

                  {m.notes && (
                    <div className="kpi-explain-row">
                      <div className="kpi-explain-label">메모</div>
                      <p className="kpi-notes muted">{m.notes}</p>
                    </div>
                  )}
                </section>
              )}
            </article>
          )
        })}
      </div>
    </div>
  )
}

function KpiHeader({ subtitle }) {
  return (
    <header className="kpi-header">
      <h1 className="kpi-title">서비스 KPI 대시보드</h1>
      <p className="kpi-subtitle muted">
        프로젝트 기획 단계에서 정한 4개 핵심 지표의 현재 수준과 산출 근거를 확인합니다.
        {subtitle && <> · {subtitle}</>}
      </p>
    </header>
  )
}
