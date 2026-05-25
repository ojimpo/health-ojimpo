#!/usr/bin/env node
// Headless screenshot helper for health.ojimpo.com dev verification.
//
// Usage:
//   node snap.mjs <name> [options]
//
// Options (all optional):
//   --url <url>           Page to load (default: http://localhost:8401/admin)
//   --click <selector>    Click selector after load
//   --click-text <text>   Click first element with this exact text
//   --wait <ms>           Wait this many ms after click before screenshot (default: 500)
//   --width <px>          Viewport width (default: 1400)
//   --height <px>          Viewport height for screenshot (default: full page)
//   --full                Capture full page (default true unless --height given)
//
// Output: /tmp/health-screenshots/<name>.png

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2)
const name = args[0] || 'snap'
const opts = {}
for (let i = 1; i < args.length; i++) {
  const k = args[i]
  if (k === '--full') { opts.full = true; continue }
  opts[k.replace(/^--/, '')] = args[++i]
}

const url = opts.url || 'http://localhost:8401/admin'
const width = parseInt(opts.width || '1400', 10)
const height = opts.height ? parseInt(opts.height, 10) : null
const fullPage = opts.full || !height
const outDir = '/tmp/health-screenshots'
mkdirSync(outDir, { recursive: true })
const out = path.join(outDir, `${name}.png`)

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width, height: height || 900 } })
const page = await ctx.newPage()

await page.goto(url, { waitUntil: 'networkidle' })
// Allow chart animations to settle
await page.waitForTimeout(800)

if (opts.click) {
  await page.locator(opts.click).first().click()
  await page.waitForTimeout(parseInt(opts.wait || '500', 10))
}
if (opts['click-text']) {
  await page.getByText(opts['click-text'], { exact: true }).first().click()
  await page.waitForTimeout(parseInt(opts.wait || '500', 10))
}

if (opts.element) {
  const el = page.locator(opts.element).first()
  await el.screenshot({ path: out })
} else {
  await page.screenshot({ path: out, fullPage })
}
await browser.close()
console.log(`wrote ${out}`)
