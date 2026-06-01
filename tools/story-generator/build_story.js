#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';

// argv[2] = google JP font family, argv[3] = output suffix
const jpFont = process.argv[2] || 'Murecho';
const suffix = process.argv[3] || '';
const fontParam = jpFont.replace(/ /g, '+') + ':wght@400;500;700';

const gameImg = readFileSync(resolve('output/mock_game.b64'), 'utf-8').trim();

const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@400;500;700&family=${fontParam}&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1080px; height: 1920px; background: #0a0a0f;
    font-family: '${jpFont}', sans-serif;
    color: #e0e0e0; padding: 44px;
    display: flex; flex-direction: column; gap: 18px;
  }
  .header { text-align: center; padding: 14px 0 0; }
  .header h1 {
    font-family: 'Orbitron', sans-serif; font-size: 54px; font-weight: 900;
    background: linear-gradient(135deg, #00F0FF 0%, #BD93F9 50%, #FF3366 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 3px;
  }
  .header .subtitle {
    font-family: 'Orbitron', sans-serif; font-size: 26px; font-weight: 400;
    color: #555; margin-top: 12px; letter-spacing: 6px; text-transform: uppercase;
  }
  .header .period { font-family: 'JetBrains Mono', monospace; font-size: 21px; color: #444; margin-top: 8px; letter-spacing: 3px; }
  .header .stats { font-family: 'JetBrains Mono', monospace; font-size: 19px; margin-top: 10px; letter-spacing: 1px; color: #777; }

  .add { color: #3fb950; } .del { color: #f85149; } .fno { color: #5a5a6a; }

  /* ---- Bento grid: 6 cols x 4 rows, free spans ---- */
  .grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    grid-template-rows: repeat(4, 1fr);
    gap: 16px; flex: 1;
  }
  .card {
    background: #15151d; border-radius: 28px; padding: 32px 34px;
    display: flex; flex-direction: column; justify-content: center;
    position: relative; overflow: hidden; border: 1px solid #1d1d2b;
  }
  .card::before {
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(circle at 15% -10%, var(--accent, #00f0ff), transparent 60%);
    opacity: 0.16; pointer-events: none;
  }
  .card .emoji { font-size: 46px; margin-bottom: 10px; line-height: 1; }
  .card .label { font-family: 'JetBrains Mono', monospace; font-size: 16px; color: #7a7a8a; letter-spacing: 2px; margin-bottom: 6px; }
  .card .value { font-weight: 700; font-size: 42px; color: var(--accent, #00f0ff); line-height: 1.1; }
  .card .desc { font-size: 20px; color: #9a9aa8; margin-top: 10px; line-height: 1.5; font-weight: 400; }

  /* techy spec pills */
  .spec { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
  .spec span { font-family: 'JetBrains Mono', monospace; font-size: 15px; color: #9090a0; border: 1px solid #2c2c3c; background: #1a1a26; border-radius: 9px; padding: 4px 11px; }
  /* diff stat */
  .diff { font-family: 'JetBrains Mono', monospace; font-size: 17px; margin-top: 12px; letter-spacing: 0.5px; }

  /* hero (GAME) */
  .hero { grid-column: 1 / 5; grid-row: 1 / 3; padding: 0; }
  .hero .text-side { padding: 34px 38px 8px; }
  .hero .text-side .emoji { font-size: 52px; }
  .hero .text-side .value { font-size: 52px; }
  .hero .img-wrap { flex: 1; position: relative; overflow: hidden; min-height: 0; }
  .hero .img-wrap img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; object-position: bottom center; }

  /* LIKE tall stat */
  .like { grid-column: 5 / 7; grid-row: 1 / 3; }
  .like .bignum { font-family: 'Orbitron', sans-serif; font-size: 84px; font-weight: 900; color: var(--accent); line-height: 1; text-shadow: 0 0 30px rgba(224,36,94,.45); margin-top: 4px; }
  .like .delta { font-family: 'JetBrains Mono', monospace; font-size: 22px; color: #3fb950; margin-top: 2px; font-weight: 700; }

  /* STUDY tall */
  .study { grid-column: 1 / 3; grid-row: 3 / 5; }
  .study .latest { font-family: 'JetBrains Mono', monospace; font-size: 16px; color: #8a8aa0; margin-top: 14px; border-left: 3px solid var(--accent); padding-left: 12px; line-height: 1.5; }

  /* GITHUB + 通知 wide horizontal */
  .wide-bar { flex-direction: row; align-items: center; gap: 28px; }
  .wide-bar .emoji { font-size: 52px; margin: 0; flex-shrink: 0; }
  .wide-bar .value { font-size: 38px; }
  .wide-bar .body { flex: 1; }
  .github { grid-column: 3 / 7; grid-row: 3 / 4; }
  .noti   { grid-column: 3 / 7; grid-row: 4 / 5; }

  .footer { text-align: center; padding: 0 0 8px; }
  .footer .url { font-family: 'Orbitron', sans-serif; font-size: 22px; color: #333; letter-spacing: 5px; }
</style>
</head>
<body>

<div class="header">
  <h1>HEALTH.OJIMPO.COM</h1>
  <div class="subtitle">Recent Updates</div>
  <div class="period">2026.04.26 — 2026.06.01</div>
  <div class="stats">13 commits · <span class="add">+1,505</span> <span class="del">−421</span> · 48 files</div>
</div>

<div class="grid">

  <!-- GAME hero -->
  <div class="card hero" style="--accent: #66C0F4;">
    <div class="text-side">
      <div class="emoji">🎮</div>
      <div class="label">NEW CATEGORY · GAME</div>
      <div class="value">ゲーム</div>
      <div class="desc">Steamのゲームプレイ時間を取得し、文化スコアに合流</div>
      <div class="spec"><span>STEAM WEB API</span><span>基準 300分/週</span><span>decay 7d</span></div>
      <div class="diff"><span class="add">+378</span> <span class="del">−1</span> <span class="fno">· 9 files</span></div>
    </div>
    <div class="img-wrap"><img src="${gameImg}"></div>
  </div>

  <!-- LIKE tall stat -->
  <div class="card like" style="--accent: #E0245E;">
    <div class="emoji">❤️</div>
    <div class="label">NEW CATEGORY</div>
    <div class="value">Like</div>
    <div class="bignum">196</div>
    <div class="delta">前期比 +60 ▲</div>
    <div class="desc">Spotifyで「保存」した曲を音楽の発掘として記録</div>
    <div class="spec"><span>SPOTIFY SAVED</span><span>1,902 tracks</span></div>
    <div class="diff"><span class="add">+202</span> <span class="del">−1</span> <span class="fno">· 7 files</span></div>
  </div>

  <!-- STUDY tall -->
  <div class="card study" style="--accent: #5C6BC0;">
    <div class="emoji">📚</div>
    <div class="label">NEW CATEGORY</div>
    <div class="value">勉強</div>
    <div class="desc">StudyplusとDuolingoの学習時間を記録</div>
    <div class="latest">▸ 工業数学の基礎<br>&nbsp;&nbsp;65 min · today</div>
    <div class="spec"><span>Studyplus</span><span>Duolingo</span></div>
    <div class="diff"><span class="add">+372</span> <span class="del">−126</span> <span class="fno">· 10 files</span></div>
  </div>

  <!-- GITHUB wide -->
  <div class="card github wide-bar" style="--accent: #50FA7B;">
    <div class="emoji">🐙</div>
    <div class="body">
      <div class="label">REVIVED</div>
      <div class="value">GitHub</div>
      <div class="desc">コミット数を文化スコアとして再び計測</div>
      <div class="spec"><span>GITHUB API</span><span>基準 14 commits/週</span><span class="add" style="border-color:#234;background:#11210f;">+18</span><span class="del" style="border-color:#321;background:#210f0f;">−6</span></div>
    </div>
  </div>

  <!-- 通知 wide -->
  <div class="card noti wide-bar" style="--accent: #FFB347;">
    <div class="emoji">🔔</div>
    <div class="body">
      <div class="label">RELIABILITY</div>
      <div class="value">通知ロジック</div>
      <div class="desc">3回連続で異常を観測したら発火、CRITICALは即時</div>
      <div class="spec"><span>persistence guard</span><span class="add" style="border-color:#234;background:#11210f;">+94</span><span class="del" style="border-color:#321;background:#210f0f;">−5</span></div>
    </div>
  </div>

</div>

<div class="footer">
  <div class="url">health.ojimpo.com</div>
</div>

</body>
</html>`;

const outName = suffix ? `output/story_20260601_${suffix}.html` : 'output/story_20260601.html';
writeFileSync(resolve(outName), html);
console.log(`Wrote ${outName}`);
