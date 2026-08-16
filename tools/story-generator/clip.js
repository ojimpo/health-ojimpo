#!/usr/bin/env node
// ページ内の特定要素だけを切り出して PNG にする。
// ヒーロー用にダッシュボードのグラフ本体（.recharts-wrapper）だけ抜いたり、
// 組み上げたストーリーHTMLのカード1枚を拡大確認したりするのに使う。
//
//   node clip.js <url> <out.png> <selector> [viewportW] [viewportH]
//   node clip.js http://localhost:8401 output/hero_chart.png ".recharts-wrapper"
//   node clip.js "file://$PWD/output/story.html" output/zoom.png ".bento > div:nth-child(3)" 1080 1920
import puppeteer from 'puppeteer';
import { resolve } from 'path';

const [, , url, out, sel, w, h] = process.argv;

if (!url || !out || !sel) {
  console.error('Usage: node clip.js <url> <out.png> <selector> [width] [height]');
  process.exit(1);
}

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});
const page = await browser.newPage();
await page.setViewport({ width: +(w || 1400), height: +(h || 1000), deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle0', timeout: 20000 });

const el = await page.$(sel);
if (!el) {
  console.error(`Element not found: ${sel}`);
  await browser.close();
  process.exit(1);
}
await el.screenshot({ path: resolve(out) });
await browser.close();

console.log(`Clipped: ${resolve(out)}`);
