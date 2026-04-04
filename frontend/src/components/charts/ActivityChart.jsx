import { useState } from 'react'
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { activityCategories, stateCategories } from '../../constants/categories'
import { healthStatusConfig, culturalStatusConfig } from '../../constants/statusConfig'
import styles from './ActivityChart.module.css'

const MODES = ['ACTIVITY', 'SCORE', 'CONDITION']

const OVERLAY_KEYS = new Set([
  'health_score', 'cultural_score',
  'health_normal', 'health_caution', 'health_critical',
  'cultural_rich', 'cultural_moderate', 'cultural_low',
  ...stateCategories.map(c => c.key),
])

function ChartTooltip({ active, payload, label, mode }) {
  if (!active || !payload || !payload.length) return null
  const areaPayload = payload.filter(p => !OVERLAY_KEYS.has(p.dataKey))
  const total = areaPayload.reduce((s, p) => s + (p.value || 0), 0)
  const point = payload[0]?.payload
  const healthStatus = point?.health_status
  const culturalStatus = point?.cultural_status
  const healthScore = point?.health_score
  const culturalScore = point?.cultural_score
  return (
    <div style={{
      background: 'rgba(10,10,20,0.95)',
      border: '1px solid rgba(0,240,255,0.3)',
      borderRadius: 8,
      padding: '12px 16px',
      backdropFilter: 'blur(12px)',
      fontFamily: 'var(--font-mono)',
    }}>
      <div style={{ color: '#00F0FF', fontSize: 11, marginBottom: 8, letterSpacing: 1 }}>
        {label}
      </div>
      {(healthStatus || culturalStatus) && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 10, letterSpacing: 0.5 }}>
          {healthStatus && (
            <span style={{ color: healthStatusConfig[healthStatus]?.color, fontWeight: 600 }}>
              ● {healthStatus}{healthScore != null ? ` ${healthScore}` : ''}
            </span>
          )}
          {culturalStatus && (
            <span style={{ color: culturalStatusConfig[culturalStatus]?.color, fontWeight: 600 }}>
              ● {culturalStatus}{culturalScore != null ? ` ${culturalScore}` : ''}
            </span>
          )}
        </div>
      )}
      {mode === 'CONDITION' && stateCategories.map((c, i) => {
        const v = point?.[c.key]
        if (v == null) return null
        const unit = c.key === 'outing' ? '%' : ''
        return (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 12, color: c.color, padding: '2px 0' }}>
            <span style={{ opacity: 0.8 }}>{c.label}</span>
            <span style={{ fontWeight: 600 }}>{v}{unit}</span>
          </div>
        )
      })}
      {mode !== 'CONDITION' && [...areaPayload].reverse().map((p, i) => {
        const cat = activityCategories.find(c => c.key === p.dataKey)
        return (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 12, color: cat?.color || p.color, padding: '2px 0' }}>
            <span style={{ opacity: 0.8 }}>{cat?.label}</span>
            <span style={{ fontWeight: 600 }}>{p.value}</span>
          </div>
        )
      })}
      {mode !== 'CONDITION' && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: 8, paddingTop: 8, display: 'flex', justifyContent: 'space-between', color: '#fff', fontSize: 12, fontWeight: 700 }}>
          <span>TOTAL</span><span>{Math.round(total)}</span>
        </div>
      )}
    </div>
  )
}

function getTickInterval(dataLength, mobile) {
  if (mobile) {
    if (dataLength <= 30) return 6
    if (dataLength <= 90) return 20
    return 8
  }
  if (dataLength <= 30) return 0
  if (dataLength <= 90) return 6
  return 3
}

function prepareScoreData(data) {
  if (!data) return data
  return data.map((point, i) => {
    const prev = i > 0 ? data[i - 1] : null
    const out = { ...point }

    const hs = point.health_status
    const hv = point.health_score
    out.health_normal = hs === 'NORMAL' ? hv : null
    out.health_caution = hs === 'CAUTION' ? hv : null
    out.health_critical = hs === 'CRITICAL' ? hv : null
    if (prev && prev.health_status !== hs && prev.health_score != null) {
      if (prev.health_status === 'NORMAL') out.health_normal = hv
      if (prev.health_status === 'CAUTION') out.health_caution = hv
      if (prev.health_status === 'CRITICAL') out.health_critical = hv
    }

    const cs = point.cultural_status
    const cv = point.cultural_score
    out.cultural_rich = cs === 'RICH' ? cv : null
    out.cultural_moderate = cs === 'MODERATE' ? cv : null
    out.cultural_low = cs === 'LOW' ? cv : null
    if (prev && prev.cultural_status !== cs && prev.cultural_score != null) {
      if (prev.cultural_status === 'RICH') out.cultural_rich = cv
      if (prev.cultural_status === 'MODERATE') out.cultural_moderate = cv
      if (prev.cultural_status === 'LOW') out.cultural_low = cv
    }

    return out
  })
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useState(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  })
  return isMobile
}

function getYMax(data) {
  if (!data?.length) return undefined
  const totals = data.map(d =>
    activityCategories.reduce((sum, c) => sum + (d[c.key] || 0), 0)
  )
  const sorted = [...totals].sort((a, b) => a - b)
  // Use 90th percentile to clip extreme spikes
  // Use median to aggressively clip spikes
  const median = sorted[Math.floor(sorted.length * 0.5)]
  return Math.ceil(median * 1.2 / 50) * 50
}

export default function ActivityChart({ data, hoveredCategory, height = 350, saturation }) {
  const [mode, setMode] = useState('ACTIVITY')
  const isMobile = useIsMobile()
  const isOverlay = mode !== 'ACTIVITY'
  const chartData = mode === 'SCORE' ? prepareScoreData(data) : data
  const chartHeight = isMobile ? 300 : 450
  const yMax = getYMax(data)

  return (
    <div className={styles.container} style={saturation != null ? { filter: `saturate(${saturation})` } : undefined}>
      <div style={{
        position: 'absolute',
        top: 8,
        right: 8,
        zIndex: 10,
        display: 'flex',
        gap: 0,
        borderRadius: 4,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.08)',
      }}>
        {MODES.map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              background: mode === m ? 'rgba(255,255,255,0.1)' : 'transparent',
              border: 'none',
              borderRight: m !== MODES[MODES.length - 1] ? '1px solid rgba(255,255,255,0.08)' : 'none',
              padding: '3px 8px',
              fontSize: 9,
              letterSpacing: 1,
              color: mode === m ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.25)',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              transition: 'all 0.2s ease',
            }}
          >
            {m}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <ComposedChart data={chartData} margin={{ top: 10, right: isOverlay ? 40 : 10, left: 10, bottom: 0 }}>
          <defs>
            {activityCategories.map(c => (
              <linearGradient key={c.key} id={`grad-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isOverlay ? '#888' : c.color} stopOpacity={hoveredCategory == null || hoveredCategory === c.key ? 0.6 : 0.1} />
                <stop offset="100%" stopColor={isOverlay ? '#888' : c.color} stopOpacity={hoveredCategory == null || hoveredCategory === c.key ? 0.08 : 0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="date"
            interval={getTickInterval(data?.length || 0, isMobile)}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.25)', fontFamily: "'JetBrains Mono'" }}
            axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
            tickLine={false}
          />
          <YAxis
            yAxisId="left"
            domain={[0, yMax || 'auto']}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.2)', fontFamily: "'JetBrains Mono'" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={mode === 'CONDITION' ? [0, 100] : [0, 140]}
            tick={isOverlay ? { fontSize: 10, fill: 'rgba(255,255,255,0.15)', fontFamily: "'JetBrains Mono'" } : false}
            axisLine={false}
            tickLine={false}
            ticks={mode === 'CONDITION' ? [20, 40, 60, 80] : [40, 70, 100]}
            width={isOverlay ? 30 : 0}
          />
          <ReferenceLine
            yAxisId="left"
            y={100}
            stroke="rgba(255,255,255,0.08)"
            strokeDasharray="6 4"
            label={{ value: 'BASE 100', position: 'insideTopLeft', fill: 'rgba(255,255,255,0.12)', fontSize: 9, fontFamily: "'JetBrains Mono'" }}
          />
          <Tooltip content={<ChartTooltip mode={mode} />} />
          {/* Stacked area — always shown, monochrome in overlay modes */}
          {activityCategories.map(c => (
            <Area
              key={c.key}
              yAxisId="left"
              type="linear"
              dataKey={c.key}
              stackId="1"
              stroke={isOverlay ? '#555' : c.color}
              strokeWidth={hoveredCategory == null || hoveredCategory === c.key ? 1.5 : 0.5}
              fill={`url(#grad-${c.key})`}
              strokeOpacity={isOverlay ? 0.3 : (hoveredCategory == null || hoveredCategory === c.key ? 0.8 : 0.15)}
              dot={isMobile ? false : { r: 2, fill: isOverlay ? '#555' : c.color, strokeWidth: 0, opacity: isOverlay ? 0.2 : (hoveredCategory == null || hoveredCategory === c.key ? 0.8 : 0.15) }}
              activeDot={isMobile ? false : { r: 4, fill: isOverlay ? '#555' : c.color, stroke: '#07080F', strokeWidth: 2 }}
            />
          ))}
          {/* SCORE mode: health score lines */}
          {[
            { key: 'health_normal', color: '#50FA7B' },
            { key: 'health_caution', color: '#FFB86C' },
            { key: 'health_critical', color: '#FF1744' },
          ].map(s => (
            <Line
              key={s.key}
              yAxisId="right"
              type="linear"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={2}
              hide={mode !== 'SCORE'}
              dot={mode === 'SCORE' ? { r: 2, fill: s.color, strokeWidth: 0 } : false}
              activeDot={mode === 'SCORE' ? { r: 4, fill: s.color, stroke: '#07080F', strokeWidth: 2 } : false}
              connectNulls={false}
            />
          ))}
          {/* SCORE mode: cultural score lines */}
          {[
            { key: 'cultural_rich', color: '#00F0FF' },
            { key: 'cultural_moderate', color: '#FFB86C' },
            { key: 'cultural_low', color: '#FF3366' },
          ].map(s => (
            <Line
              key={s.key}
              yAxisId="right"
              type="linear"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray="6 3"
              hide={mode !== 'SCORE'}
              dot={mode === 'SCORE' ? { r: 2, fill: s.color, strokeWidth: 0 } : false}
              activeDot={mode === 'SCORE' ? { r: 4, fill: s.color, stroke: '#07080F', strokeWidth: 2 } : false}
              connectNulls={false}
            />
          ))}
          {/* CONDITION mode: state lines */}
          {stateCategories.map(c => (
            <Line
              key={c.key}
              yAxisId="right"
              type="linear"
              dataKey={c.key}
              stroke={c.color}
              strokeWidth={2}
              hide={mode !== 'CONDITION'}
              dot={mode === 'CONDITION' ? { r: 2, fill: c.color, strokeWidth: 0 } : false}
              activeDot={mode === 'CONDITION' ? { r: 4, fill: c.color, stroke: '#07080F', strokeWidth: 2 } : false}
              connectNulls={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
