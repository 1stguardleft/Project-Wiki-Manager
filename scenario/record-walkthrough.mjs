// Project Wiki Manager — 자동 워크스루 녹화 (Playwright recordVideo).
// 사용: `node scenario/record-walkthrough.mjs` (백엔드/프론트가 떠 있어야 함)
// 산출: demo-recordings/walkthrough-{stamp}.webm + .srt + scenario/shots/*.png
//
// 본 스크립트는 시나리오/시연영상_녹화계획_v2.md 의 Scene A~F 를 그대로 따른다.
// 자막 계층은 옵션 C(burn-in + SRT 동시) — 영상은 자족, .srt 는 추후 재편집용.
//
// 옵션 환경변수
//   WALK_SKIP_REBUILD=1   녹화 전 /api/wiki/rebuild-crossref 호출을 건너뜀
//   WALK_FRONTEND, WALK_BACKEND  주소 오버라이드 (기본 5173 / 8000)

import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import pwt from '/home/lstguardleft/workspace/Project-Wiki-Manager/frontend/node_modules/playwright-core/index.js'
const { chromium } = pwt

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FRONTEND = process.env.WALK_FRONTEND || 'http://localhost:5173'
const BACKEND = process.env.WALK_BACKEND || 'http://127.0.0.1:8000'
const STAMP = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12)
const VIDEO_DIR = path.join(ROOT, 'scenario', '.video-tmp')
const SHOTS_DIR = path.join(ROOT, 'scenario', 'shots')
const OUT_DIR = path.join(ROOT, 'demo-recordings')
const EDGES_FILE = path.join(ROOT, 'wiki', 'graph', 'edges.jsonl')
const LOG_FILE = '/tmp/walkthrough.log'

await fs.mkdir(VIDEO_DIR, { recursive: true })
await fs.mkdir(SHOTS_DIR, { recursive: true })
await fs.mkdir(OUT_DIR, { recursive: true })
// 시작 전 .video-tmp의 잔여 webm 제거 — 이전 실행이 비정상 종료해 남긴
// 파일을 신규 산출물로 오인해 옮기는 사고 방지(2026-05-28 회귀 경험)
for (const f of (await fs.readdir(VIDEO_DIR))) {
  if (f.endsWith('.webm')) await fs.rm(path.join(VIDEO_DIR, f)).catch(() => {})
}

const logLines = []
const log = (s) => { console.log(s); logLines.push(`[${new Date().toISOString()}] ${s}`) }

// ── 데모 엣지 (Scene E 의 구조화 evidence 패널 보장용. 녹화 후 자동 회수) ──
const demoEdge = {
  from: '고객-관리-고객-기본정보-요구사항-1차',
  to:   '상품-관리-상품-분류-구현-1차',
  type: 'relates_to', confidence: 'medium',
  evidence: {
    summary: '[DEMO] 고객 관심 카테고리와 상품 분류 사전이 동일 코드 체계',
    why: '신규 고객 기본정보 요구사항은 가입 시 관심 상품 카테고리를 수집하며, 상품 분류 구현은 카테고리 코드 사전을 정의·관리한다. 양측은 동일 CATEGORY_CODE 사전을 공유하므로 사전 변경이 발생하면 함께 갱신해야 한다.',
    anchors: [
      { side: 'new',      quote: '관심 상품 카테고리는 최대 5개까지 선택 (CATEGORY_CODE 사전 기반)' },
      { side: 'existing', quote: '상품 분류 코드는 CATEGORY_CODE 표준에 따라 4자리로 부여한다' },
    ],
    shared: ['CATEGORY_CODE', '상품 카테고리 분류', '사전 동기화'],
    usage: '카테고리 분류 체계가 바뀔 때 두 문서를 함께 검토하세요',
    similarity: 0.74, distance: 0.26,
  },
}
const demoTag = '[DEMO]'
const readEdges = async () => (await fs.readFile(EDGES_FILE, 'utf-8')).split('\n').filter(Boolean)
const writeEdges = async (lines) => fs.writeFile(EDGES_FILE, lines.join('\n') + '\n', 'utf-8')
const injectDemo = async () => {
  const lines = await readEdges()
  const filtered = lines.filter((l) => {
    try { const ev = JSON.parse(l).evidence; return !(ev && typeof ev === 'object' && (ev.summary || '').includes(demoTag)) }
    catch { return true }
  })
  filtered.push(JSON.stringify(demoEdge))
  await writeEdges(filtered)
  log('demo edge injected')
}
const removeDemo = async () => {
  const lines = await readEdges()
  const filtered = lines.filter((l) => {
    try { const ev = JSON.parse(l).evidence; return !(ev && typeof ev === 'object' && (ev.summary || '').includes(demoTag)) }
    catch { return true }
  })
  await writeEdges(filtered)
  log('demo edge removed')
}

// ── 사전 처리: 누적 코퍼스 기준으로 상호참조 일괄 재생성 ──────────────────
// 기본 SKIP — 페이지 수×LLM 호출이라 분 단위로 길어진다(이전 회차에서 fetch가
// 끊긴 사고 경험). 그래프가 비어 있으면 WALK_DO_REBUILD=1 로 켜서 사용.
async function rebuildCrossref() {
  if (process.env.WALK_DO_REBUILD !== '1') {
    log('rebuild-crossref: SKIPPED (default — set WALK_DO_REBUILD=1 to enable)')
    return
  }
  log('rebuild-crossref: requesting (may take a few minutes on large wikis)...')
  const t0 = Date.now()
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), 600_000)  // 10분 안전 한도
  try {
    const r = await fetch(`${BACKEND}/api/wiki/rebuild-crossref`,
      { method: 'POST', signal: ctl.signal })
    const data = await r.json()
    log(`rebuild-crossref ✓ ${Math.round((Date.now() - t0) / 1000)}s: ` +
        `pages_updated=${data.pages_updated} edges_added=${data.edges_added} edges_removed=${data.edges_removed}`)
  } catch (e) {
    log(`rebuild-crossref FAILED: ${e.message} (continuing anyway)`)
  } finally { clearTimeout(timer) }
}

// ── 자막/타이틀 시스템 (burn-in + SRT 동시 기록) ──────────────────────────
let videoT0 = 0                              // 녹화 시작 기준 시각 (ms)
let captionCur = { text: '', start: -1 }     // 현재 노출 중인 캡션
const srtEntries = []                        // SRT 출력 버퍼

const fmtSrt = (ms) => {
  const t = Math.max(0, ms | 0)
  const h = String(Math.floor(t / 3600000)).padStart(2, '0')
  const m = String(Math.floor(t / 60000) % 60).padStart(2, '0')
  const s = String(Math.floor(t / 1000) % 60).padStart(2, '0')
  const u = String(t % 1000).padStart(3, '0')
  return `${h}:${m}:${s},${u}`
}
const nowRel = () => Date.now() - videoT0
const flushCaption = () => {
  if (captionCur.start >= 0 && captionCur.text) {
    const end = nowRel()
    if (end - captionCur.start >= 400) {     // <0.4s 라인은 SRT에 안 남김
      srtEntries.push({ start: captionCur.start, end, text: captionCur.text })
    }
  }
  captionCur = { text: '', start: -1 }
}

const ensureOverlayCss = async (page) => {
  // 매 페이지마다 한 번 주입 (이미 있으면 noop)
  await page.evaluate(() => {
    if (document.getElementById('__walk_css')) return
    const s = document.createElement('style')
    s.id = '__walk_css'
    s.textContent = `
      .__walk_caption {
        position: fixed; left: 50%; bottom: 64px; transform: translateX(-50%);
        z-index: 999998; max-width: 84%; padding: 14px 28px; border-radius: 8px;
        background: rgba(0,0,0,.82); color: #fff; font-size: 24px;
        font-weight: 500; line-height: 1.5; text-align: center;
        letter-spacing: .2px; opacity: 0; transition: opacity .22s ease;
        box-shadow: 0 8px 28px rgba(0,0,0,.6);
        font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR", sans-serif;
      }
      .__walk_caption.show { opacity: 1; }
      /* Persistent scenario badge — 우측 상단에 SC-XXX · 시나리오명 상시 표시 */
      /* "엄청 크게, 한 눈에 띄게" 요구사항(2026-05-28) — 폰트 26px + 강조 테두리/그림자 */
      .__walk_scbadge {
        position: fixed; top: 28px; right: 32px; z-index: 999996;
        padding: 16px 30px 16px 24px; border-radius: 999px;
        background: rgba(8,10,18,.88); color: #f3f4f8;
        border: 1.5px solid rgba(193, 132, 252, .45);
        font-size: 26px; font-weight: 700; letter-spacing: .3px;
        opacity: 0; transition: opacity .22s ease;
        box-shadow: 0 12px 36px rgba(0,0,0,.65), 0 0 0 1px rgba(255,255,255,.06) inset;
        font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR", sans-serif;
        display: inline-flex; align-items: center; gap: 16px;
      }
      .__walk_scbadge.show { opacity: 1; }
      .__walk_scbadge .sc-id-tag {
        font-weight: 800; letter-spacing: 3px; font-size: 26px;
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
        -webkit-background-clip: text; background-clip: text; color: transparent;
      }
      .__walk_scbadge .sc-sep { opacity: .35; font-weight: 400; }
      /* 클릭/선택 직전 0.7s 동안 대상 요소를 보라색 outline 으로 깜빡 — */
      /* 헤드리스라 마우스 커서가 안 보이므로 "지금 무엇이 선택됐는가" 를 시청자에게 알리는 단서 */
      .__walk_flash {
        pointer-events: none; position: fixed; z-index: 999995;
        border-radius: 8px;
        box-shadow:
          0 0 0 3px rgba(193, 132, 252, .95),
          0 0 24px 8px rgba(193, 132, 252, .55),
          0 0 4px 1px rgba(255, 255, 255, .6) inset;
        animation: __walk_flash_anim 720ms cubic-bezier(.2,.6,.2,1) forwards;
      }
      @keyframes __walk_flash_anim {
        0%   { transform: scale(1);     opacity: 1; }
        60%  { transform: scale(1.02);  opacity: .95; }
        100% { transform: scale(1.06);  opacity: 0; }
      }
      /* Sustain — flash 가 한 번 깜빡하는 데 비해 sustain 은 다음 sustain/clear */
      /* 가 호출될 때까지 *지속* 강조. 자막을 띄우는 동안 어느 노드가 설명 대상인지 */
      /* 시청자가 계속 알 수 있도록(특히 SC-004 에이전트 순차 설명). */
      .__walk_sustain {
        pointer-events: none; position: fixed; z-index: 999994;
        border-radius: 12px;
        box-shadow:
          0 0 0 3px rgba(193, 132, 252, .95),
          0 0 28px 10px rgba(193, 132, 252, .55);
        animation: __walk_sustain_pulse 1.8s ease-in-out infinite;
      }
      @keyframes __walk_sustain_pulse {
        0%, 100% { box-shadow: 0 0 0 3px rgba(193,132,252,.95), 0 0 28px 10px rgba(193,132,252,.55); }
        50%      { box-shadow: 0 0 0 3.5px rgba(193,132,252,1), 0 0 38px 14px rgba(193,132,252,.8); }
      }
      .__walk_card {
        position: fixed; inset: 0; z-index: 999999; display: flex;
        align-items: center; justify-content: center; flex-direction: column;
        background: linear-gradient(135deg, rgba(8,10,18,.96), rgba(22,26,41,.96));
        color: #fff; text-align: center; opacity: 0; transition: opacity .28s ease;
        font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR", sans-serif;
      }
      .__walk_card.show { opacity: 1; }
      .__walk_card .title {
        font-size: 50px; font-weight: 800; letter-spacing: -.6px; margin-bottom: 14px;
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
        -webkit-background-clip: text; background-clip: text; color: transparent;
      }
      .__walk_card .subtitle { font-size: 19px; color: #eceef6; font-weight: 400; opacity: .92; }
      /* Scenario start cards: "SC-001" / 시나리오명 / 상황·목표 요약 */
      .__walk_card .sc-id {
        font-size: 22px; font-weight: 700; letter-spacing: 4px; opacity: .9;
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
        -webkit-background-clip: text; background-clip: text; color: transparent;
        margin-bottom: 10px;
      }
      .__walk_card .sc-name {
        font-size: 38px; font-weight: 800; letter-spacing: -.4px;
        color: #fff; margin-bottom: 20px;
      }
      .__walk_card .sc-body {
        font-size: 17px; line-height: 1.65; color: #d6d9e3;
        max-width: 760px; font-weight: 400; white-space: pre-line;
      }
      .__walk_chapter {
        position: fixed; top: 26px; left: 50%; transform: translateX(-50%);
        z-index: 999997; padding: 6px 18px; border-radius: 999px;
        background: rgba(0,0,0,.70); color: #fff; font-size: 13px;
        font-weight: 600; letter-spacing: 1.1px;
        opacity: 0; transition: opacity .2s ease;
        font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR", sans-serif;
      }
      .__walk_chapter.show { opacity: 1; }`
    document.head.appendChild(s)
  })
}

const titleCard = async (page, title, subtitle, holdMs = 4500, subtitleAbove = false) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ title, subtitle, subtitleAbove }) => {
    document.querySelectorAll('.__walk_card').forEach((e) => e.remove())
    const el = document.createElement('div'); el.className = '__walk_card'
    const t = document.createElement('div'); t.className = 'title'; t.textContent = title
    const s = subtitle
      ? Object.assign(document.createElement('div'), { className: 'subtitle', textContent: subtitle })
      : null
    if (s && subtitleAbove) {
      // 작은 줄을 큰 줄 위에 두는 클로징 변형 — title 기본 margin-bottom 을
      // 끄고, 두 줄 사이 간격은 subtitle 의 margin-bottom 으로 옮긴다.
      s.style.marginBottom = '14px'
      t.style.marginBottom = '0'
      el.appendChild(s); el.appendChild(t)
    } else {
      el.appendChild(t)
      if (s) el.appendChild(s)
    }
    document.body.appendChild(el)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { title, subtitle: subtitle || '', subtitleAbove })
  await page.waitForTimeout(holdMs)
  await page.evaluate(() => {
    document.querySelectorAll('.__walk_card').forEach((el) => {
      el.classList.remove('show')
      setTimeout(() => el.remove(), 320)
    })
  })
  await page.waitForTimeout(350)
}

// 클릭/선택 직전 호출 — 대상 요소 위에 같은 크기의 보라색 글로우 오버레이를
// 띄워 0.7s 동안 자연스럽게 깜빡인다. 헤드리스라 마우스 커서가 안 보이므로
// 시청자에게 "지금 이 요소가 선택됐다" 는 신호를 준다.
// 보통 패턴: `await flash(page, locator); await locator.click()`
const flash = async (page, locator) => {
  await ensureOverlayCss(page)
  let handle
  try { handle = await locator.elementHandle({ timeout: 1500 }) } catch { handle = null }
  if (!handle) return
  await page.evaluate((el) => {
    if (!el) return
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) return
    const fx = document.createElement('div')
    fx.className = '__walk_flash'
    fx.style.left   = `${r.left - 4}px`
    fx.style.top    = `${r.top - 4}px`
    fx.style.width  = `${r.width + 8}px`
    fx.style.height = `${r.height + 8}px`
    document.body.appendChild(fx)
    setTimeout(() => fx.remove(), 760)
  }, handle)
  await page.waitForTimeout(380)  // 클릭 전에 시청자가 글로우를 인지할 시간
}

// 지속 강조 — sustainHighlight 가 호출될 때마다 이전 강조는 제거되고
// 새 위치에 보라색 펄스 outline 이 *지속*된다. clearSustain 으로 명시 해제.
// 자막이 떠 있는 동안 강조 대상이 무엇인지 시청자에게 계속 알려주는 용도.
const sustainHighlight = async (page, locator) => {
  await ensureOverlayCss(page)
  let handle
  try { handle = await locator.elementHandle({ timeout: 1500 }) } catch { handle = null }
  if (!handle) return
  await page.evaluate((el) => {
    document.querySelectorAll('.__walk_sustain').forEach((e) => e.remove())
    if (!el) return
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) return
    const fx = document.createElement('div')
    fx.className = '__walk_sustain'
    fx.style.left   = `${r.left - 4}px`
    fx.style.top    = `${r.top - 4}px`
    fx.style.width  = `${r.width + 8}px`
    fx.style.height = `${r.height + 8}px`
    document.body.appendChild(fx)
  }, handle)
}
const clearSustain = async (page) => {
  await page.evaluate(() => {
    document.querySelectorAll('.__walk_sustain').forEach((e) => e.remove())
  })
}

// 우측 상단의 상시 시나리오 뱃지(SC-ID + 시나리오명). page.goto 마다 DOM이
// 사라지므로 localStorage 에 현재 시나리오를 저장하고, addInitScript 에서
// DOMContentLoaded 시점에 자동 복원하도록 한다.
const setScenarioBadge = async (page, id, name) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ id, name }) => {
    // 저장(다음 페이지에서 init script 가 읽음)
    if (id && name) localStorage.setItem('__walkScBadge', JSON.stringify({ id, name }))
    else localStorage.removeItem('__walkScBadge')
    // 현재 페이지의 뱃지 갱신/제거
    let el = document.querySelector('.__walk_scbadge')
    if (!id || !name) {
      if (el) { el.classList.remove('show'); setTimeout(() => el.remove(), 280) }
      return
    }
    if (!el) {
      el = document.createElement('div'); el.className = '__walk_scbadge'
      document.body.appendChild(el)
    }
    el.innerHTML = ''
    const idTag = document.createElement('span'); idTag.className = 'sc-id-tag'; idTag.textContent = id
    const sep = document.createElement('span'); sep.className = 'sc-sep'; sep.textContent = '·'
    const nm = document.createElement('span'); nm.textContent = name
    el.appendChild(idTag); el.appendChild(sep); el.appendChild(nm)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { id: id || null, name: name || null })
}

// 시나리오 시작 카드 — documents/시나리오수립.md 의 SC-XXX 시나리오와 1:1.
// `body` 안의 줄바꿈(\n)은 sc-body 의 white-space:pre-line 로 그대로 보임.
const scenarioCard = async (page, id, name, body, holdMs = 4200) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ id, name, body }) => {
    document.querySelectorAll('.__walk_card').forEach((e) => e.remove())
    const el = document.createElement('div'); el.className = '__walk_card'
    const idEl = document.createElement('div'); idEl.className = 'sc-id'; idEl.textContent = id
    const nameEl = document.createElement('div'); nameEl.className = 'sc-name'; nameEl.textContent = name
    const bodyEl = document.createElement('div'); bodyEl.className = 'sc-body'; bodyEl.textContent = body
    el.appendChild(idEl); el.appendChild(nameEl); el.appendChild(bodyEl)
    document.body.appendChild(el)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { id, name, body })
  await page.waitForTimeout(holdMs)
  await page.evaluate(() => {
    document.querySelectorAll('.__walk_card').forEach((el) => {
      el.classList.remove('show')
      setTimeout(() => el.remove(), 320)
    })
  })
  await page.waitForTimeout(360)
}

const chapter = async (page, text, holdMs = 1800) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ text }) => {
    document.querySelectorAll('.__walk_chapter').forEach((e) => e.remove())
    const el = document.createElement('div'); el.className = '__walk_chapter'
    el.textContent = text; document.body.appendChild(el)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { text })
  await page.waitForTimeout(holdMs)
  await page.evaluate(() => {
    document.querySelectorAll('.__walk_chapter').forEach((el) => {
      el.classList.remove('show')
      setTimeout(() => el.remove(), 280)
    })
  })
  await page.waitForTimeout(200)
}

const caption = async (page, text, holdMs = 3500) => {
  await ensureOverlayCss(page)
  // 직전 캡션 닫고 SRT 기록
  flushCaption()
  captionCur = { text, start: nowRel() }
  await page.evaluate(({ text }) => {
    let el = document.querySelector('.__walk_caption')
    if (!el) { el = document.createElement('div'); el.className = '__walk_caption'; document.body.appendChild(el) }
    el.textContent = text
    requestAnimationFrame(() => el.classList.add('show'))
  }, { text })
  if (holdMs > 0) await page.waitForTimeout(holdMs)
}
const clearCaption = async (page) => {
  flushCaption()
  await page.evaluate(() => {
    const el = document.querySelector('.__walk_caption')
    if (el) el.classList.remove('show')
  })
  await page.waitForTimeout(180)
}

const shot = async (page, name) => {
  await page.screenshot({ path: path.join(SHOTS_DIR, `${name}.png`), fullPage: false }).catch(() => {})
}

// ──────────────────────────────────────────────────────────────────────────
// 메인
// ──────────────────────────────────────────────────────────────────────────
await rebuildCrossref()
await injectDemo()

const browser = await chromium.launch({ headless: true })
// 1280 폭에서는 wiki 3-컬럼(tree 340 + 1fr + rail 300) 본문이 ~430px로 좁아져
// "연관 도메인" 5-컬럼 표가 글자 단위로 짜부라짐(scene-C-wiki-autosection 회귀,
// 2026-05-28). 같은 16:10 비율을 유지하면서 본문 폭을 ~590px까지 확보.
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: VIDEO_DIR, size: { width: 1440, height: 900 } },
})
// page.goto 마다 DOM이 비워져 시나리오 뱃지가 사라지지 않게, localStorage 에서
// 현재 시나리오를 읽어 자동 복원하는 init script 를 컨텍스트에 등록.
// ensureOverlayCss 보다 먼저 실행될 수 있으므로 인라인 스타일로 최소 모양을 보장한다.
await context.addInitScript(() => {
  const restore = () => {
    try {
      const raw = localStorage.getItem('__walkScBadge')
      if (!raw) return
      const { id, name } = JSON.parse(raw)
      if (!id || !name || !document.body) return
      if (document.querySelector('.__walk_scbadge')) return
      const el = document.createElement('div')
      el.className = '__walk_scbadge'
      el.style.cssText =
        'position:fixed;top:28px;right:32px;z-index:999996;' +
        'padding:16px 30px 16px 24px;border-radius:999px;' +
        'background:rgba(8,10,18,.88);color:#f3f4f8;' +
        'border:1.5px solid rgba(193,132,252,.45);' +
        'font-size:26px;font-weight:700;letter-spacing:.3px;opacity:1;' +
        'box-shadow:0 12px 36px rgba(0,0,0,.65),0 0 0 1px rgba(255,255,255,.06) inset;' +
        'font-family:-apple-system,"Apple SD Gothic Neo","Segoe UI","Noto Sans CJK KR",sans-serif;' +
        'display:inline-flex;align-items:center;gap:16px;'
      const idTag = document.createElement('span'); idTag.textContent = id
      idTag.style.cssText =
        'font-weight:800;letter-spacing:3px;font-size:26px;' +
        'background:linear-gradient(135deg,#818cf8 0%,#c084fc 100%);' +
        '-webkit-background-clip:text;background-clip:text;color:transparent;'
      const sep = document.createElement('span'); sep.textContent = '·'
      sep.style.cssText = 'opacity:.35;font-weight:400;'
      const nm = document.createElement('span'); nm.textContent = name
      el.appendChild(idTag); el.appendChild(sep); el.appendChild(nm)
      document.body.appendChild(el)
    } catch {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', restore)
  } else {
    restore()
  }
})

videoT0 = Date.now()    // recordVideo 시작 시각 — 모든 SRT 타임코드의 기준
const page = await context.newPage()
const errs = []
page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()) })

// IngestView 폴더 네비게이션 헬퍼.
// loadFiles 가 fire-and-forget fetch라 race 가능 — 빵부스러기 마지막 세그먼트가
// 라벨로 바뀔 때까지 명시적으로 대기. 못 찾으면 throw 해서 잘못된 화면 캡처 방지.
async function enterFolder(page, label) {
  const row = page.locator('tr.src-row.dir-row', { hasText: label }).first()
  if (!(await row.count())) {
    throw new Error(`folder row not found at current level: ${label}`)
  }
  await flash(page, row)
  await row.click()
  await page.waitForFunction((target) => {
    const crumbs = document.querySelectorAll('.breadcrumb .crumb')
    const last = crumbs[crumbs.length - 1]
    return !!(last && last.textContent && last.textContent.trim() === target)
  }, label, { timeout: 8000 })
  log(`  entered folder: ${label}`)
}

// 워크플로우 노드 클릭(라벨 부분일치). 클릭 후 상세 패널이 업데이트될 시간을 준다.
async function clickNodeByLabel(page, label) {
  const n = page.locator('.react-flow__node', { hasText: label }).first()
  if (await n.count()) {
    await flash(page, n)
    await n.evaluate((el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    log(`  clicked node: ${label}`)
    await page.waitForTimeout(2500)
  } else {
    log(`  node not found: ${label}`)
  }
}

// SC-004 전용 — 노드를 클릭해 우측 상세 패널을 갱신하고, 같은 노드에
// 보라색 펄스 outline 을 *지속* 강조한다(다음 focusAgent 또는 clearSustain 까지).
// 호출 직후 caption() 을 띄우면, 자막이 떠 있는 동안 어느 에이전트가 설명 대상인지
// 시청자가 분명히 알 수 있다("자막에 맞춰 에이전트 강조" 요구사항).
//
// 주의: sustainHighlight 은 *클릭 + scrollIntoView 후* 에 호출한다. React Flow 가
// 클릭 시 선택 상태(테두리/스케일) 재렌더 + 패널 갱신으로 노드를 미세하게 밀어내,
// 클릭 전에 캡처한 좌표가 어긋났기 때문(sc-004-verify.png 회귀, 2026-05-28).
async function focusAgent(page, label) {
  const n = page.locator('.react-flow__node', { hasText: label }).first()
  if (!(await n.count())) { log(`  agent node not found: ${label}`); return }
  await n.evaluate((el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  // 우측 상세 패널 갱신 + React Flow 선택 상태 재렌더가 모두 settle 될 시간
  await page.waitForTimeout(420)
  // 노드가 일부 잘려 있어도 좌표가 어긋나지 않게 화면 중앙으로 끌어옴
  await n.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' })).catch(() => {})
  await page.waitForTimeout(180)
  await sustainHighlight(page, n)
  log(`  focused agent: ${label}`)
}

try {
  // ── Intro: 전체 타이틀 카드 ──────────────────────────────────────────────
  await page.goto(`${FRONTEND}/ingest`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(800)
  await titleCard(page,
    'Project Wiki Manager',
    'LLM 멀티 에이전트가 자동으로 유지하는 위키',
    5000)

  // ──────────────────────────────────────────────────────────────────────
  // SC-001 : 단일 문서 적재 → 위키 페이지 자동 생성
  // ──────────────────────────────────────────────────────────────────────
  log('SC-001: 단일 문서 적재 → 위키 페이지 자동 생성')
  await setScenarioBadge(page, 'SC-001', '단일 문서 적재 → 위키 페이지 자동 생성')
  await chapter(page, 'SC-001 · 단일 문서 적재 → 위키 페이지 자동 생성')
  await scenarioCard(page, 'SC-001',
    '단일 문서 적재 → 위키 페이지 자동 생성',
    '멀티 에이전트 파이프라인이 SDLC 단계와 도메인을 분류해 위키 페이지를 자동으로 생성합니다.')
  await caption(page, '분산된 개발 산출물을 한 번의 적재 요청으로 멀티 에이전트 파이프라인에 투입합니다.', 4200)
  await shot(page, 'sc-001-ingest')

  // 2차/01-요구사항/고객관리/고객검색/고객검색.md — 1차 이미 적재돼 있어
  // 자연스럽게 *병합* 경로를 거친다(SC-002 연결).
  for (const seg of ['2차', '01-요구사항', '고객관리', '고객검색']) {
    await enterFolder(page, seg)
  }
  const fileRow = page.locator('tr.src-row:not(.dir-row)', { hasText: '고객검색.md' }).first()
  if (!(await fileRow.count())) {
    throw new Error('file row not found in current folder: 고객검색.md')
  }
  await flash(page, fileRow)
  await fileRow.click()
  const startBtn = page.locator('button', { hasText: /선택.*적재/ }).first()
  if (!(await startBtn.count())) throw new Error('start button not found')
  await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll('button'))
    const b = btns.find((el) => /선택.*적재/.test(el.textContent || ''))
    return !!(b && !b.disabled)
  }, null, { timeout: 5000 })
  // 충돌 정책 select — 네 옵션을 모두 보여주기 위해 값을 순차로 교체.
  // (네이티브 select 의 dropdown 은 OS 가 그려서 영상에 안 잡히므로, 표시 텍스트를 직접 갈아 가며 노출)
  const policySelect = page.locator('select').first()
  await flash(page, policySelect)
  await caption(page, '충돌 정책은 문서 단위로 지정합니다. LLM 자동 병합, 수동 검토 보존, 신규 우선, 기존 우선 — 네 가지 옵션을 제공합니다.', 0)
  for (const v of ['manual', 'prefer_incoming', 'prefer_existing', 'llm_merge']) {
    await policySelect.selectOption(v)
    await page.waitForTimeout(1300)
  }
  await page.waitForTimeout(400)
  await flash(page, startBtn)
  await startBtn.click()
  // 이미 분석된 문서면 "재분석 확인" 패널 자동 통과
  const reConfirmBtn = page.locator('.reingest-confirm button', { hasText: '재분석 진행' }).first()
  try {
    await reConfirmBtn.waitFor({ state: 'visible', timeout: 1500 })
    await flash(page, reConfirmBtn)
    await reConfirmBtn.click()
    log('  re-ingest confirmed')
  } catch { /* 신규 문서면 패널이 안 뜸 */ }
  await page.waitForURL(/\/runs\//, { timeout: 15000 })
  // 이후 SC-004 에서 다시 돌아오기 위해 run_id 보관
  const runUrl = page.url()
  const runId = runUrl.match(/\/runs\/([^/?#]+)/)?.[1] || null
  log(`  run_id: ${runId}`)
  // SC-001 에서는 워크플로우/에이전트 상세 설명은 하지 않는다 — SC-004 에서 따로 다룸.
  // 여기서는 "워크플로우를 통해 문서가 적재되는 모습" 만 짧게 보여 줌.
  await page.waitForTimeout(5000)  // 파이프라인이 몇 단계 진행돼 동작감이 느껴질 정도만
  await caption(page, '문서가 파이프라인을 따라 처리됩니다. 각 에이전트의 세부 역할은 시나리오 4에서 다룹니다.', 5000)
  await shot(page, 'sc-001-pipeline')

  // ──────────────────────────────────────────────────────────────────────
  // SC-002 : 중복·충돌 문서 적재 → LLM 자동 병합
  // ──────────────────────────────────────────────────────────────────────
  log('SC-002: 중복·충돌 문서 적재 → LLM 자동 병합')
  await setScenarioBadge(page, 'SC-002', '중복·충돌 문서 적재 → LLM 자동 병합')
  await chapter(page, 'SC-002 · 중복·충돌 문서 적재 → LLM 자동 병합')
  await scenarioCard(page, 'SC-002',
    '중복·충돌 문서 적재 → LLM 자동 병합',
    '신규·기존 문서의 의미 관계를 LLM이 판정하고, 충돌 정책에 따라 한 페이지로 자동 병합합니다.')
  await caption(page, '벡터 유사도 검색이 동일 주제의 기존 페이지를 식별하면, 파이프라인이 충돌판정·병합 단계를 자동으로 활성화합니다.', 5500)
  await clickNodeByLabel(page, '충돌판정')
  await shot(page, 'sc-002-conflict')
  await caption(page, 'LLM이 두 문서의 의미 관계를 보강·중복·모순·구체화 네 가지로 판별한 뒤, 단일 페이지로 통합합니다.', 6200)
  await clickNodeByLabel(page, '병합')
  await shot(page, 'sc-002-merge')
  await caption(page, '병합 직후 누락검토 단계가 양쪽 본문의 커버리지를 정량 평가하며, 임계값 미달 시 병합으로 1회 자동 재진입합니다.', 0)
  await page.waitForFunction(() => {
    const t = document.body.innerText
    return /완료/.test(t) || !!document.querySelector('a[href*="/wiki?slug"]')
  }, { timeout: 90000 }).catch(() => log('  run_completed not detected (timeout)'))
  await page.waitForTimeout(1200)
  await shot(page, 'sc-002-pipeline-done')

  // ──────────────────────────────────────────────────────────────────────
  // SC-003 : 위키 검색 및 질의응답
  // ──────────────────────────────────────────────────────────────────────
  log('SC-003: 위키 검색 및 질의응답')
  await setScenarioBadge(page, 'SC-003', '위키 검색 및 질의응답')
  await chapter(page, 'SC-003 · 위키 검색 및 질의응답')
  await scenarioCard(page, 'SC-003',
    '위키 검색 및 질의응답',
    '하이브리드 검색(BM25 + 벡터)으로 관련 페이지를 찾고, 자연어 질의응답으로 근거 인용 답변을 받습니다.')
  await page.goto(`${FRONTEND}/wiki`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  const searchInput = page.locator('input[placeholder*="하이브리드 검색"]').first()
  if (!(await searchInput.count())) throw new Error('search input not found')
  await caption(page, '하이브리드 검색은 BM25 키워드 매칭과 의미 벡터 검색을 RRF로 결합해, 어휘 일치와 의미 유사도를 동시에 반영합니다.', 6000)
  await flash(page, searchInput)
  await searchInput.click()
  await searchInput.fill('고객 검색')
  await page.waitForTimeout(700)
  await page.keyboard.press('Enter')
  await page.waitForTimeout(2500)
  await shot(page, 'sc-003-search')

  const queryInput = page.locator('input[placeholder*="위키에 질문하기"]').first()
  if (await queryInput.count()) {
    await caption(page, '자연어 질의응답은 관련 페이지 본문을 인용하며, 근거 출처를 wikilink로 함께 제시합니다.', 6500)
    await flash(page, queryInput)
    await queryInput.click()
    await queryInput.fill('고객 검색에서 지원하는 필터 조건은?')
    await page.waitForTimeout(700)
    await page.keyboard.press('Enter')
    await page.waitForTimeout(6000)  // LLM 응답 대기
    await shot(page, 'sc-003-query')
  } else {
    log('  query input not found — skipping')
  }

  // ──────────────────────────────────────────────────────────────────────
  // SC-004 : 멀티 에이전트 워크플로우 실시간 시각화
  // ──────────────────────────────────────────────────────────────────────
  log('SC-004: 멀티 에이전트 워크플로우 실시간 시각화')
  await setScenarioBadge(page, 'SC-004', '멀티 에이전트 워크플로우 실시간 시각화')
  await chapter(page, 'SC-004 · 멀티 에이전트 워크플로우 실시간 시각화')
  await scenarioCard(page, 'SC-004',
    '멀티 에이전트 워크플로우 실시간 시각화',
    '13개 노드의 진행·소요시간·입출력·LLM 판정 근거를 실시간으로 확인합니다.')
  if (runId) {
    await page.goto(`${FRONTEND}/runs/${runId}`, { waitUntil: 'domcontentloaded' })
  } else {
    log('  no runId — staying on current page')
  }
  await page.waitForSelector('.react-flow__node', { timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(1500)

  // 전체 그림 — 13개 노드, LLM 배지가 붙은 8개 에이전트가 강조됨
  await caption(page, '13개 에이전트가 SSE 스트림으로 실시간 상태를 공유하며 협업합니다. LLM 배지가 표시된 8개 에이전트를 파이프라인 순서대로 살펴봅니다.', 6500)
  await shot(page, 'sc-004-pipeline')

  // ── LLM 에이전트 8종을 파이프라인 순서대로 ──
  // 각 에이전트: focusAgent (=클릭+sustain 강조) → 자막 (자막 떠 있는 동안 강조 지속) → 캡처

  await focusAgent(page, '정규화')
  await caption(page, '정규화 — 본문을 마크다운 구조로 정렬하고, SDLC 단계와 도메인·서브도메인을 LLM이 분류합니다.', 5200)
  await shot(page, 'sc-004-normalize')

  await focusAgent(page, '도메인 분해')
  await caption(page, '도메인 분해 — 복수 도메인을 포함한 문서를 LLM이 단위별로 분할해 자식 run으로 병렬 처리합니다.', 5500)
  await shot(page, 'sc-004-decompose')

  await focusAgent(page, '임베딩')
  await caption(page, '임베딩 — 본문 청크를 임베딩 모델로 벡터화해 벡터 DB(Chroma)에 적재합니다.', 4800)
  await shot(page, 'sc-004-embed')

  await focusAgent(page, '유사도')
  await caption(page, '유사도 — 벡터 거리 기준으로 후보 페이지를 선별한 뒤, LLM이 동일성 여부를 재판정합니다.', 5800)
  await shot(page, 'sc-004-similarity')

  await focusAgent(page, '충돌판정')
  await caption(page, '충돌판정 — 신규·기존 문서의 의미 관계를 LLM이 보강·중복·모순·구체화 네 가지로 판별합니다.', 5500)
  await shot(page, 'sc-004-conflict')

  await focusAgent(page, '병합')
  await caption(page, '병합 — 판별된 관계와 충돌 정책에 따라 LLM이 두 본문을 단일 페이지로 통합합니다.', 5000)
  await shot(page, 'sc-004-merge')

  await focusAgent(page, '누락검토')
  await caption(page, '누락검토 — 병합 결과의 커버리지를 LLM이 정량 평가하며, 임계값 미달 시 병합 단계로 1회 자동 재진입합니다.', 6300)
  await shot(page, 'sc-004-verify')

  await focusAgent(page, '상호참조')
  await caption(page, '상호참조 — LLM이 의미적으로 연관된 페이지를 식별해 "연관 도메인" 표와 지식 그래프 엣지를 동시에 갱신합니다.', 6300)
  await shot(page, 'sc-004-crossref')

  await clearSustain(page)   // 다음 시나리오로 넘어가기 전 강조 해제

  // ──────────────────────────────────────────────────────────────────────
  // SC-005 : 병합 결과 검토 및 되돌림 (diff / revert)
  // ──────────────────────────────────────────────────────────────────────
  log('SC-005: 병합 결과 검토 및 되돌림')
  await setScenarioBadge(page, 'SC-005', '병합 결과 검토 및 되돌림')
  await chapter(page, 'SC-005 · 병합 결과 검토 및 되돌림')
  await scenarioCard(page, 'SC-005',
    '병합 결과 검토 및 되돌림 (diff / revert)',
    '병합 전과 후를 라인 단위 diff로 비교하고, 일부 또는 전체를 되돌리거나 직접 편집합니다.')
  await page.goto(`${FRONTEND}/merges`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  await caption(page, '병합 전후를 라인 단위 side-by-side diff로 비교하며, 특정 hunk 또는 전체 되돌리기를 지원합니다. 되돌린 본문은 즉시 재임베딩되어 검색 결과에 반영됩니다.', 7000)
  const firstMerge = page.locator('.list-item').first()
  if (await firstMerge.count()) { await flash(page, firstMerge); await firstMerge.click() }
  await page.waitForTimeout(2500)
  await caption(page, '충돌이 없는 항목은 가독성을 위해 목록에서 자동으로 제외됩니다.', 5000)

  // ── 복구 옵션 두 가지를 차례로 강조하며 설명 ───────────────────────────
  // 전체 되돌리기 — 헤더 우측 .btn-danger
  const revertAllBtn = page.locator('button.btn-danger', { hasText: /전체 되돌리기/ }).first()
  if (await revertAllBtn.count()) {
    await sustainHighlight(page, revertAllBtn)
    await caption(page, '전체 되돌리기 — 이번 병합 전체를 일괄 취소하고 병합 직전 본문으로 복원합니다.', 5500)
  }
  // 부분 되돌리기 — diff 표의 첫 hunk 옆 .hunk-revert (↩ 복원)
  const hunkRevertBtn = page.locator('button.hunk-revert').first()
  if (await hunkRevertBtn.count()) {
    // 표 안쪽이라 화면 밖에 있을 수 있어 중앙으로 끌어와 좌표 신뢰도 확보
    await hunkRevertBtn.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' })).catch(() => {})
    await page.waitForTimeout(180)
    await sustainHighlight(page, hunkRevertBtn)
    await caption(page, '부분 되돌리기 — 변경 hunk 단위로 원하는 부분만 선택해 변경 전 내용으로 복원합니다.', 5500)
  }
  await shot(page, 'sc-005-diff')
  await clearSustain(page)

  // ──────────────────────────────────────────────────────────────────────
  // SC-006 : 지식 그래프 탐색
  // ──────────────────────────────────────────────────────────────────────
  log('SC-006: 지식 그래프 탐색')
  await setScenarioBadge(page, 'SC-006', '지식 그래프 탐색')
  await chapter(page, 'SC-006 · 지식 그래프 탐색')
  await scenarioCard(page, 'SC-006',
    '지식 그래프 탐색',
    '도메인 스윔레인과 9종 엣지 타입·신뢰도로 위키 페이지 간 의미 관계를 탐색합니다.')
  await page.goto(`${FRONTEND}/graph`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.react-flow__node', { timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(1500)
  // fitView 기본 배율로는 7-레인 전체를 맞추느라 칩 라벨이 너무 작아 영상에서 안 읽힘
  // (sc-006-cross-only.png 회귀, 2026-05-28). React Flow Controls 의 zoom-in 을
  // 두 번 눌러 칩이 또렷이 보이는 배율까지 확대한 뒤 캡션/캡처.
  const zoomInBtn = page.locator('.react-flow__controls-zoomin').first()
  if (await zoomInBtn.count()) {
    for (let i = 0; i < 2; i++) {
      await zoomInBtn.click().catch(() => {})
      await page.waitForTimeout(220)
    }
  }
  await page.waitForTimeout(400)   // zoom transform settle
  await caption(page, '구현·검증·구체화·참조·연관·중복·대체·충돌·병합출처 9종 엣지 타입과 상·중·하 신뢰도가 색상으로 구분됩니다.', 6500)
  await shot(page, 'sc-006-graph-base')

  // ── 관계 한 개만 골라 evidence 팝업을 확대해서 자세히 설명한다 ──
  // (필터/토글 데모는 의도적으로 생략 — "여러 개 보여주는 게 아니라 1개를 확대해서 설명")
  //
  // 이전엔 데모 엣지를 찾기 위해 모든 엣지를 순회하며 클릭→패널 텍스트를 확인했는데
  // 위키 엣지가 많을 때(100+) 약 2분이 통째로 낭비됨(2026-05-28 회귀).
  //
  // injectDemo() 가 edges.jsonl *끝*에 append → GraphExplorer 가 edges 배열에 같은
  // 순서로 받아 `id: \`e${i}\`` 로 매김 → React Flow 가 배열 순서대로 DOM 렌더.
  // 따라서 *마지막* .react-flow__edge 가 곧 [DEMO] 엣지.
  await caption(page, '엣지 하나를 선택해 담긴 정보를 상세히 확인합니다.', 4000)
  const allEdges = await page.$$('.react-flow__edge')
  const matchedEdge = allEdges.length ? allEdges[allEdges.length - 1] : null
  if (matchedEdge) {
    await matchedEdge.evaluate((el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await page.waitForTimeout(450)
  }
  // 선택된 엣지를 보라색 글로우로 깜빡여, 어느 엣지가 짝인지 명시.
  if (matchedEdge) {
    await matchedEdge.evaluate((el) => {
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) return
      const fx = document.createElement('div')
      fx.className = '__walk_flash'
      fx.style.left   = `${r.left - 6}px`
      fx.style.top    = `${r.top - 6}px`
      fx.style.width  = `${r.width + 12}px`
      fx.style.height = `${r.height + 12}px`
      document.body.appendChild(fx)
      setTimeout(() => fx.remove(), 760)
    })
    await page.waitForTimeout(420)
  }
  // evidence 팝업 확대 — transform scale 로 크기 키워 시청자 눈에 잘 들어오게.
  // 좌하단에 자리잡은 패널이라 origin을 left bottom 으로 두어 화면 밖으로 안 밀린다.
  await page.evaluate(() => {
    const panel = document.querySelector('.edge-detail')
    if (!panel) return
    panel.style.transition = 'transform .55s ease-out, box-shadow .55s ease-out'
    panel.style.transformOrigin = 'left bottom'
    panel.style.transform = 'scale(1.35)'
    panel.style.boxShadow = '0 24px 80px rgba(0,0,0,.85), 0 0 0 2px rgba(193,132,252,.55)'
    panel.style.zIndex = '99'
  })
  await page.waitForTimeout(900)
  await shot(page, 'sc-006-edge-evidence')

  // 다섯 단의 구조를 캡션으로 차례로 짚는다 (확대된 팝업이 화면에 계속 떠 있는 상태)
  await caption(page, '엣지를 선택하면 LLM이 작성한 연결 정보가 다섯 단계로 표시됩니다.', 4500)
  await caption(page, '요약 — 두 페이지의 연결 지점을 한 줄로 요약합니다.', 4500)
  await caption(page, '연관 사유 — 두 페이지를 함께 검토해야 하는 근거를 LLM이 서술합니다.', 5000)
  await caption(page, '근거 인용 — 양쪽 본문에서 직접 인용한 문장으로 판단의 출처를 제시합니다.', 5500)
  await caption(page, '공유 개념 — 두 페이지가 공통으로 다루는 개념·코드·식별자를 정리합니다.', 5000)
  await caption(page, '함께 볼 때 — 한쪽을 수정·검토할 때 동시 참조가 필요한 시점을 안내합니다.', 5000)

  // 팝업 원상복귀 후 닫기
  await page.evaluate(() => {
    const panel = document.querySelector('.edge-detail')
    if (!panel) return
    panel.style.transform = ''
    panel.style.boxShadow = ''
  })
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(700)

  // ── 마무리 ─────────────────────────────────────────────────────────────
  log('Closing')
  await setScenarioBadge(page, null, null)   // 뱃지 해제(클로징 카드와 겹치지 않게)
  await page.goto(`${FRONTEND}/wiki`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  await caption(page, '위키는 일회성 구축에 그치지 않고, 신규 문서 적재마다 자동으로 갱신·유지됩니다.', 5200)
  await shot(page, 'sc-closing')
  await clearCaption(page)
  await titleCard(page,
    '계속 유지합니다.',
    '한 번 만들고 끝이 아니라,',
    4500,
    true)   // subtitle 을 큰 줄 위에 배치 — "끝이 아니라, … 계속 유지합니다." 강조 흐름

  await page.waitForTimeout(800)
} catch (e) {
  log('FATAL: ' + (e.stack || e.message))
} finally {
  // 자막 마지막 라인 flush 후 영상/SRT 마무리
  flushCaption()
  log(`scene errors during run: ${errs.length}`)
  for (const e of errs.slice(0, 8)) log('  ' + e)

  await page.close()
  await context.close()
  await browser.close()

  // tmp 비디오 → demo-recordings/walkthrough-{stamp}.webm 으로 이동
  const list = (await fs.readdir(VIDEO_DIR)).filter((f) => f.endsWith('.webm'))
  let videoOut = null
  if (list.length) {
    const src = path.join(VIDEO_DIR, list[0])
    videoOut = path.join(OUT_DIR, `walkthrough-${STAMP}.webm`)
    await fs.rename(src, videoOut)
    const stat = await fs.stat(videoOut)
    log(`video → ${videoOut} (${Math.round(stat.size / 1024)} KiB)`)
  } else {
    log('NO video file produced')
  }

  // SRT 사이드카 출력 (영상 파일명과 짝)
  if (srtEntries.length) {
    const srt = srtEntries.map((e, i) =>
      `${i + 1}\n${fmtSrt(e.start)} --> ${fmtSrt(e.end)}\n${e.text}\n`
    ).join('\n')
    const srtOut = path.join(OUT_DIR, `walkthrough-${STAMP}.srt`)
    await fs.writeFile(srtOut, srt, 'utf-8')
    log(`srt   → ${srtOut} (${srtEntries.length} entries)`)
  }

  // mp4 변환 — ffmpeg-static(npm 동봉 정적 바이너리) 우선, 시스템 ffmpeg 폴백.
  // 자막은 burn-in 이라 비디오 트림/리먹스만 해도 그대로 유지됨.
  // WALK_SKIP_MP4=1 로 건너뛸 수 있음.
  if (videoOut && process.env.WALK_SKIP_MP4 !== '1') {
    let ffPath = null
    try {
      const mod = await import('/home/lstguardleft/workspace/Project-Wiki-Manager/frontend/node_modules/ffmpeg-static/index.js')
      ffPath = mod.default || mod
    } catch { ffPath = 'ffmpeg' /* 시스템 PATH 시도 */ }
    const mp4Out = videoOut.replace(/\.webm$/i, '.mp4')
    const t0 = Date.now()
    const code = await new Promise((resolve) => {
      const args = ['-y', '-i', videoOut, '-c:v', 'libx264', '-preset', 'medium',
                    '-crf', '22', '-pix_fmt', 'yuv420p', '-an', mp4Out]
      const ch = spawn(ffPath, args, { stdio: 'ignore' })
      ch.on('error', () => resolve(-1))
      ch.on('exit', (c) => resolve(c ?? -1))
    })
    if (code === 0) {
      const sz = (await fs.stat(mp4Out)).size
      log(`mp4   → ${mp4Out} (${Math.round(sz / 1024)} KiB, ${Math.round((Date.now() - t0) / 1000)}s)`)
    } else {
      log(`mp4 conversion failed (exit=${code}) — webm 만 보관`)
    }
  }

  await removeDemo()
  await fs.writeFile(LOG_FILE, logLines.join('\n'), 'utf-8')
  log(`log file: ${LOG_FILE}`)
}
