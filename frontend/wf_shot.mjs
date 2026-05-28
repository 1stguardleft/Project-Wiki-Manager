import { chromium } from 'playwright'
import fs from 'fs'

const runId = fs.readFileSync('/tmp/wf_run_id.txt', 'utf8').trim()
const base = 'http://localhost:5173'
const url = `${base}/runs/${runId}`

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 720 } })
const errors = []
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))

await page.goto(url, { waitUntil: 'networkidle' })
// mid-run shot (try to catch a running node)
await page.waitForTimeout(1200)
await page.screenshot({ path: '/tmp/wf_running.png' })
// wait for completion
await page.waitForTimeout(6000)
await page.screenshot({ path: '/tmp/wf_done.png' })

// click the first node to test pin/pause, then screenshot
const firstNode = page.locator('.wf-node').first()
if (await firstNode.count()) {
  await firstNode.click()
  await page.waitForTimeout(400)
  await page.screenshot({ path: '/tmp/wf_pinned.png' })
}

console.log('console/page errors:', JSON.stringify(errors, null, 2))
await browser.close()
