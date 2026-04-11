#!/usr/bin/env node
// HTML file → PNG (1080x1920 Instagram Stories)
import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const htmlPath = process.argv[2];
const outPath = process.argv[3] || 'output/story.png';

if (!htmlPath) {
  console.error('Usage: node render.js <input.html> [output.png]');
  process.exit(1);
}

const html = readFileSync(resolve(htmlPath), 'utf-8');

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: 'networkidle0' });
await page.screenshot({ path: resolve(outPath), type: 'png' });
await browser.close();

console.log(`Generated: ${resolve(outPath)}`);
