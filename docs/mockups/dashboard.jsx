import { useState, useMemo } from "react";
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

// --- Activity categories (stacked area chart) ---
const activityCategories = [
  { key: "music", label: "音楽", color: "#00F0FF" },
  { key: "exercise", label: "運動", color: "#FF3366" },
  { key: "reading", label: "読書", color: "#ADFF2F" },
  { key: "movie", label: "映画", color: "#FF9500" },
  { key: "sns", label: "SNS", color: "#BD93F9" },
  { key: "coding", label: "コーディング", color: "#50FA7B" },
  { key: "calendar", label: "予定", color: "#FFB86C" },
];

// --- State categories (line chart) ---
const stateCategories = [
  { key: "sleep", label: "Sleep Score", color: "#BD93F9" },
  { key: "readiness", label: "Readiness", color: "#00F0FF" },
  { key: "stress", label: "Stress", color: "#FF3366" },
  { key: "weight", label: "体重", color: "#F8F8F2" },
];

// --- Generate mock data ---
const generateData = () => {
  const weeks = [];
  const now = new Date(2026, 2, 9);
  for (let i = 12; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i * 7);
    const weekLabel = `${d.getMonth() + 1}/${d.getDate()}`;
    const dip = (i >= 5 && i <= 7) ? 0.35 : (i >= 3 && i <= 4) ? 0.7 : 1;

    weeks.push({
      week: weekLabel,
      music: Math.round((55 + Math.random() * 30) * dip),
      exercise: Math.round((35 + Math.random() * 25) * dip),
      reading: Math.round((20 + Math.random() * 40) * dip * (0.8 + Math.random() * 0.4)),
      movie: Math.round((10 + Math.random() * 20) * dip * (Math.random() > 0.3 ? 1 : 0.2)),
      sns: Math.round((40 + Math.random() * 20) * dip),
      coding: Math.round((15 + Math.random() * 35) * dip * (0.6 + Math.random() * 0.6)),
      calendar: Math.round((10 + Math.random() * 15) * dip),
      sleep: Math.round(60 + 25 * dip + Math.random() * 10),
      readiness: Math.round(55 + 30 * dip + Math.random() * 10),
      stress: Math.round(80 - 35 * dip + Math.random() * 15),
      weight: +(68 + (1 - dip) * 2.5 + (Math.random() - 0.5) * 0.8).toFixed(1),
    });
  }
  return weeks;
};

const weeks = generateData();

const getTrendComments = () => [
  { text: "文化活動総量は前期比で回復傾向にあります", type: "positive" },
  { text: "読書が増加傾向", type: "positive" },
  { text: "睡眠スコアがやや低下気味", type: "warning" },
];

// --- Tooltips ---
const ActivityTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null;
  const total = payload.reduce((s, p) => s + (p.value || 0), 0);
  return (
    <div style={{ background: "rgba(10,10,20,0.95)", border: "1px solid rgba(0,240,255,0.3)", borderRadius: 8, padding: "12px 16px", backdropFilter: "blur(12px)", fontFamily: "'JetBrains Mono', monospace" }}>
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
    <div style={{ background: "rgba(10,10,20,0.95)", border: "1px solid rgba(189,147,249,0.3)", borderRadius: 8, padding: "12px 16px", backdropFilter: "blur(12px)", fontFamily: "'JetBrains Mono', monospace" }}>
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
export default function HealthDashboard() {
  const [hoveredCategory, setHoveredCategory] = useState(null);
  const [timeRange, setTimeRange] = useState("3m");
  const trendComments = useMemo(() => getTrendComments(), []);

  const baselineScore = useMemo(() => {
    const last = weeks[weeks.length - 1];
    const scores = [(last.music / 75) * 100, (last.sns / 50) * 100];
    return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
  }, []);

  const culturalScore = useMemo(() => {
    const last = weeks[weeks.length - 1];
    const total = activityCategories.reduce((s, c) => s + (last[c.key] || 0), 0);
    return Math.round((total / 220) * 100);
  }, []);

  const healthStatus = baselineScore >= 70 ? "NORMAL" : baselineScore >= 40 ? "CAUTION" : "CRITICAL";
  const culturalStatus = culturalScore >= 70 ? "RICH" : culturalScore >= 40 ? "MODERATE" : "LOW";
  const healthColor = { NORMAL: "#50FA7B", CAUTION: "#FFB86C", CRITICAL: "#FF1744" }[healthStatus];
  const culturalColor = { RICH: "#00F0FF", MODERATE: "#FFB86C", LOW: "#FF3366" }[culturalStatus];

  const totalActivity = useMemo(() => {
    const last = weeks[weeks.length - 1];
    return activityCategories.reduce((s, c) => s + (last[c.key] || 0), 0);
  }, []);
  const prevActivity = useMemo(() => {
    const prev = weeks[weeks.length - 3];
    return activityCategories.reduce((s, c) => s + (prev[c.key] || 0), 0);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: "#07080F", color: "#E0E0E0", fontFamily: "'JetBrains Mono', monospace", position: "relative", overflow: "hidden" }}>
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Orbitron:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "radial-gradient(ellipse at 20% 50%, rgba(0,240,255,0.03) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(255,51,102,0.02) 0%, transparent 50%)", pointerEvents: "none" }} />
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, backgroundImage: "linear-gradient(rgba(0,240,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,0.015) 1px, transparent 1px)", backgroundSize: "60px 60px", pointerEvents: "none" }} />

      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200, margin: "0 auto", padding: "32px 24px" }}>
        {/* Header */}
        <header style={{ marginBottom: 40 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#00F0FF", boxShadow: "0 0 12px #00F0FF, 0 0 24px rgba(0,240,255,0.3)", animation: "pulse 2s ease-in-out infinite" }} />
            <span style={{ fontSize: 11, letterSpacing: 4, color: "rgba(0,240,255,0.6)" }}>CULTURAL HEALTH DASHBOARD</span>
          </div>
          <h1 style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 42, fontWeight: 800, letterSpacing: 3, margin: 0, background: "linear-gradient(135deg, #00F0FF 0%, #BD93F9 50%, #FF3366 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", lineHeight: 1.2 }}>
            HEALTH.OJIMPO.COM
          </h1>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", margin: "8px 0 0", letterSpacing: 1 }}>文化的生活ダッシュボード — Monitoring your cultural vitality</p>
          <style>{`
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            @keyframes fadeInUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
            @keyframes slideIn { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
          `}</style>
        </header>

        {/* DUAL STATUS */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 28 }}>
          <div style={{ background: `linear-gradient(135deg, ${healthColor}08 0%, transparent 100%)`, border: `1px solid ${healthColor}30`, borderRadius: 14, padding: "24px 28px", animation: "fadeInUp 0.5s ease-out" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: healthColor, boxShadow: `0 0 10px ${healthColor}60` }} />
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 13, fontWeight: 700, letterSpacing: 4, color: healthColor }}>{healthStatus}</span>
            </div>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", marginBottom: 6 }}>健康状態</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 36, fontWeight: 700, color: healthColor, textShadow: `0 0 20px ${healthColor}30` }}>{baselineScore}</span>
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>/ 100</span>
            </div>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", margin: "8px 0 0", lineHeight: 1.6 }}>ベースライン指標は安定しています</p>
          </div>
          <div style={{ background: `linear-gradient(135deg, ${culturalColor}08 0%, transparent 100%)`, border: `1px solid ${culturalColor}30`, borderRadius: 14, padding: "24px 28px", animation: "fadeInUp 0.5s ease-out 0.1s both" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: culturalColor, boxShadow: `0 0 10px ${culturalColor}60` }} />
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 13, fontWeight: 700, letterSpacing: 4, color: culturalColor }}>{culturalStatus}</span>
            </div>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", marginBottom: 6 }}>文化活動</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 36, fontWeight: 700, color: culturalColor, textShadow: `0 0 20px ${culturalColor}30` }}>{culturalScore}</span>
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>%</span>
              <span style={{ fontSize: 13, color: (totalActivity - prevActivity) >= 0 ? "#50FA7B" : "#FF3366", fontWeight: 600, marginLeft: 8 }}>
                {(totalActivity - prevActivity) >= 0 ? "▲" : "▼"} {Math.abs(totalActivity - prevActivity)}
              </span>
            </div>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", margin: "8px 0 0", lineHeight: 1.6 }}>文化活動の総量は基準の{culturalScore}%です</p>
          </div>
        </div>

        {/* Trend Analysis */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, padding: "18px 24px", marginBottom: 28, animation: "fadeInUp 0.5s ease-out 0.15s both" }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 10 }}>TREND ANALYSIS</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {trendComments.map((c, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, animation: `slideIn 0.4s ease-out ${0.2 + i * 0.08}s both` }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: c.type === "positive" ? "#50FA7B" : "#FF3366", boxShadow: `0 0 8px ${c.type === "positive" ? "#50FA7B" : "#FF3366"}`, flexShrink: 0 }} />
                <span style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>{c.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Time range */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(0,240,255,0.5)" }}>CULTURAL ACTIVITY</div>
          <div style={{ display: "flex", gap: 4 }}>
            {[{ key: "1m", label: "1M" }, { key: "3m", label: "3M" }, { key: "1y", label: "1Y" }].map(t => (
              <button key={t.key} onClick={() => setTimeRange(t.key)} style={{
                background: timeRange === t.key ? "rgba(0,240,255,0.15)" : "transparent",
                border: `1px solid ${timeRange === t.key ? "rgba(0,240,255,0.4)" : "rgba(255,255,255,0.08)"}`,
                borderRadius: 6, padding: "6px 14px", color: timeRange === t.key ? "#00F0FF" : "rgba(255,255,255,0.3)",
                fontSize: 11, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1, cursor: "pointer", transition: "all 0.2s ease",
              }}>{t.label}</button>
            ))}
          </div>
        </div>

        {/* UPPER: Stacked Area */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 16, padding: "24px 16px 16px 0", marginBottom: 16, animation: "fadeInUp 0.5s ease-out 0.2s both" }}>
          <ResponsiveContainer width="100%" height={350}>
            <AreaChart data={weeks} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <defs>
                {activityCategories.map(c => (
                  <linearGradient key={c.key} id={`grad-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.color} stopOpacity={hoveredCategory === null || hoveredCategory === c.key ? 0.6 : 0.1} />
                    <stop offset="100%" stopColor={c.color} stopOpacity={hoveredCategory === null || hoveredCategory === c.key ? 0.08 : 0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "rgba(255,255,255,0.25)", fontFamily: "'JetBrains Mono'" }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono'" }} axisLine={false} tickLine={false} />
              <ReferenceLine y={100} stroke="rgba(255,255,255,0.08)" strokeDasharray="6 4" label={{ value: "BASE 100", position: "right", fill: "rgba(255,255,255,0.12)", fontSize: 9, fontFamily: "'JetBrains Mono'" }} />
              <Tooltip content={<ActivityTooltip />} />
              {activityCategories.map(c => (
                <Area key={c.key} type="linear" dataKey={c.key} stackId="1" stroke={c.color}
                  strokeWidth={hoveredCategory === null || hoveredCategory === c.key ? 1.5 : 0.5}
                  fill={`url(#grad-${c.key})`} strokeOpacity={hoveredCategory === null || hoveredCategory === c.key ? 0.8 : 0.15}
                  dot={{ r: 2, fill: c.color, strokeWidth: 0, opacity: hoveredCategory === null || hoveredCategory === c.key ? 0.8 : 0.15 }}
                  activeDot={{ r: 4, fill: c.color, stroke: "#07080F", strokeWidth: 2 }}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* LOWER: Line Chart (State) */}
        <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(189,147,249,0.5)", marginBottom: 8 }}>CONDITION</div>
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 16, padding: "24px 16px 16px 0", marginBottom: 28, animation: "fadeInUp 0.5s ease-out 0.25s both" }}>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={weeks} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "rgba(255,255,255,0.25)", fontFamily: "'JetBrains Mono'" }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono'" }} axisLine={false} tickLine={false} domain={[0, 'auto']} />
              <Tooltip content={<StateTooltip />} />
              {stateCategories.map(c => (
                <Line key={c.key} type="linear" dataKey={c.key} stroke={c.color} strokeWidth={2} strokeOpacity={0.8}
                  dot={{ r: 2, fill: c.color, strokeWidth: 0 }} activeDot={{ r: 4, fill: c.color, stroke: "#07080F", strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Activity category cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 16 }}>
          {activityCategories.map((c, i) => {
            const lastVal = weeks[weeks.length - 1][c.key];
            const prevVal = weeks[weeks.length - 3][c.key];
            const diff = lastVal - prevVal;
            return (
              <div key={c.key} onMouseEnter={() => setHoveredCategory(c.key)} onMouseLeave={() => setHoveredCategory(null)}
                style={{ background: hoveredCategory === c.key ? `${c.color}10` : "rgba(255,255,255,0.02)", border: `1px solid ${hoveredCategory === c.key ? c.color + "40" : "rgba(255,255,255,0.06)"}`, borderRadius: 10, padding: "14px 16px", cursor: "pointer", transition: "all 0.25s ease", animation: `fadeInUp 0.4s ease-out ${0.3 + i * 0.04}s both` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 3, background: c.color, boxShadow: `0 0 8px ${c.color}60` }} />
                  <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", letterSpacing: 1 }}>{c.label}</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 22, fontWeight: 600, color: c.color }}>{lastVal}</span>
                  <span style={{ fontSize: 11, color: diff >= 0 ? "#50FA7B" : "#FF3366" }}>{diff >= 0 ? "+" : ""}{diff}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* State indicator cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 32 }}>
          {stateCategories.map((c, i) => {
            const lastVal = weeks[weeks.length - 1][c.key];
            const prevVal = weeks[weeks.length - 3][c.key];
            const isStress = c.key === "stress";
            const diff = isStress ? prevVal - lastVal : lastVal - prevVal;
            return (
              <div key={c.key} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, padding: "14px 16px", animation: `fadeInUp 0.4s ease-out ${0.35 + i * 0.04}s both` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 10, height: 3, borderRadius: 2, background: c.color, boxShadow: `0 0 8px ${c.color}60` }} />
                  <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", letterSpacing: 1 }}>{c.label}</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 22, fontWeight: 600, color: c.color }}>{lastVal}</span>
                  <span style={{ fontSize: 11, color: diff >= 0 ? "#50FA7B" : "#FF3366" }}>
                    {diff >= 0 ? (isStress ? "▼" : "▲") : (isStress ? "▲" : "▼")} {Math.abs(+(lastVal - prevVal).toFixed(1))}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Recent Activity */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, padding: "20px 24px", marginBottom: 48, animation: "fadeInUp 0.5s ease-out 0.45s both" }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>RECENT ACTIVITY</div>
          {[
            { time: "1日前", icon: "📖", text: "1冊の本を読了", detail: "村上春樹『街とその不確かな壁』", color: "#ADFF2F" },
            { time: "1日前", icon: "♫", text: "音楽を2時間34分再生", detail: "32トラック再生", color: "#00F0FF" },
            { time: "1日前", icon: "📷", text: "Instagramを47分閲覧", detail: null, color: "#BD93F9" },
            { time: "1日前", icon: "🚲", text: "通勤ライドを記録", detail: "12.3km / 38分", color: "#FF3366" },
            { time: "2日前", icon: "🎬", text: "1本の映画を鑑賞", detail: "Filmarksに記録済み", color: "#FF9500" },
            { time: "2日前", icon: "💻", text: "コーディング活動を記録", detail: "GitHub: 4 commits", color: "#50FA7B" },
            { time: "3日前", icon: "📅", text: "休日に2件の予定", detail: null, color: "#FFB86C" },
            { time: "3日前", icon: "🏃", text: "休日ランニング 5.2km", detail: "Strava記録", color: "#FF3366" },
          ].map((item, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 0", borderBottom: i < 7 ? "1px solid rgba(255,255,255,0.03)" : "none" }}>
              <span style={{ fontSize: 14, width: 20, textAlign: "center", flexShrink: 0 }}>{item.icon}</span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.25)", width: 48, flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>{item.time}</span>
              <span style={{ fontSize: 13, color: `${item.color}CC` }}>{item.text}</span>
              {item.detail && <span style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", marginLeft: 4 }}>— {item.detail}</span>}
            </div>
          ))}
        </div>

        {/* Footer */}
        <footer style={{ paddingTop: 24, borderTop: "1px solid rgba(255,255,255,0.04)", display: "flex", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.15)", letterSpacing: 1 }}>health.ojimpo.com v0.5</span>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.1)" }}>Design Mockup — 2026.03</span>
        </footer>
      </div>
    </div>
  );
}
