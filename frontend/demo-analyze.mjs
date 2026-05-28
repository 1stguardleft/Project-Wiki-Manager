// Playwright 시연 녹화: 파일 1개 적재 → 멀티에이전트 워크플로우.
// 포함: 마우스 커서 + 클릭 리플 강조, 타이틀 카드/캡션, mp4 자동 변환.
// 실행: (frontend 디렉터리에서) node demo-analyze.mjs
import { chromium } from 'playwright'
import { execFileSync } from 'node:child_process'
import { readdir, rename } from 'node:fs/promises'
import ffmpegPath from 'ffmpeg-static'

const BASE = 'http://127.0.0.1:5173'
const VID_DIR = '../demo-recordings'
const SIZE = { width: 1440, height: 900 }
const CASE_TITLE = '시연 ① 단일 문서 분석'
const CASE_SUB = '고객 검색 요구사항 적재 → 멀티에이전트 워크플로우'
const beat = (ms = 800) => new Promise((r) => setTimeout(r, ms))

// 페이지에 주입: 가짜 커서 + 클릭 리플 + 타이틀/캡션 스타일 (모든 문서에 적용)
function overlayInit() {
  const style = document.createElement('style')
  style.textContent = `
    #pw-cursor { position: fixed; width: 20px; height: 20px; margin: -10px 0 0 -10px;
      border: 2px solid #818cf8; border-radius: 50%; background: rgba(129,140,248,.22);
      box-shadow: 0 0 10px rgba(129,140,248,.6); z-index: 2147483647; pointer-events: none;
      left: -50px; top: -50px; transition: left .04s linear, top .04s linear; }
    .pw-ripple { position: fixed; border: 2.5px solid #a855f7; border-radius: 50%;
      z-index: 2147483646; pointer-events: none; animation: pw-r .6s ease-out forwards; }
    @keyframes pw-r { from { width:10px;height:10px;margin:-5px 0 0 -5px;opacity:.95; }
      to { width:64px;height:64px;margin:-32px 0 0 -32px;opacity:0; } }
    #pw-caption { position: fixed; top: 14px; left: 16px; z-index: 2147483646;
      font: 600 13px/1 -apple-system,'Apple SD Gothic Neo',sans-serif; color:#eceef6;
      background: rgba(22,26,41,.92); border:1px solid rgba(168,85,247,.5);
      padding: 8px 14px; border-radius: 999px; box-shadow: 0 8px 24px -10px rgba(0,0,0,.8); }
    #pw-titlecard { position: fixed; inset: 0; z-index: 2147483645; display:flex;
      flex-direction:column; align-items:center; justify-content:center; gap:14px;
      background: radial-gradient(900px 500px at 50% 40%, rgba(99,102,241,.25), rgba(8,10,18,.94));
      color:#fff; font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;
      opacity:0; transition: opacity .5s ease; }
    #pw-titlecard.show { opacity:1; }
    #pw-titlecard .t { font-size: 40px; font-weight: 800; letter-spacing:-.5px; }
    #pw-titlecard .s { font-size: 18px; color:#c7cbe0; }
    #pw-titlecard .tag { font-size:12px; font-weight:700; letter-spacing:1px; text-transform:uppercase;
      color:#fff; background:linear-gradient(135deg,#6366f1,#a855f7); padding:5px 12px; border-radius:6px; }
  `
  document.documentElement.appendChild(style)
  const cur = document.createElement('div'); cur.id = 'pw-cursor'
  document.documentElement.appendChild(cur)
  addEventListener('mousemove', (e) => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px' }, true)
  addEventListener('mousedown', (e) => {
    const r = document.createElement('div'); r.className = 'pw-ripple'
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'
    document.documentElement.appendChild(r); setTimeout(() => r.remove(), 650)
  }, true)
}

const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: SIZE,
  recordVideo: { dir: VID_DIR, size: SIZE },
})
await ctx.addInitScript(overlayInit)
const page = await ctx.newPage()

async function clickDir(name) {
  const row = page.locator(`tr.dir-row:has-text("${name}")`).first()
  await row.waitFor({ state: 'visible', timeout: 15000 })
  await beat()
  await row.click()
}

console.log('▶ 적재 화면 진입')
await page.goto(`${BASE}/ingest`)
await page.waitForLoadState('networkidle')

// ── 타이틀 카드 (2.6초) + 상시 캡션 ──
await page.evaluate(({ t, s }) => {
  const cap = document.createElement('div'); cap.id = 'pw-caption'; cap.textContent = '📽 ' + t
  document.documentElement.appendChild(cap)
  const card = document.createElement('div'); card.id = 'pw-titlecard'
  card.innerHTML = `<span class="tag">PROJECT WIKI MANAGER</span><div class="t">${t}</div><div class="s">${s}</div>`
  document.documentElement.appendChild(card)
  requestAnimationFrame(() => card.classList.add('show'))
}, { t: CASE_TITLE, s: CASE_SUB })
await beat(2600)
await page.evaluate(() => {
  const c = document.getElementById('pw-titlecard'); if (!c) return
  c.classList.remove('show'); setTimeout(() => c.remove(), 500)
})
await beat(900)

console.log('▶ 폴더 드릴다운: 1차 > 01-요구사항 > 고객관리 > 고객검색')
await clickDir('1차')
await clickDir('01-요구사항')
await clickDir('고객관리')
await clickDir('고객검색')

console.log('▶ 파일 선택')
const fileRow = page.locator('tr.src-row:not(.dir-row)').first()
await fileRow.waitFor({ state: 'visible', timeout: 15000 })
await beat()
await fileRow.click()
await beat(1000)

console.log('▶ 적재 시작')
await page.getByRole('button', { name: /적재/ }).first().click()
await page.waitForURL('**/runs/**', { timeout: 15000 })
console.log('▶ 워크플로우 실행 중…')
try {
  await page.locator('.wf-status:has-text("완료"), .badge.succeeded:has-text("전체 완료")')
    .first().waitFor({ timeout: 120000 })
  console.log('▶ 완료')
} catch { console.log('▶ (완료 미감지 — 현재 상태로 마무리)') }
await beat(3500)

await ctx.close()
await browser.close()

// ── 동영상 정리 + mp4 변환 ──
const vids = (await readdir(VID_DIR)).filter((f) => f.endsWith('.webm')).sort()
if (!vids.length) { console.log('⚠ 동영상 없음'); process.exit(1) }
const webm = `${VID_DIR}/demo-analyze.webm`
await rename(`${VID_DIR}/${vids[vids.length - 1]}`, webm)
const mp4 = `${VID_DIR}/demo-analyze.mp4`
execFileSync(ffmpegPath, ['-y', '-i', webm, '-c:v', 'libx264', '-preset', 'veryfast',
  '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4], { stdio: 'ignore' })
console.log('✔ 저장: demo-recordings/demo-analyze.webm, demo-recordings/demo-analyze.mp4')
