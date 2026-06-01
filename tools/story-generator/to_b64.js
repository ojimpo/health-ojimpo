#!/usr/bin/env node
// HTML file → base64 data URI PNG (size auto from body). Usage: node to_b64.js <in.html> <out.b64> [w] [h]
import puppeteer from 'puppeteer';
import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';

const htmlPath = process.argv[2];
const outPath = process.argv[3];
const w = parseInt(process.argv[4] || '520');
const h = parseInt(process.argv[5] || '300');

const html = readFileSync(resolve(htmlPath), 'utf-8');
const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: w, height: h, deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: 'networkidle0' });
const buf = await page.screenshot({ type: 'png' });
await browser.close();
const dataUri = 'data:image/png;base64,' + buf.toString('base64');
writeFileSync(resolve(outPath), dataUri);
console.log(`Wrote ${outPath} (${dataUri.length} chars)`);
