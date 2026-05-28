// 타이틀/캡션/SRT 시스템 단독 검증용 — 적재·rebuild-crossref 없이
// 기존 페이지 1건만 열어 약 30초짜리 영상을 만든다.
//
// 사용: `node scenario/record-test-titlecaption.mjs`
// 산출: demo-recordings/test-titlecaption-{stamp}.{webm,srt}
//
// 본 스크립트가 정상 동작하면 record-walkthrough.mjs 의 자막 계층도 동작.

import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import pwt from '/home/lstguardleft/workspace/Project-Wiki-Manager/frontend/node_modules/playwright-core/index.js'
const { chromium } = pwt

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FRONTEND = process.env.WALK_FRONTEND || 'http://localhost:5173'
const BACKEND = process.env.WALK_BACKEND || 'http://127.0.0.1:8000'
const STAMP = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12)
const VIDEO_DIR = path.join(ROOT, 'scenario', '.video-tmp')
const OUT_DIR = path.join(ROOT, 'demo-recordings')
const SHOTS_DIR = path.join(ROOT, 'scenario', 'shots')
await fs.mkdir(VIDEO_DIR, { recursive: true })
await fs.mkdir(OUT_DIR, { recursive: true })
await fs.mkdir(SHOTS_DIR, { recursive: true })
// 시작 전 .video-tmp의 잔여 webm 제거 — 이전 실행이 비정상 종료해 남긴
// 파일을 신규 산출물로 오인해 옮기는 사고 방지(2026-05-28 회귀 경험)
for (const f of (await fs.readdir(VIDEO_DIR))) {
  if (f.endsWith('.webm')) await fs.rm(path.join(VIDEO_DIR, f)).catch(() => {})
}

const log = (s) => console.log(`[${new Date().toISOString().slice(11,19)}] ${s}`)

// ── 검증용 페이지 1건 — 백엔드에서 첫 페이지 slug 가져오기 ──────────────
async function pickSlug() {
  if (process.env.WALK_SLUG) return process.env.WALK_SLUG
  const r = await fetch(`${BACKEND}/api/wiki/pages`)
  const { pages } = await r.json()
  if (!pages || !pages.length) throw new Error('no pages in wiki — ingest at least one document first')
  // 본문이 풍부할 가능성이 높은 요구사항 페이지 우선, 없으면 첫 페이지
  const pref = pages.find((p) => p.sdlc_phase === 'requirements') || pages[0]
  return pref.slug
}

// ── 자막/타이틀/챕터 시스템 (record-walkthrough.mjs 와 동일 로직) ───────
let videoT0 = 0
let captionCur = { text: '', start: -1 }
const srt = []
const nowRel = () => Date.now() - videoT0
const fmtSrt = (ms) => {
  const t = Math.max(0, ms | 0)
  const h = String(Math.floor(t / 3600000)).padStart(2, '0')
  const m = String(Math.floor(t / 60000) % 60).padStart(2, '0')
  const s = String(Math.floor(t / 1000) % 60).padStart(2, '0')
  const u = String(t % 1000).padStart(3, '0')
  return `${h}:${m}:${s},${u}`
}
const flushCaption = () => {
  if (captionCur.start >= 0 && captionCur.text) {
    const end = nowRel()
    if (end - captionCur.start >= 400) srt.push({ start: captionCur.start, end, text: captionCur.text })
  }
  captionCur = { text: '', start: -1 }
}
const ensureOverlayCss = async (page) => {
  await page.evaluate(() => {
    if (document.getElementById('__walk_css')) return
    const s = document.createElement('style')
    s.id = '__walk_css'
    s.textContent = `
      .__walk_caption {
        position: fixed; left: 50%; bottom: 56px; transform: translateX(-50%);
        z-index: 999998; max-width: 80%; padding: 11px 22px; border-radius: 6px;
        background: rgba(0,0,0,.80); color: #fff; font-size: 18px;
        font-weight: 500; line-height: 1.45; text-align: center;
        letter-spacing: .2px; opacity: 0; transition: opacity .22s ease;
        box-shadow: 0 6px 24px rgba(0,0,0,.55);
        font-family: -apple-system, "Apple SD Gothic Neo", "Segoe UI", "Noto Sans CJK KR", sans-serif;
      }
      .__walk_caption.show { opacity: 1; }
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
const titleCard = async (page, title, subtitle, hold = 4000) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ title, subtitle }) => {
    document.querySelectorAll('.__walk_card').forEach((e) => e.remove())
    const el = document.createElement('div'); el.className = '__walk_card'
    const t = document.createElement('div'); t.className = 'title'; t.textContent = title
    el.appendChild(t)
    if (subtitle) { const s = document.createElement('div'); s.className = 'subtitle'; s.textContent = subtitle; el.appendChild(s) }
    document.body.appendChild(el)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { title, subtitle: subtitle || '' })
  await page.waitForTimeout(hold)
  await page.evaluate(() => document.querySelectorAll('.__walk_card').forEach((el) => {
    el.classList.remove('show'); setTimeout(() => el.remove(), 320)
  }))
  await page.waitForTimeout(350)
}
const chapter = async (page, text, hold = 1800) => {
  await ensureOverlayCss(page)
  await page.evaluate(({ text }) => {
    document.querySelectorAll('.__walk_chapter').forEach((e) => e.remove())
    const el = document.createElement('div'); el.className = '__walk_chapter'
    el.textContent = text; document.body.appendChild(el)
    requestAnimationFrame(() => el.classList.add('show'))
  }, { text })
  await page.waitForTimeout(hold)
  await page.evaluate(() => document.querySelectorAll('.__walk_chapter').forEach((el) => {
    el.classList.remove('show'); setTimeout(() => el.remove(), 280)
  }))
  await page.waitForTimeout(200)
}
const caption = async (page, text, hold = 3000) => {
  await ensureOverlayCss(page)
  flushCaption()
  captionCur = { text, start: nowRel() }
  await page.evaluate(({ text }) => {
    let el = document.querySelector('.__walk_caption')
    if (!el) { el = document.createElement('div'); el.className = '__walk_caption'; document.body.appendChild(el) }
    el.textContent = text
    requestAnimationFrame(() => el.classList.add('show'))
  }, { text })
  if (hold > 0) await page.waitForTimeout(hold)
}
const clearCaption = async (page) => {
  flushCaption()
  await page.evaluate(() => { const el = document.querySelector('.__walk_caption'); if (el) el.classList.remove('show') })
  await page.waitForTimeout(180)
}

// ── 메인 ──────────────────────────────────────────────────────────────
const slug = await pickSlug()
log(`테스트 페이지: ${slug}`)

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 800 } },
})
videoT0 = Date.now()
const page = await context.newPage()
const errs = []
page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))

try {
  await page.goto(`${FRONTEND}/wiki?slug=${encodeURIComponent(slug)}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)

  // 인트로 타이틀 카드
  await titleCard(page,
    '타이틀 · 자막 시스템 테스트',
    '적재된 문서 1건 조회 · 약 30초',
    4000)

  // 챕터 마커 + 캡션
  await chapter(page, 'TEST — 위키 페이지 조회')
  await caption(page, '기존 위키 페이지를 그대로 엽니다', 3000)
  await page.screenshot({ path: path.join(SHOTS_DIR, 'test-A-top.png') }).catch(() => {})

  await caption(page, '프론트 매터 메타데이터 + 본문 + 페이지 이력', 3500)
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }))
  await page.waitForTimeout(2000)
  await page.screenshot({ path: path.join(SHOTS_DIR, 'test-B-scroll1.png') }).catch(() => {})

  await caption(page, '하단의 \"연관 도메인\" 표는 상호참조 Agent 가 자동 갱신', 4000)
  await page.evaluate(() => window.scrollBy({ top: 900, behavior: 'smooth' }))
  await page.waitForTimeout(2500)
  await page.screenshot({ path: path.join(SHOTS_DIR, 'test-C-bottom.png') }).catch(() => {})

  await caption(page, '한 페이지 안에서 5가지 자막 라인이 모두 노출됐습니다', 3500)
  await page.waitForTimeout(800)

  // 아웃트로
  await clearCaption(page)
  await titleCard(page,
    '자막 시스템 OK',
    '본 영상은 burn-in + SRT 동시 출력',
    4000)
  await page.waitForTimeout(500)
} catch (e) {
  log('FATAL: ' + (e.stack || e.message))
} finally {
  flushCaption()
  if (errs.length) log(`page errors: ${errs.length} — ${errs[0]}`)
  await page.close(); await context.close(); await browser.close()

  // webm 이동
  const list = (await fs.readdir(VIDEO_DIR)).filter((f) => f.endsWith('.webm'))
  if (list.length) {
    const src = path.join(VIDEO_DIR, list[0])
    const dst = path.join(OUT_DIR, `test-titlecaption-${STAMP}.webm`)
    await fs.rename(src, dst)
    const sz = (await fs.stat(dst)).size
    log(`video → ${dst} (${Math.round(sz / 1024)} KiB)`)
  } else log('NO video produced')

  // SRT 저장
  if (srt.length) {
    const out = path.join(OUT_DIR, `test-titlecaption-${STAMP}.srt`)
    await fs.writeFile(out,
      srt.map((e, i) => `${i + 1}\n${fmtSrt(e.start)} --> ${fmtSrt(e.end)}\n${e.text}\n`).join('\n'),
      'utf-8')
    log(`srt   → ${out} (${srt.length} entries)`)
  }
}
