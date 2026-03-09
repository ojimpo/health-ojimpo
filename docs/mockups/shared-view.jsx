import { useState, useMemo, useEffect } from "react";
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

// --- Categories ---
const activityCategories = [
  { key: "music", label: "音楽", color: "#00F0FF" },
  { key: "exercise", label: "運動", color: "#FF3366" },
  { key: "reading", label: "読書", color: "#ADFF2F" },
  { key: "movie", label: "映画", color: "#FF9500" },
  { key: "sns", label: "SNS", color: "#BD93F9" },
  { key: "coding", label: "コーディング", color: "#50FA7B" },
  { key: "calendar", label: "予定", color: "#FFB86C" },
];

const stateCategories = [
  { key: "sleep", label: "Sleep Score", color: "#BD93F9" },
  { key: "readiness", label: "Readiness", color: "#00F0FF" },
  { key: "stress", label: "Stress", color: "#FF3366" },
];

// --- Status Configs ---
const HEALTH_STATUS = {
  NORMAL: { color: "#50FA7B", label: "健康状態", msg: "ベースライン指標は安定しています" },
  CAUTION: { color: "#FFB86C", label: "健康状態", msg: "ベースライン指標がやや低下しています" },
  CRITICAL: { color: "#FF1744", label: "健康状態", msg: "ベースライン指標が大幅に低下しています" },
};
const CULTURAL_STATUS = {
  RICH: { color: "#00F0FF", label: "文化活動", msg: "文化活動は豊かです" },
  MODERATE: { color: "#FFB86C", label: "文化活動", msg: "文化活動がやや控えめです" },
  LOW: { color: "#FF3366", label: "文化活動", msg: "文化活動がほぼ停止しています" },
};

// --- Data ---
const generateData = (scenario) => {
  const weeks = [];
  const now = new Date(2026, 2, 9);
  for (let i = 12; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i * 7);
    const weekLabel = `${d.getMonth() + 1}/${d.getDate()}`;
    let dip = 1;
    if (scenario === "critical_low") dip = i <= 4 ? 0.12 + i * 0.04 : i <= 7 ? 0.5 : 1;
    else if (scenario === "caution_moderate") dip = i <= 3 ? 0.55 : i <= 6 ? 0.75 : 1;

    weeks.push({
      week: weekLabel,
      music: Math.round((55 + Math.random() * 30) * dip),
      exercise: Math.round((35 + Math.random() * 25) * dip),
      reading: Math.round((20 + Math.random() * 40) * dip * (0.7 + Math.random() * 0.5)),
      movie: Math.round((10 + Math.random() * 20) * dip * (Math.random() > 0.3 ? 1 : 0.1)),
      sns: Math.round((40 + Math.random() * 20) * dip),
      coding: Math.round((15 + Math.random() * 35) * dip * (0.5 + Math.random() * 0.7)),
      calendar: Math.round((10 + Math.random() * 15) * dip),
      sleep: Math.round(60 + 25 * dip + Math.random() * 10),
      readiness: Math.round(55 + 30 * dip + Math.random() * 10),
      stress: Math.round(80 - 35 * dip + Math.random() * 15),
    });
  }
  return weeks;
};

const getTrendComments = (scenario) => {
  if (scenario === "critical_low") return [
    { text: "文化活動総量が4週連続で大幅に低下しています", type: "warning" },
    { text: "ベースライン指標（SNS・音楽）がほぼ停止しています", type: "warning" },
    { text: "早めに連絡を取ることを推奨します", type: "warning" },
  ];
  if (scenario === "caution_moderate") return [
    { text: "文化活動総量が2週連続で低下傾向にあります", type: "warning" },
    { text: "音楽の再生時間が減少しています", type: "warning" },
    { text: "運動量は維持されています", type: "positive" },
  ];
  return [
    { text: "文化活動総量は安定しています", type: "positive" },
    { text: "読書が増加傾向", type: "positive" },
    { text: "バランスの良い活動パターンです", type: "neutral" },
  ];
};

const getRecentActivity = (scenario) => {
  if (scenario === "critical_low") return [
    { time: "3日前", icon: "♫", text: "音楽を32分再生", color: "#00F0FF", dimmed: true },
    { time: "5日前", icon: "🚲", text: "通勤ライドを記録", color: "#FF3366", dimmed: true },
    { time: "8日前", icon: "♫", text: "音楽を15分再生", color: "#00F0FF", dimmed: true },
  ];
  if (scenario === "caution_moderate") return [
    { time: "1日前", icon: "♫", text: "音楽を1時間12分再生", color: "#00F0FF" },
    { time: "1日前", icon: "🚲", text: "通勤ライドを記録", color: "#FF3366" },
    { time: "2日前", icon: "📷", text: "Instagramを閲覧", color: "#BD93F9" },
    { time: "3日前", icon: "♫", text: "音楽を48分再生", color: "#00F0FF" },
    { time: "5日前", icon: "📖", text: "1冊の本を読了", color: "#ADFF2F" },
  ];
  return [
    { time: "1日前", icon: "📖", text: "1冊の本を読了", color: "#ADFF2F" },
    { time: "1日前", icon: "♫", text: "音楽を2時間34分再生", color: "#00F0FF" },
    { time: "1日前", icon: "📷", text: "Instagramを閲覧", color: "#BD93F9" },
    { time: "1日前", icon: "🚲", text: "通勤ライドを記録", color: "#FF3366" },
    { time: "2日前", icon: "🎬", text: "1本の映画を鑑賞", color: "#FF9500" },
    { time: "2日前", icon: "💻", text: "コーディング活動を記録", color: "#50FA7B" },
    { time: "3日前", icon: "📅", text: "休日に2件の予定", color: "#FFB86C" },
    { time: "3日前", icon: "🏃", text: "休日ランニング 5.2km", color: "#FF3366" },
  ];
};

// --- EVA Warning Overlay ---
const EvaWarningOverlay = () => {
  const [flash, setFlash] = useState(true);
  useEffect(() => { const iv = setInterval(() => setFlash(f => !f), 800); return () => clearInterval(iv); }, []);
  return (<>
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,0,0,0.03) 2px, rgba(255,0,0,0.03) 4px)", pointerEvents: "none", zIndex: 10 }} />
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: `radial-gradient(ellipse at center, transparent 40%, rgba(255,23,68,${flash ? 0.15 : 0.05}) 100%)`, pointerEvents: "none", zIndex: 10, transition: "background 0.8s ease" }} />
    {[{ top: 20, left: 20 }, { top: 20, right: 20 }, { bottom: 20, left: 20 }, { bottom: 20, right: 20 }].map((pos, i) => (
      <div key={i} style={{ position: "fixed", ...pos, zIndex: 11, fontFamily: "'Orbitron', sans-serif", fontSize: 10, letterSpacing: 4, color: flash ? "#FF1744" : "rgba(255,23,68,0.3)", transition: "color 0.4s ease" }}>WARNING</div>
    ))}
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 4, background: "repeating-linear-gradient(45deg, #FF1744, #FF1744 10px, #000 10px, #000 20px)", opacity: flash ? 0.8 : 0.3, transition: "opacity 0.4s ease", zIndex: 11 }} />
    <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, height: 4, background: "repeating-linear-gradient(45deg, #FF1744, #FF1744 10px, #000 10px, #000 20px)", opacity: flash ? 0.8 : 0.3, transition: "opacity 0.4s ease", zIndex: 11 }} />
  </>);
};

// --- Tooltips ---
const ActivityTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null;
  const total = payload.reduce((s, p) => s + (p.value || 0), 0);
  return (
    <div style={{ background: "rgba(10,10,20,0.95)", border: "1px solid rgba(0,240,255,0.3)", borderRadius: 8, padding: "12px 16px", fontFamily: "'JetBrains Mono', monospace" }}>
      <div style={{ color: "#00F0FF", fontSize: 11, marginBottom: 8, letterSpacing: 1 }}>WEEK {label}</div>
      {[...payload].reverse().map((p, i) => (
        <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 24, fontSize: 12, color: p.color, padding: "2px 0" }}>
          <span style={{ opacity: 0.8 }}>{activityCategories.find(c => c.key === p.dataKey)?.label}</span>
          <span style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", marginTop: 8, paddingTop: 8, display: "flex", justifyContent: "space-between", color: "#fff", fontSize: 12, fontWeight: 700 }}>
        <span>TOTAL</span><span>{total}</span>
      </div>
    </div>
  );
};

const StateTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null;
  return (
    <div style={{ background: "rgba(10,10,20,0.95)", border: "1px solid rgba(189,147,249,0.3)", borderRadius: 8, padding: "12px 16px", fontFamily: "'JetBrains Mono', monospace" }}>
      <div style={{ color: "#BD93F9", fontSize: 11, marginBottom: 8, letterSpacing: 1 }}>WEEK {label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 24, fontSize: 12, color: p.color, padding: "2px 0" }}>
          <span style={{ opacity: 0.8 }}>{stateCategories.find(c => c.key === p.dataKey)?.label}</span>
          <span style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
};

// --- Main ---
export default function SharedView() {
  const [scenario, setScenario] = useState("normal_rich");
  const [flash, setFlash] = useState(true);

  const data = useMemo(() => generateData(scenario), [scenario]);
  const comments = useMemo(() => getTrendComments(scenario), [scenario]);
  const activities = useMemo(() => getRecentActivity(scenario), [scenario]);

  const isCritical = scenario === "critical_low";
  const isCaution = scenario === "caution_moderate";

  useEffect(() => {
    if (!isCritical) return;
    const iv = setInterval(() => setFlash(f => !f), 800);
    return () => clearInterval(iv);
  }, [isCritical]);

  // Compute scores
  const baselineScore = useMemo(() => {
    const last = data[data.length - 1];
    const scores = [(last.music / 75) * 100, (last.sns / 50) * 100];
    return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
  }, [data]);

  const culturalScore = useMemo(() => {
    const last = data[data.length - 1];
    const total = activityCategories.reduce((s, c) => s + (last[c.key] || 0), 0);
    return Math.round((total / 220) * 100);
  }, [data]);

  const healthKey = baselineScore >= 70 ? "NORMAL" : baselineScore >= 40 ? "CAUTION" : "CRITICAL";
  const culturalKey = culturalScore >= 70 ? "RICH" : culturalScore >= 40 ? "MODERATE" : "LOW";
  const hStatus = HEALTH_STATUS[healthKey];
  const cStatus = CULTURAL_STATUS[culturalKey];

  // Visual effect matrix
  const isLow = culturalKey === "LOW";
  const chartSaturation = isLow ? 0.2 : culturalKey === "MODERATE" ? 0.6 : 1;
  const getChartColor = (color) => {
    if (isCritical) return "#FF1744";
    if (isLow) return "rgba(255,255,255,0.3)";
    return color;
  };

  const accentColor = isCritical ? "#FF1744" : isCaution ? "#FFB86C" : "#00F0FF";
  const bgColor = isCritical ? "#0A0000" : "#07080F";

  return (
    <div style={{ minHeight: "100vh", background: bgColor, color: "#E0E0E0", fontFamily: "'JetBrains Mono', monospace", position: "relative", overflow: "hidden", transition: "background 0.6s ease" }}>
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Orbitron:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />

      {isCritical && <EvaWarningOverlay />}

      <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: isCritical ? "radial-gradient(ellipse at 50% 50%, rgba(255,23,68,0.05) 0%, transparent 70%)" : "radial-gradient(ellipse at 20% 50%, rgba(0,240,255,0.03) 0%, transparent 60%)", pointerEvents: "none" }} />
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, backgroundImage: `linear-gradient(${isCritical ? "rgba(255,23,68,0.02)" : "rgba(0,240,255,0.015)"} 1px, transparent 1px), linear-gradient(90deg, ${isCritical ? "rgba(255,23,68,0.02)" : "rgba(0,240,255,0.015)"} 1px, transparent 1px)`, backgroundSize: "60px 60px", pointerEvents: "none" }} />

      <div style={{ position: "relative", zIndex: 5, maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>

        {/* Demo switcher */}
        <div style={{ display: "flex", gap: 6, marginBottom: 28, padding: "8px 12px", background: "rgba(255,255,255,0.03)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)", width: "fit-content" }}>
          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", letterSpacing: 2, alignSelf: "center", marginRight: 8 }}>DEMO</span>
          {[
            { key: "normal_rich", label: "NORMAL / RICH", color: "#50FA7B" },
            { key: "caution_moderate", label: "CAUTION / MODERATE", color: "#FFB86C" },
            { key: "critical_low", label: "CRITICAL / LOW", color: "#FF1744" },
          ].map(s => (
            <button key={s.key} onClick={() => setScenario(s.key)} style={{
              background: scenario === s.key ? s.color + "20" : "transparent",
              border: `1px solid ${scenario === s.key ? s.color + "60" : "rgba(255,255,255,0.08)"}`,
              borderRadius: 6, padding: "5px 14px", color: scenario === s.key ? s.color : "rgba(255,255,255,0.3)",
              fontSize: 10, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1, cursor: "pointer", transition: "all 0.3s ease",
            }}>{s.label}</button>
          ))}
        </div>

        {/* Header */}
        <header style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: accentColor, boxShadow: `0 0 12px ${accentColor}`, animation: isCritical ? "none" : "pulse 2s ease-in-out infinite" }} />
            <span style={{ fontSize: 11, letterSpacing: 4, color: "rgba(255,255,255,0.4)" }}>SHARED VIEW</span>
          </div>
          <h1 style={{
            fontFamily: "'Orbitron', sans-serif", fontSize: 36, fontWeight: 800, letterSpacing: 3, margin: 0,
            color: isCritical ? (flash ? "#FF1744" : "#FF174480") : undefined,
            background: isCritical ? undefined : "linear-gradient(135deg, #00F0FF 0%, #BD93F9 50%, #FF3366 100%)",
            WebkitBackgroundClip: isCritical ? undefined : "text", WebkitTextFillColor: isCritical ? undefined : "transparent",
            lineHeight: 1.2, transition: "color 0.4s ease",
          }}>HEALTH.OJIMPO.COM</h1>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", margin: "8px 0 0", letterSpacing: 1 }}>
            文化的生活ダッシュボード — 日々の文化活動から健康状態をモニタリングしています
          </p>
          <style>{`
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            @keyframes fadeInUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
            @keyframes criticalPulse { 0%, 100% { box-shadow: 0 0 20px rgba(255,23,68,0.2), inset 0 0 20px rgba(255,23,68,0.05); } 50% { box-shadow: 0 0 40px rgba(255,23,68,0.4), inset 0 0 40px rgba(255,23,68,0.1); } }
            @keyframes textGlitch { 0%, 90%, 100% { transform: none; opacity: 1; } 92% { transform: translateX(-2px) skewX(-1deg); opacity: 0.8; } 94% { transform: translateX(2px); opacity: 1; } 96% { transform: translateX(-1px) skewX(0.5deg); opacity: 0.9; } }
          `}</style>
        </header>

        {/* DUAL STATUS */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 28 }}>
          {/* Health */}
          <div style={{
            background: `linear-gradient(135deg, ${hStatus.color}08 0%, transparent 100%)`,
            border: `2px solid ${isCritical && flash ? hStatus.color : hStatus.color + "30"}`,
            borderRadius: 14, padding: "24px 28px",
            animation: isCritical ? "criticalPulse 1.6s ease-in-out infinite" : "fadeInUp 0.5s ease-out",
            transition: "border-color 0.4s ease",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: hStatus.color, boxShadow: `0 0 10px ${hStatus.color}60` }} />
              <span style={{
                fontFamily: "'Orbitron', sans-serif", fontSize: isCritical ? 15 : 13, fontWeight: 700, letterSpacing: 4, color: hStatus.color,
                textShadow: isCritical ? `0 0 20px ${hStatus.color}` : "none",
                animation: isCritical ? "textGlitch 3s ease-in-out infinite" : "none",
              }}>{healthKey}</span>
            </div>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", marginBottom: 6 }}>{hStatus.label}</div>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 32, fontWeight: 700, color: hStatus.color, textShadow: isCritical ? `0 0 20px ${hStatus.color}` : "none" }}>{baselineScore}</span>
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", marginLeft: 6 }}>/ 100</span>
            <p style={{ fontSize: 12, color: isCritical ? "rgba(255,200,200,0.6)" : "rgba(255,255,255,0.35)", margin: "8px 0 0", lineHeight: 1.6 }}>{hStatus.msg}</p>
          </div>
          {/* Cultural */}
          <div style={{
            background: `linear-gradient(135deg, ${cStatus.color}08 0%, transparent 100%)`,
            border: `2px solid ${cStatus.color}30`,
            borderRadius: 14, padding: "24px 28px",
            animation: "fadeInUp 0.5s ease-out 0.1s both",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: cStatus.color, boxShadow: `0 0 10px ${cStatus.color}60` }} />
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 13, fontWeight: 700, letterSpacing: 4, color: cStatus.color }}>{culturalKey}</span>
            </div>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", marginBottom: 6 }}>{cStatus.label}</div>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 32, fontWeight: 700, color: cStatus.color }}>{culturalScore}</span>
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", marginLeft: 6 }}>%</span>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", margin: "8px 0 0", lineHeight: 1.6 }}>{cStatus.msg}</p>
          </div>
        </div>

        {/* Friendly message */}
        <div style={{
          background: `linear-gradient(135deg, ${hStatus.color}06 0%, transparent 100%)`,
          border: `1px solid ${hStatus.color}15`, borderRadius: 12, padding: "16px 24px", marginBottom: 28,
        }}>
          <p style={{ fontSize: 14, color: isCritical ? "rgba(255,180,180,0.7)" : "rgba(255,255,255,0.5)", margin: 0, lineHeight: 1.8 }}>
            {scenario === "normal_rich" && "健康だと思われるのでいつも通り接して大丈夫です。"}
            {scenario === "caution_moderate" && "少し気にかけてあげてください。さりげなく連絡してみるのもいいかもしれません。"}
            {scenario === "critical_low" && "文化活動が大幅に低下しています。連絡を取ってみてください。"}
          </p>
        </div>

        {/* Trend Analysis */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: `1px solid ${isCritical ? "rgba(255,23,68,0.15)" : "rgba(255,255,255,0.06)"}`, borderRadius: 12, padding: "18px 24px", marginBottom: 28 }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 10 }}>TREND ANALYSIS</div>
          {comments.map((c, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: c.type === "positive" ? "#50FA7B" : c.type === "warning" ? "#FF1744" : "#FFB86C", boxShadow: `0 0 8px ${c.type === "positive" ? "#50FA7B" : "#FF1744"}`, flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>{c.text}</span>
            </div>
          ))}
        </div>

        {/* Upper chart: Stacked Area */}
        <div style={{ fontSize: 10, letterSpacing: 3, color: `${accentColor}80`, marginBottom: 8 }}>CULTURAL ACTIVITY</div>
        <div style={{ background: "rgba(255,255,255,0.02)", border: `1px solid ${isCritical ? "rgba(255,23,68,0.1)" : "rgba(255,255,255,0.06)"}`, borderRadius: 16, padding: "24px 16px 16px 0", marginBottom: 16, filter: isLow ? "saturate(0.15)" : culturalKey === "MODERATE" ? "saturate(0.6)" : "none", transition: "filter 0.6s ease" }}>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <defs>
                {activityCategories.map(c => (
                  <linearGradient key={c.key} id={`sg-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={getChartColor(c.color)} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={getChartColor(c.color)} stopOpacity={0.05} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono'" }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "rgba(255,255,255,0.15)", fontFamily: "'JetBrains Mono'" }} axisLine={false} tickLine={false} />
              <ReferenceLine y={100} stroke="rgba(255,255,255,0.06)" strokeDasharray="6 4" />
              <Tooltip content={<ActivityTooltip />} />
              {activityCategories.map(c => (
                <Area key={c.key} type="linear" dataKey={c.key} stackId="1"
                  stroke={getChartColor(c.color)} strokeWidth={1.5} fill={`url(#sg-${c.key})`} strokeOpacity={0.8}
                  dot={{ r: 2, fill: getChartColor(c.color), strokeWidth: 0, opacity: 0.7 }}
                  activeDot={{ r: 4, fill: getChartColor(c.color), stroke: bgColor, strokeWidth: 2 }}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Lower chart: Line (State) */}
        <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(189,147,249,0.5)", marginBottom: 8 }}>CONDITION</div>
        <div style={{ background: "rgba(255,255,255,0.02)", border: `1px solid ${isCritical ? "rgba(255,23,68,0.1)" : "rgba(255,255,255,0.06)"}`, borderRadius: 16, padding: "24px 16px 16px 0", marginBottom: 28 }}>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono'" }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "rgba(255,255,255,0.15)", fontFamily: "'JetBrains Mono'" }} axisLine={false} tickLine={false} domain={[0, 'auto']} />
              <Tooltip content={<StateTooltip />} />
              {stateCategories.map(c => (
                <Line key={c.key} type="linear" dataKey={c.key} stroke={isCritical ? "#FF1744" : c.color} strokeWidth={2} strokeOpacity={0.8}
                  dot={{ r: 2, fill: isCritical ? "#FF1744" : c.color, strokeWidth: 0 }}
                  activeDot={{ r: 4, fill: isCritical ? "#FF1744" : c.color, stroke: bgColor, strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Category cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8, marginBottom: 28 }}>
          {activityCategories.map((c, i) => {
            const val = data[data.length - 1][c.key];
            return (
              <div key={c.key} style={{ background: "rgba(255,255,255,0.02)", border: `1px solid ${isCritical ? "rgba(255,23,68,0.1)" : "rgba(255,255,255,0.06)"}`, borderRadius: 8, padding: "12px 14px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: getChartColor(c.color), boxShadow: `0 0 6px ${getChartColor(c.color)}50` }} />
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", letterSpacing: 1 }}>{c.label}</span>
                </div>
                <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 20, fontWeight: 600, color: getChartColor(c.color) }}>{val}</span>
              </div>
            );
          })}
        </div>

        {/* Recent Activity */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: `1px solid ${isCritical ? "rgba(255,23,68,0.1)" : "rgba(255,255,255,0.06)"}`, borderRadius: 12, padding: "20px 24px", marginBottom: 48 }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>RECENT ACTIVITY</div>
          {activities.map((item, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 0", borderBottom: i < activities.length - 1 ? "1px solid rgba(255,255,255,0.03)" : "none", opacity: item.dimmed ? 0.4 : 0.8 }}>
              <span style={{ fontSize: 14, width: 20, textAlign: "center", flexShrink: 0 }}>{item.icon}</span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.25)", width: 48, flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>{item.time}</span>
              <span style={{ fontSize: 13, color: isCritical ? "rgba(255,100,100,0.5)" : `${item.color}CC` }}>{item.text}</span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <footer style={{ paddingTop: 24, borderTop: `1px solid ${isCritical ? "rgba(255,23,68,0.08)" : "rgba(255,255,255,0.04)"}`, display: "flex", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.15)", letterSpacing: 1 }}>health.ojimpo.com — Shared View v0.5</span>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.1)" }}>Design Mockup — 2026.03</span>
        </footer>
      </div>
    </div>
  );
}
