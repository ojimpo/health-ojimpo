import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { activityCategories } from '../../constants/categories'
import { healthStatusConfig, culturalStatusConfig } from '../../constants/statusConfig'
import styles from './ActivityChart.module.css'

function ActivityTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const total = payload.reduce((s, p) => s + (p.value || 0), 0)
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
      {[...payload].reverse().map((p, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 12, color: p.color, padding: '2px 0' }}>
          <span style={{ opacity: 0.8 }}>{activityCategories.find(c => c.key === p.dataKey)?.label}</span>
          <span style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: 8, paddingTop: 8, display: 'flex', justifyContent: 'space-between', color: '#fff', fontSize: 12, fontWeight: 700 }}>
        <span>TOTAL</span><span>{Math.round(total)}</span>
      </div>
    </div>
  )
}

function getTickInterval(dataLength) {
  if (dataLength <= 30) return 0        // 1M: show all
  if (dataLength <= 90) return 6        // 3M daily: show every 7th
  return 3                              // 1Y weekly: show every 4th
}

export default function ActivityChart({ data, hoveredCategory, height = 350, saturation }) {
  return (
    <div className={styles.container} style={saturation != null ? { filter: `saturate(${saturation})` } : undefined}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
          <defs>
            {activityCategories.map(c => (
              <linearGradient key={c.key} id={`grad-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c.color} stopOpacity={hoveredCategory == null || hoveredCategory === c.key ? 0.6 : 0.1} />
                <stop offset="100%" stopColor={c.color} stopOpacity={hoveredCategory == null || hoveredCategory === c.key ? 0.08 : 0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="date"
            interval={getTickInterval(data?.length || 0)}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.25)', fontFamily: "'JetBrains Mono'" }}
            axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.2)', fontFamily: "'JetBrains Mono'" }}
            axisLine={false}
            tickLine={false}
          />
          <ReferenceLine
            y={100}
            stroke="rgba(255,255,255,0.08)"
            strokeDasharray="6 4"
            label={{ value: 'BASE 100', position: 'right', fill: 'rgba(255,255,255,0.12)', fontSize: 9, fontFamily: "'JetBrains Mono'" }}
          />
          <Tooltip content={<ActivityTooltip />} />
          {activityCategories.map(c => (
            <Area
              key={c.key}
              type="linear"
              dataKey={c.key}
              stackId="1"
              stroke={c.color}
              strokeWidth={hoveredCategory == null || hoveredCategory === c.key ? 1.5 : 0.5}
              fill={`url(#grad-${c.key})`}
              strokeOpacity={hoveredCategory == null || hoveredCategory === c.key ? 0.8 : 0.15}
              dot={{ r: 2, fill: c.color, strokeWidth: 0, opacity: hoveredCategory == null || hoveredCategory === c.key ? 0.8 : 0.15 }}
              activeDot={{ r: 4, fill: c.color, stroke: '#07080F', strokeWidth: 2 }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
