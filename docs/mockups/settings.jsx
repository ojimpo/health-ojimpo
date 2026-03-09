import { useState } from "react";

// --- Data Source Definitions ---
const dataSources = [
  { id: "lastfm", name: "Last.fm", category: "音楽", icon: "♫", type: "activity", classification: "baseline", phase: "mvp", status: "active", color: "#00F0FF",
    config: { period: 7, unit: "日", baseValue: 700, baseUnit: "分再生", history: [{ from: "2026-03-01", value: 700, unit: "分再生", memo: "初期設定" }] } },
  { id: "strava", name: "Strava", category: "運動", icon: "🚲", type: "activity", classification: "both", phase: "phase2", status: "coming_soon", color: "#FF3366",
    config: { period: 30, unit: "日", baseValue: 200, baseUnit: "km", history: [{ from: "2026-03-01", value: 200, unit: "km", memo: "自転車通勤を開始" }] } },
  { id: "oura", name: "Oura", category: "睡眠", icon: "💤", type: "state", classification: "baseline", phase: "phase2", status: "coming_soon", color: "#BD93F9",
    config: { period: 7, unit: "日", baseValue: 80, baseUnit: "Readiness Score", history: [] } },
  { id: "intervals", name: "intervals.icu", category: "フィットネス", icon: "📊", type: "state", classification: "baseline", phase: "phase2", status: "coming_soon", color: "#50FA7B",
    config: { period: 30, unit: "日", baseValue: 50, baseUnit: "CTL", history: [] } },
  { id: "instagram", name: "Instagram", category: "SNS", icon: "📷", type: "activity", classification: "baseline", phase: "phase2", status: "coming_soon", color: "#FF9500",
    config: { period: 7, unit: "日", baseValue: 280, baseUnit: "分", history: [] } },
  { id: "twitter", name: "Twitter", category: "SNS", icon: "🐦", type: "activity", classification: "baseline", phase: "phase2", status: "coming_soon", color: "#1DA1F2",
    config: { period: 7, unit: "日", baseValue: 140, baseUnit: "分", history: [] } },
  { id: "gcal_holiday", name: "Googleカレンダー（休日予定）", category: "予定", icon: "📅", type: "activity", classification: "event", phase: "phase2", status: "coming_soon", color: "#FFB86C",
    config: { period: 30, unit: "日", baseValue: 8, baseUnit: "件", history: [] } },
  { id: "gcal_live", name: "Googleカレンダー（ライブ）", category: "音楽ライブ", icon: "🎸", type: "activity", classification: "event", phase: "phase2", status: "coming_soon", color: "#FF79C6",
    config: { period: 90, unit: "日", baseValue: 3, baseUnit: "回", history: [{ from: "2026-03-01", value: 3, unit: "回", memo: "月1ペースが目標" }] } },
  { id: "gmail", name: "Gmail", category: "買い物", icon: "🛒", type: "activity", classification: "baseline", phase: "phase2", status: "coming_soon", color: "#8BE9FD",
    config: { period: 30, unit: "日", baseValue: 10, baseUnit: "件", history: [] } },
  { id: "kashidashi", name: "kashidashi", category: "図書館", icon: "📚", type: "activity", classification: "event", phase: "phase2", status: "coming_soon", color: "#ADFF2F",
    config: { period: 30, unit: "日", baseValue: 5, baseUnit: "冊", history: [] } },
  { id: "bookmeter", name: "読書メーター", category: "読書", icon: "📖", type: "activity", classification: "event", phase: "phase3", status: "coming_soon", color: "#ADFF2F",
    config: { period: 90, unit: "日", baseValue: 21, baseUnit: "冊", history: [{ from: "2026-03-01", value: 21, unit: "冊", memo: "月7冊ペース" }] } },
  { id: "filmarks", name: "Filmarks", category: "映画", icon: "🎬", type: "activity", classification: "event", phase: "phase3", status: "coming_soon", color: "#FF9500",
    config: { period: 30, unit: "日", baseValue: 4, baseUnit: "本", history: [] } },
  { id: "github", name: "GitHub", category: "コーディング", icon: "💻", type: "activity", classification: "event", phase: "phase3", status: "coming_soon", color: "#50FA7B",
    config: { period: 30, unit: "日", baseValue: 60, baseUnit: "commits", history: [] } },
  { id: "anthropic", name: "Claude Code", category: "コーディング", icon: "🤖", type: "activity", classification: "event", phase: "phase3", status: "coming_soon", color: "#D4A574",
    config: { period: 30, unit: "日", baseValue: 500000, baseUnit: "tokens", history: [] } },
  { id: "openai", name: "Codex", category: "コーディング", icon: "🧠", type: "activity", classification: "event", phase: "phase3", status: "coming_soon", color: "#74AA9C",
    config: { period: 30, unit: "日", baseValue: 500000, baseUnit: "tokens", history: [] } },
  { id: "bathmat", name: "スマートバスマット", category: "体重", icon: "⚖️", type: "state", classification: "baseline", phase: "phase3", status: "coming_soon", color: "#F8F8F2",
    config: { period: 7, unit: "日", baseValue: 7, baseUnit: "回測定", history: [] } },
  { id: "spotify_podcast", name: "Spotify（ポッドキャスト）", category: "ポッドキャスト", icon: "🎙️", type: "activity", classification: "baseline", phase: "phase3", status: "coming_soon", color: "#1DB954",
    config: { period: 7, unit: "日", baseValue: 300, baseUnit: "分", history: [] } },
];

const phaseLabels = { mvp: "MVP", phase2: "PHASE 2", phase3: "PHASE 3" };
const phaseColors = { mvp: "#50FA7B", phase2: "#00F0FF", phase3: "rgba(255,255,255,0.25)" };

// --- Source Card ---
const SourceCard = ({ source, isExpanded, onToggle }) => {
  const isActive = source.status === "active";
  const isComingSoon = source.status === "coming_soon";
  const [showSelf, setShowSelf] = useState(true);
  const [showShared, setShowShared] = useState(source.classification !== "baseline" || source.id === "lastfm");
  const [autoMode, setAutoMode] = useState(false);

  return (
    <div style={{
      background: isExpanded ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.015)",
      border: `1px solid ${isActive ? source.color + "30" : "rgba(255,255,255,0.06)"}`,
      borderRadius: 12,
      overflow: "hidden",
      transition: "all 0.3s ease",
      opacity: isComingSoon ? 0.55 : 1,
    }}>
      {/* Header row */}
      <div
        onClick={onToggle}
        style={{
          display: "flex", alignItems: "center", gap: 14,
          padding: "16px 20px",
          cursor: isActive ? "pointer" : "default",
        }}
      >
        <span style={{ fontSize: 18, width: 28, textAlign: "center" }}>{source.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              fontSize: 14, fontWeight: 600,
              color: isActive ? source.color : "rgba(255,255,255,0.4)",
            }}>
              {source.name}
            </span>
            <span style={{
              fontSize: 9, letterSpacing: 2, fontWeight: 600,
              color: phaseColors[source.phase],
              background: phaseColors[source.phase] + "15",
              border: `1px solid ${phaseColors[source.phase]}30`,
              borderRadius: 4, padding: "2px 8px",
            }}>
              {phaseLabels[source.phase]}
            </span>
            {isComingSoon && (
              <span style={{
                fontSize: 9, letterSpacing: 1,
                color: "rgba(255,255,255,0.2)",
                fontStyle: "italic",
              }}>
                Coming Soon
              </span>
            )}
          </div>
          <div style={{
            fontSize: 11, color: "rgba(255,255,255,0.25)", marginTop: 3,
            display: "flex", gap: 12,
          }}>
            <span>{source.category}</span>
            <span>•</span>
            <span>{source.type === "activity" ? "活動量" : "状態"}</span>
            <span>•</span>
            <span>{source.classification === "baseline" ? "ベースライン" : source.classification === "event" ? "イベント" : "両方"}</span>
          </div>
        </div>

        {/* Toggles */}
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <ToggleSwitch label="本人" checked={showSelf} onChange={setShowSelf} color={source.color} disabled={isComingSoon} />
          <ToggleSwitch label="共有" checked={showShared} onChange={setShowShared} color={source.color} disabled={isComingSoon} />
        </div>

        {isActive && (
          <div style={{
            width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center",
            color: "rgba(255,255,255,0.3)", fontSize: 12,
            transform: isExpanded ? "rotate(180deg)" : "rotate(0)",
            transition: "transform 0.2s ease",
          }}>
            ▼
          </div>
        )}
      </div>

      {/* Expanded config panel */}
      {isExpanded && isActive && (
        <div style={{
          padding: "0 20px 20px",
          borderTop: "1px solid rgba(255,255,255,0.04)",
        }}>
          {/* Scoring config */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            <div>
              <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
                集計期間
              </label>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="number"
                  value={source.config.period}
                  readOnly
                  style={{
                    width: 60, padding: "8px 12px",
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 6,
                    color: "#fff", fontSize: 14,
                    fontFamily: "'Orbitron', sans-serif",
                    textAlign: "center",
                  }}
                />
                <span style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>{source.config.unit}</span>
              </div>
            </div>
            <div>
              <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
                基準値（= 100点）
              </label>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="number"
                  value={source.config.baseValue}
                  readOnly
                  style={{
                    width: 80, padding: "8px 12px",
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 6,
                    color: source.color, fontSize: 14,
                    fontFamily: "'Orbitron', sans-serif",
                    textAlign: "center",
                  }}
                />
                <span style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>{source.config.baseUnit}</span>
              </div>
            </div>
          </div>

          {/* Classification toggles */}
          <div style={{ display: "flex", gap: 24, marginTop: 16 }}>
            <div>
              <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
                指標分類
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                {["baseline", "event", "both"].map(c => (
                  <button key={c} style={{
                    padding: "5px 12px", fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    background: source.classification === c ? source.color + "20" : "transparent",
                    border: `1px solid ${source.classification === c ? source.color + "50" : "rgba(255,255,255,0.08)"}`,
                    borderRadius: 5,
                    color: source.classification === c ? source.color : "rgba(255,255,255,0.3)",
                    cursor: "pointer",
                  }}>
                    {c === "baseline" ? "ベースライン" : c === "event" ? "イベント" : "両方"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
                表示カテゴリ
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                {["activity", "state"].map(t => (
                  <button key={t} style={{
                    padding: "5px 12px", fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                    background: source.type === t ? source.color + "20" : "transparent",
                    border: `1px solid ${source.type === t ? source.color + "50" : "rgba(255,255,255,0.08)"}`,
                    borderRadius: 5,
                    color: source.type === t ? source.color : "rgba(255,255,255,0.3)",
                    cursor: "pointer",
                  }}>
                    {t === "activity" ? "活動量（面グラフ）" : "状態（折れ線）"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Auto mode */}
          <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 10 }}>
            <ToggleSwitch label="" checked={autoMode} onChange={setAutoMode} color={source.color} />
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
              自動モード：過去最高を基準値に設定
            </span>
          </div>

          {/* Base value history */}
          {source.config.history.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
                基準値の履歴
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {source.config.history.map((h, i) => (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 12,
                    padding: "8px 12px",
                    background: "rgba(255,255,255,0.02)",
                    borderRadius: 6,
                    border: "1px solid rgba(255,255,255,0.04)",
                  }}>
                    <span style={{
                      fontSize: 11, color: source.color,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {h.from}〜
                    </span>
                    <span style={{
                      fontSize: 13, color: "#fff", fontWeight: 600,
                      fontFamily: "'Orbitron', sans-serif",
                    }}>
                      {h.value}
                    </span>
                    <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>{h.unit}</span>
                    {h.memo && (
                      <span style={{
                        fontSize: 11, color: "rgba(255,255,255,0.2)",
                        fontStyle: "italic",
                        marginLeft: "auto",
                      }}>
                        {h.memo}
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <button style={{
                marginTop: 8, padding: "6px 14px",
                fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
                background: "transparent",
                border: "1px dashed rgba(255,255,255,0.1)",
                borderRadius: 6,
                color: "rgba(255,255,255,0.25)",
                cursor: "pointer",
              }}>
                + 新しい基準値を追加
              </button>
            </div>
          )}

          {/* Voluntariness coefficient */}
          <div style={{ marginTop: 16 }}>
            <label style={{ fontSize: 10, letterSpacing: 2, color: "rgba(255,255,255,0.3)", display: "block", marginBottom: 8 }}>
              自発性係数
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <input
                type="range" min="0" max="1.5" step="0.1" defaultValue="1.0"
                style={{ width: 160, accentColor: source.color }}
              />
              <span style={{
                fontSize: 14, fontFamily: "'Orbitron', sans-serif",
                color: source.color, fontWeight: 600,
              }}>
                1.0
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// --- Toggle Switch ---
const ToggleSwitch = ({ label, checked, onChange, color, disabled }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
    {label && <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", letterSpacing: 1 }}>{label}</span>}
    <div
      onClick={() => !disabled && onChange(!checked)}
      style={{
        width: 36, height: 20, borderRadius: 10,
        background: checked && !disabled ? color + "40" : "rgba(255,255,255,0.06)",
        border: `1px solid ${checked && !disabled ? color + "60" : "rgba(255,255,255,0.1)"}`,
        position: "relative",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.2s ease",
      }}
    >
      <div style={{
        width: 14, height: 14, borderRadius: 7,
        background: checked && !disabled ? color : "rgba(255,255,255,0.2)",
        position: "absolute",
        top: 2, left: checked ? 19 : 2,
        transition: "all 0.2s ease",
        boxShadow: checked && !disabled ? `0 0 6px ${color}60` : "none",
      }} />
    </div>
  </div>
);

// --- Main Settings Page ---
export default function SettingsPage() {
  const [expandedId, setExpandedId] = useState("lastfm");
  const [filterPhase, setFilterPhase] = useState("all");

  const filtered = filterPhase === "all"
    ? dataSources
    : dataSources.filter(s => s.phase === filterPhase);

  const activeCount = dataSources.filter(s => s.status === "active").length;
  const totalCount = dataSources.length;

  return (
    <div style={{
      minHeight: "100vh",
      background: "#07080F",
      color: "#E0E0E0",
      fontFamily: "'JetBrains Mono', monospace",
      position: "relative",
      overflow: "hidden",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Orbitron:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />

      {/* Background */}
      <div style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
        background: "radial-gradient(ellipse at 20% 50%, rgba(0,240,255,0.03) 0%, transparent 60%)",
        pointerEvents: "none",
      }} />
      <div style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
        backgroundImage: "linear-gradient(rgba(0,240,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,0.015) 1px, transparent 1px)",
        backgroundSize: "60px 60px",
        pointerEvents: "none",
      }} />

      <div style={{ position: "relative", zIndex: 1, maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
        {/* Header */}
        <header style={{ marginBottom: 40 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: "#00F0FF",
              boxShadow: "0 0 12px #00F0FF, 0 0 24px rgba(0,240,255,0.3)",
            }} />
            <span style={{ fontSize: 11, letterSpacing: 4, color: "rgba(0,240,255,0.6)" }}>
              SETTINGS
            </span>
          </div>
          <h1 style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 32, fontWeight: 800, letterSpacing: 3, margin: 0,
            background: "linear-gradient(135deg, #00F0FF 0%, #BD93F9 50%, #FF3366 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}>
            DATA SOURCES
          </h1>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", margin: "8px 0 0" }}>
            {activeCount} / {totalCount} ソースが有効
          </p>

          <style>{`
            @keyframes fadeInUp {
              from { opacity: 0; transform: translateY(12px); }
              to { opacity: 1; transform: translateY(0); }
            }
          `}</style>
        </header>

        {/* Phase filter */}
        <div style={{ display: "flex", gap: 6, marginBottom: 24 }}>
          {[
            { key: "all", label: "ALL" },
            { key: "mvp", label: "MVP" },
            { key: "phase2", label: "PHASE 2" },
            { key: "phase3", label: "PHASE 3" },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setFilterPhase(f.key)}
              style={{
                padding: "6px 16px", fontSize: 11,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: 1,
                background: filterPhase === f.key ? "rgba(0,240,255,0.1)" : "transparent",
                border: `1px solid ${filterPhase === f.key ? "rgba(0,240,255,0.3)" : "rgba(255,255,255,0.08)"}`,
                borderRadius: 6,
                color: filterPhase === f.key ? "#00F0FF" : "rgba(255,255,255,0.3)",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Source list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filtered.map((source, i) => (
            <div key={source.id} style={{ animation: `fadeInUp 0.3s ease-out ${i * 0.03}s both` }}>
              <SourceCard
                source={source}
                isExpanded={expandedId === source.id}
                onToggle={() => setExpandedId(expandedId === source.id ? null : source.id)}
              />
            </div>
          ))}
        </div>

        {/* Global settings */}
        <div style={{
          marginTop: 40,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 12,
          padding: "24px",
        }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>
            THRESHOLD SETTINGS
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
            {/* Health indicator thresholds */}
            <div>
              <div style={{ fontSize: 12, color: "#50FA7B", marginBottom: 12, fontWeight: 600 }}>
                健康指標（ベースライン）
              </div>
              {[
                { label: "NORMAL", value: "70", desc: "以上", color: "#50FA7B" },
                { label: "CAUTION", value: "40 〜 70", desc: "", color: "#FFB86C" },
                { label: "CRITICAL", value: "40", desc: "未満", color: "#FF1744" },
              ].map(t => (
                <div key={t.label} style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "6px 0",
                }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: 2,
                    background: t.color, boxShadow: `0 0 6px ${t.color}50`,
                  }} />
                  <span style={{
                    fontSize: 11, color: t.color, fontWeight: 600,
                    fontFamily: "'Orbitron', sans-serif",
                    width: 80,
                  }}>
                    {t.label}
                  </span>
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                    {t.value} {t.desc}
                  </span>
                </div>
              ))}
            </div>

            {/* Cultural indicator thresholds */}
            <div>
              <div style={{ fontSize: 12, color: "#00F0FF", marginBottom: 12, fontWeight: 600 }}>
                文化的指標（活動量）
              </div>
              {[
                { label: "RICH", value: "70%", desc: "以上", color: "#00F0FF" },
                { label: "MODERATE", value: "40 〜 70%", desc: "", color: "#FFB86C" },
                { label: "LOW", value: "40%", desc: "未満", color: "#FF3366" },
              ].map(t => (
                <div key={t.label} style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "6px 0",
                }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: 2,
                    background: t.color, boxShadow: `0 0 6px ${t.color}50`,
                  }} />
                  <span style={{
                    fontSize: 11, color: t.color, fontWeight: 600,
                    fontFamily: "'Orbitron', sans-serif",
                    width: 80,
                  }}>
                    {t.label}
                  </span>
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                    基準の{t.value} {t.desc}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Shared view settings */}
        <div style={{
          marginTop: 16,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 12,
          padding: "24px",
        }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>
            SHARED VIEW
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 13, color: "rgba(255,255,255,0.6)", marginBottom: 4 }}>
                共有ビューURL
              </div>
              <div style={{
                fontSize: 14, color: "#00F0FF",
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                health.ojimpo.com/shared/xxxxxxxxxx
              </div>
            </div>
            <ToggleSwitch label="公開" checked={true} onChange={() => {}} color="#50FA7B" />
          </div>
        </div>

        {/* Footer */}
        <footer style={{
          marginTop: 48, paddingTop: 24,
          borderTop: "1px solid rgba(255,255,255,0.04)",
          display: "flex", justifyContent: "space-between",
        }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.15)", letterSpacing: 1 }}>
            health.ojimpo.com — Settings
          </span>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.1)" }}>
            Design Mockup — 2026.03
          </span>
        </footer>
      </div>
    </div>
  );
}
