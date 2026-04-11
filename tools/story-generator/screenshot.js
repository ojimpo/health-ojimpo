#!/usr/bin/env node
// Take a screenshot of a URL
import puppeteer from 'puppeteer';
import { resolve } from 'path';

const url = process.argv[2] || 'http://localhost:8401';
const outPath = process.argv[3] || 'output/screenshot.png';
const width = parseInt(process.argv[4] || '1280');
const height = parseInt(process.argv[5] || '800');

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});
const page = await browser.newPage();
await page.setViewport({ width, height, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle0', timeout: 15000 });
await page.screenshot({ path: resolve(outPath), type: 'png' });
await browser.close();

console.log(`Screenshot: ${resolve(outPath)}`);
