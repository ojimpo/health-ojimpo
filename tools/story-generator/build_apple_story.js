#!/usr/bin/env node
// Apple Event 風 Bento ストーリー（1080x1920）を組み立てる。
// 画像は setContent 時に読めないので base64 で埋め込む。
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const b64 = (p) => `data:image/png;base64,${readFileSync(resolve(here, p)).toString('base64')}`;
const chart = b64('output/hero_chart.png');
const logo = b64('../../frontend/public/icon-512.png');

const html = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1080px; height:1920px; background:#000; overflow:hidden;
    font-family:'Inter','Noto Sans JP',sans-serif;
    color:#f5f5f7; -webkit-font-smoothing:antialiased;
  }
  .page { padding:56px 40px 0; height:100%; display:flex; flex-direction:column; }

  /* ---------- header ---------- */
  .brand { display:flex; align-items:center; gap:24px; }
  .brand .mark {
    width:104px; height:104px; border-radius:24px; flex:none;
    background:url('${logo}') center / cover no-repeat;
    box-shadow:0 0 0 1px rgba(255,255,255,.08);
  }
  .brand h1 {
    font-family:'Inter',sans-serif; font-weight:700; font-size:47px;
    letter-spacing:-.025em; line-height:1.05; color:#f5f5f7;
  }
  .brand .tag {
    font-family:'Noto Sans JP',sans-serif; font-size:21px; color:#86868b;
    margin-top:9px; font-weight:400;
  }
  .lede {
    margin-top:26px; font-family:'Noto Sans JP',sans-serif; font-weight:700;
    font-size:38px; letter-spacing:-.02em; color:#f5f5f7;
  }
  .stats {
    margin-top:12px; font-family:'JetBrains Mono',monospace; font-size:19px;
    color:#86868b; letter-spacing:.01em;
  }
  .stats .add { color:#f5f5f7; }
  .stats .sep { opacity:.4; margin:0 10px; }

  /* ---------- bento ---------- */
  .bento {
    margin-top:30px;
    display:grid; grid-template-columns:repeat(6,1fr);
    grid-template-rows:392px 268px 248px 286px 184px; gap:14px;
  }
  .card {
    background:#121214; border:1px solid rgba(255,255,255,.08);
    border-radius:30px; padding:26px 28px; position:relative; overflow:hidden;
    display:flex; flex-direction:column;
  }
  .kicker {
    font-size:16px; font-weight:600; letter-spacing:.06em; color:#86868b;
    font-family:'Noto Sans JP',sans-serif; margin-bottom:auto;
  }
  .title {
    font-family:'Noto Sans JP',sans-serif; font-weight:700;
    font-size:31px; line-height:1.32; letter-spacing:-.01em; color:#f5f5f7;
  }
  .title.sm { font-size:26px; }
  .sub {
    font-family:'Noto Sans JP',sans-serif; font-size:18px; line-height:1.5;
    color:#86868b; margin-top:10px; font-weight:400;
  }
  .metric {
    font-family:'Inter',sans-serif; font-weight:700; letter-spacing:-.045em;
    font-size:78px; line-height:1; color:#f5f5f7; margin:14px 0 8px;
  }
  .metric .unit { font-size:34px; font-weight:600; letter-spacing:-.02em; color:#86868b; margin-left:4px; }

  /* ---------- hero ---------- */
  .hero {
    padding:0; background:#0c0c0e; align-items:center; justify-content:center;
  }
  .hero .shot {
    position:absolute; left:0; right:0; bottom:0; height:252px;
    background:url('${chart}') center top / 118% auto no-repeat;
    opacity:.95;
    -webkit-mask-image:linear-gradient(to bottom, transparent 0%, #000 30%, #000 66%, transparent 100%);
  }
  .hero .veil {
    position:absolute; inset:0;
    background:
      radial-gradient(100% 66% at 50% 2%, rgba(0,0,0,.96) 0%, rgba(0,0,0,.62) 46%, rgba(0,0,0,.06) 76%),
      linear-gradient(to bottom, rgba(0,0,0,0) 58%, rgba(0,0,0,.32) 100%);
  }
  .hero .inner { position:relative; text-align:center; padding-top:30px; }
  .hero .word {
    font-family:'Inter',sans-serif; font-weight:800; font-size:158px; line-height:.92;
    letter-spacing:-.055em;
    background:linear-gradient(180deg,#8FE9FF 0%,#2AB6F5 58%,#0E7FD4 100%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
    filter:drop-shadow(0 6px 30px rgba(0,0,0,.85));
  }
  .hero .lead {
    font-family:'Noto Sans JP',sans-serif; font-weight:700; font-size:34px;
    letter-spacing:-.01em; color:#f5f5f7; margin-top:14px;
    text-shadow:0 3px 22px rgba(0,0,0,.9), 0 1px 4px rgba(0,0,0,.8);
  }
  .hero .lead-sub {
    font-family:'Noto Sans JP',sans-serif; font-size:19px; color:#c2c2c8; margin-top:10px;
    text-shadow:0 2px 16px rgba(0,0,0,.9), 0 1px 4px rgba(0,0,0,.8);
  }

  /* ---------- bits ---------- */
  .badge {
    display:inline-flex; align-items:center; gap:9px; align-self:flex-start;
    margin-top:16px; padding:9px 16px; border-radius:999px;
    background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.1);
    font-family:'Noto Sans JP',sans-serif; font-size:17px; font-weight:500; color:#d6d6da;
  }
  .badge .dot { width:9px; height:9px; border-radius:50%; background:#6e6e73; }
  .bubble {
    margin-top:16px; background:#1c1c1f; border-radius:18px 18px 18px 6px;
    padding:14px 16px; font-family:'Noto Sans JP',sans-serif; font-size:17px;
    line-height:1.45; color:#e6e6ea;
  }
  .choices { display:flex; gap:8px; margin-top:10px; }
  .choices span {
    flex:1; text-align:center; padding:9px 0; border-radius:11px;
    background:rgba(255,255,255,.08); font-family:'Noto Sans JP',sans-serif;
    font-size:15px; color:#c7c7cc;
  }
  /* 大きな英単語で見せるタイル（ヒーローの弟分。色はヒーローに譲って白のまま） */
  .word-lg {
    font-family:'Inter',sans-serif; font-weight:800; font-size:70px; line-height:.95;
    letter-spacing:-.05em; color:#f5f5f7; margin:8px 0 10px;
  }
  .word-md { font-size:54px; }

  /* ---------- 図版 ---------- */
  svg { display:block; }
  /* SVGのtextはfont-family属性が効かないとセリフ体に落ちる。CSSで明示的に上書きする */
  svg text {
    font-family:'JetBrains Mono','Inter',monospace; font-weight:400;
  }
  svg text.jp { font-family:'Noto Sans JP','Inter',sans-serif; }
  .fig { margin-top:auto; }
  .fig-cap {
    font-family:'JetBrains Mono',monospace; font-size:14px; color:#6e6e73; margin-top:10px;
  }
  /* 縦フロー（配信ゲート） */
  .flow { margin-top:6px; display:flex; flex-direction:column; gap:0; }
  .node {
    border:1px solid rgba(255,255,255,.14); border-radius:16px; padding:13px 15px;
    font-family:'Noto Sans JP',sans-serif; font-size:18px; font-weight:500; color:#e6e6ea;
  }
  .node.accent { border-color:rgba(42,182,245,.55); color:#8FE9FF; }
  .node small {
    display:block; font-size:14px; color:#86868b; font-weight:400; margin-top:4px;
    font-family:'JetBrains Mono',monospace;
  }
  .link {
    height:34px; margin-left:26px; border-left:2px solid rgba(255,255,255,.16);
    position:relative;
  }
  .link span {
    position:absolute; left:14px; top:50%; transform:translateY(-50%);
    font-family:'Noto Sans JP',sans-serif; font-size:14px; color:#86868b; white-space:nowrap;
  }
  .link::after {
    content:''; position:absolute; left:-5px; bottom:-1px;
    border-left:5px solid transparent; border-right:5px solid transparent;
    border-top:7px solid rgba(255,255,255,.28);
  }
  /* フィルムストリップ（写真） */
  .strip { display:flex; align-items:center; gap:10px; margin-top:12px; }
  .strip .name {
    font-family:'JetBrains Mono',monospace; font-size:14px; color:#86868b; width:96px; flex:none;
  }
  .strip .cells { display:flex; gap:5px; }
  .strip i { width:20px; height:20px; border-radius:5px; background:rgba(255,255,255,.24); }
  .strip.sub i { background:rgba(42,182,245,.55); }
  /* リッチメニュー */
  .menu {
    display:flex; margin-top:auto; border:1px solid rgba(255,255,255,.14);
    border-radius:16px; overflow:hidden;
  }
  .menu div {
    flex:1; text-align:center; padding:18px 0; background:rgba(255,255,255,.05);
    font-family:'JetBrains Mono',monospace; font-size:16px; color:#d6d6da;
    border-right:1px solid rgba(255,255,255,.12);
  }
  .menu div:last-child { border-right:0; }
  /* 再較正の3行 */
  .rows { margin-top:14px; display:flex; flex-direction:column; gap:11px; }
  .rows > div { display:flex; align-items:baseline; gap:12px; }
  .rows .cat {
    font-family:'Noto Sans JP',sans-serif; font-size:17px; color:#86868b; width:74px; flex:none;
  }
  .rows .chg {
    font-family:'Inter',sans-serif; font-size:21px; font-weight:600; color:#f5f5f7; letter-spacing:-.01em;
  }
  .rows .val {
    margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:15px; color:#6e6e73;
  }
  .pills { display:flex; gap:8px; margin-top:16px; flex-wrap:wrap; }
  .pill {
    padding:8px 14px; border-radius:999px; border:1px solid rgba(255,255,255,.14);
    font-family:'JetBrains Mono',monospace; font-size:15px; color:#c7c7cc;
  }
  .arrow { color:#2AB6F5; font-weight:700; }
  .srcline {
    margin-top:14px; font-family:'JetBrains Mono',monospace; font-size:16px; color:#6e6e73;
  }

  /* ---------- link sticker + footer ---------- */
  /* リンクスティッカー（実物のピル型に合わせた実寸相当の余白） */
  .sticker { margin:auto auto 64px; width:400px; height:104px; position:relative; }
  .sticker i {
    position:absolute; width:22px; height:22px; border:2px solid rgba(255,255,255,.18);
  }
  .sticker i:nth-child(1){ top:0; left:0; border-right:0; border-bottom:0; }
  .sticker i:nth-child(2){ top:0; right:0; border-left:0; border-bottom:0; }
  .sticker i:nth-child(3){ bottom:0; left:0; border-right:0; border-top:0; }
  .sticker i:nth-child(4){ bottom:0; right:0; border-left:0; border-top:0; }
</style>
</head>
<body>
<div class="page">

  <div class="brand">
    <div class="mark"></div>
    <div>
      <h1>HEALTH.OJIMPO.COM</h1>
      <div class="tag">文化的生活ダッシュボード</div>
    </div>
  </div>
  <div class="lede">この夏のアップデートの、すべて。</div>
  <div class="stats">
    2026.07.02 — 08.16<span class="sep">·</span>33 commits<span class="sep">·</span><span class="add">+5,350</span> −374<span class="sep">·</span>65 files
  </div>

  <div class="bento">

    <!-- hero -->
    <div class="card hero" style="grid-area:1 / 1 / 2 / 7;">
      <div class="shot"></div>
      <div class="veil"></div>
      <div class="inner">
        <div class="word">TRUST</div>
        <div class="lead">計測の信頼性を、根本から見直した。</div>
        <div class="lead-sub">壊れたソースを検知し、スコアから外し、外したことを必ず見せる。</div>
      </div>
    </div>

    <!-- 縦長: 配信ゲート -->
    <div class="card" style="grid-area:2 / 1 / 4 / 3;">
      <div class="kicker">配信前の本人確認</div>
      <div class="word-lg word-md">CONSENT</div>
      <div class="sub" style="margin-bottom:20px;">警告は、本人に断ってから。</div>
      <div class="flow">
        <div class="node">健康スコアが CAUTION<small>3回連続で持続を確認</small></div>
        <div class="link"><span>本人に確認</span></div>
        <div class="node" style="padding:11px 12px;">
          <div class="choices" style="margin-top:0; gap:6px; font-size:13px;">
            <span style="font-size:13px; padding:8px 0;">配信しない</span>
            <span style="font-size:13px; padding:8px 0;">今すぐ</span>
            <span style="font-size:13px; padding:8px 0;">24h待つ</span>
          </div>
        </div>
        <div class="link"><span>無応答のまま期限</span></div>
        <div class="node accent">友人へ配信</div>
      </div>
    </div>

    <!-- 取得量の急減 -->
    <div class="card" style="grid-area:2 / 3 / 3 / 7;">
      <div class="kicker">取得量の急減を検知</div>
      <div style="display:flex; align-items:flex-end; gap:26px; margin-top:auto;">
        <div style="flex:none;">
          <div class="metric" style="font-size:66px; margin:0 0 6px;">30<span class="unit" style="font-size:30px;">%</span></div>
          <div class="sub" style="margin:0;">平常の3割を割ったら<br>データ断とみなす。</div>
        </div>
        <svg viewBox="0 0 380 118" style="flex:1; width:100%; height:auto;">
          <defs>
            <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#ffffff" stop-opacity=".22"/>
              <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <path fill="url(#g1)" d="M0,46 L16,32 L32,41 L48,28 L64,37 L80,31 L96,43 L112,29 L128,39 L144,34 L160,27 L176,41 L192,32 L208,37 L218,48 L228,96 L244,100 L260,94 L276,101 L292,97 L308,100 L324,95 L340,101 L356,98 L372,100 L380,99 L380,118 L0,118 Z"/>
          <path fill="none" stroke="#f5f5f7" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"
                d="M0,46 L16,32 L32,41 L48,28 L64,37 L80,31 L96,43 L112,29 L128,39 L144,34 L160,27 L176,41 L192,32 L208,37 L218,48 L228,96 L244,100 L260,94 L276,101 L292,97 L308,100 L324,95 L340,101 L356,98 L372,100 L380,99"/>
          <line x1="0" y1="79" x2="380" y2="79" stroke="#2AB6F5" stroke-width="1.6" stroke-dasharray="6 6" opacity=".9"/>
          <text x="4" y="72" font-family="JetBrains Mono" font-size="12" fill="#2AB6F5">30% threshold</text>
          <line x1="300" y1="14" x2="300" y2="118" stroke="#ffffff" stroke-width="1.2" opacity=".35" stroke-dasharray="4 5"/>
          <circle cx="300" cy="99" r="4.5" fill="#2AB6F5"/>
          <text x="308" y="22" font-family="JetBrains Mono" font-size="12" fill="#c7c7cc">detected</text>
        </svg>
      </div>
    </div>

    <!-- 端末ごとの沈黙 -->
    <div class="card" style="grid-area:3 / 3 / 4 / 7;">
      <div class="kicker">端末ごとの沈黙も見張る</div>
      <svg viewBox="0 0 560 104" style="width:100%; height:auto; margin-top:14px;">
        <text x="0" y="18" font-family="JetBrains Mono" font-size="13" fill="#86868b">arigato-nas</text>
        <text x="0" y="52" font-family="JetBrains Mono" font-size="13" fill="#86868b">HACHIMAN-DESK</text>
        <text x="0" y="86" font-family="JetBrains Mono" font-size="13" fill="#86868b">MacBook</text>
        <line x1="150" y1="14" x2="560" y2="14" stroke="#ffffff" stroke-width="1" opacity=".12"/>
        <line x1="150" y1="48" x2="560" y2="48" stroke="#ffffff" stroke-width="1" opacity=".12"/>
        <line x1="150" y1="82" x2="560" y2="82" stroke="#ffffff" stroke-width="1" opacity=".12"/>
        <g fill="#f5f5f7">
          <circle cx="158" cy="14" r="4"/><circle cx="180" cy="14" r="4"/><circle cx="202" cy="14" r="4"/>
          <circle cx="540" cy="14" r="4"/>
          <circle cx="158" cy="48" r="4"/><circle cx="190" cy="48" r="4"/><circle cx="228" cy="48" r="4"/>
          <circle cx="266" cy="48" r="4"/><circle cx="310" cy="48" r="4"/><circle cx="352" cy="48" r="4"/>
          <circle cx="400" cy="48" r="4"/><circle cx="452" cy="48" r="4"/><circle cx="500" cy="48" r="4"/>
          <circle cx="540" cy="48" r="4"/>
          <circle cx="168" cy="82" r="4"/><circle cx="214" cy="82" r="4"/><circle cx="262" cy="82" r="4"/>
          <circle cx="330" cy="82" r="4"/><circle cx="396" cy="82" r="4"/><circle cx="470" cy="82" r="4"/>
          <circle cx="538" cy="82" r="4"/>
        </g>
        <rect x="210" y="2" width="326" height="24" rx="12" fill="#2AB6F5" opacity=".13"/>
        <text x="248" y="19" font-family="JetBrains Mono" font-size="13" fill="#8FE9FF">3 months silent</text>
      </svg>
      <div class="fig-cap">閾値は端末ごとに自動較正（送信間隔の中央値 × 4）</div>
    </div>

    <!-- 計測障害 -->
    <div class="card" style="grid-area:4 / 1 / 5 / 3;">
      <div class="kicker">計測障害の検知</div>
      <div class="title sm" style="margin-top:8px;">壊れた計測は、<br>軸から外す。</div>
      <svg viewBox="0 0 254 104" style="width:100%; height:auto; margin-top:auto;">
        <rect x="0"   y="36" width="28" height="68" rx="7" fill="#f5f5f7" opacity=".85"/>
        <rect x="38"  y="18" width="28" height="86" rx="7" fill="#f5f5f7" opacity=".85"/>
        <rect x="76"  y="46" width="28" height="58" rx="7" fill="#f5f5f7" opacity=".85"/>
        <rect x="114" y="26" width="28" height="78" rx="7" fill="#f5f5f7" opacity=".85"/>
        <rect x="152" y="62" width="28" height="42" rx="7" fill="none" stroke="#6e6e73" stroke-width="1.8" stroke-dasharray="5 4"/>
        <rect x="190" y="30" width="28" height="74" rx="7" fill="#f5f5f7" opacity=".85"/>
        <rect x="226" y="40" width="28" height="64" rx="7" fill="#f5f5f7" opacity=".85"/>
      </svg>
      <div class="badge" style="margin-top:14px;"><span class="dot"></span>計測不能: 音楽</div>
    </div>

    <!-- 写真カテゴリ -->
    <div class="card" style="grid-area:4 / 3 / 5 / 5;">
      <div class="kicker">新カテゴリ</div>
      <div class="word-lg word-md">PHOTOS</div>
      <div class="sub" style="margin-top:0;">撮った枚数も、<br>文化として数える。</div>
      <div class="fig">
        <div class="strip"><span class="name">iPhone</span><span class="cells"><i></i><i></i><i></i><i></i><i></i><i></i></span></div>
        <div class="strip sub"><span class="name">X-E5</span><span class="cells"><i></i><i></i><i></i></span></div>
      </div>
    </div>

    <!-- 主観フィードバック -->
    <div class="card" style="grid-area:4 / 5 / 5 / 7;">
      <div class="kicker">主観フィードバック</div>
      <div class="metric" style="font-size:62px; margin:10px 0 4px;">21:00</div>
      <div class="sub" style="margin-top:0;">毎晩、その日の調子を。</div>
      <div class="bubble" style="margin-top:auto; font-size:15px; padding:12px 14px;">今日の調子はどうでしたか？
        <div class="choices"><span>良い</span><span>普通</span><span>悪い</span></div>
      </div>
    </div>

    <!-- 再較正 -->
    <div class="card" style="grid-area:5 / 1 / 6 / 4;">
      <div class="kicker">スコアの再較正</div>
      <div class="rows">
        <div><span class="cat">活力</span><span class="chg">再生回数 <span class="arrow">→</span> 再生時間</span><span class="val">180 min / week</span></div>
        <div><span class="cat">CD貸出</span><span class="chg">baseline <span class="arrow">→</span> event</span><span class="val">48 discs / 90 days</span></div>
        <div><span class="cat">運動</span><span class="chg">Strava <span class="arrow">+</span> 歩数</span><span class="val">oura_steps</span></div>
      </div>
    </div>

    <!-- リッチメニュー -->
    <div class="card" style="grid-area:5 / 4 / 6 / 7;">
      <div class="kicker">LINE リッチメニュー</div>
      <div class="title sm" style="margin-top:6px;">取り込みも点検も、ボタン1つで。</div>
      <div class="menu"><div>INGEST</div><div>HEALTH</div><div>MOOD</div></div>
    </div>

  </div>

  <div class="sticker"><i></i><i></i><i></i><i></i></div>
</div>
</body>
</html>`;

const out = process.argv[2] || 'output/story_20260816.html';
writeFileSync(resolve(here, out), html);
console.log('Wrote', resolve(here, out));
