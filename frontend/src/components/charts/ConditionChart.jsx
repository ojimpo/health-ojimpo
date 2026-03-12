import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { stateCategories } from '../../constants/categories'
import { healthStatusConfig, culturalStatusConfig } from '../../constants/statusConfig'
import styles from './ConditionChart.module.css'

function StateTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const point = payload[0]?.payload
  const healthStatus = point?.health_status
  const culturalStatus = point?.cultural_status
  return (
    <div style={{
      background: 'rgba(10,10,20,0.95)',
      border: '1px solid rgba(189,147,249,0.3)',
      borderRadius: 8,
      padding: '12px 16px',
      backdropFilter: 'blur(12px)',
      fontFamily: 'var(--font-mono)',
    }}>
      <div style={{ color: '#BD93F9', fontSize: 11, marginBottom: 8, letterSpacing: 1 }}>
        WEEK {label}
      </div>
      {(healthStatus || culturalStatus) && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 8, fontSize: 10, letterSpacing: 0.5 }}>
          {healthStatus && (
            <span style={{ color: healthStatusConfig[healthStatus]?.color, fontWeight: 600 }}>
              ● {healthStatus}
            </span>
          )}
          {culturalStatus && (
            <span style={{ color: culturalStatusConfig[culturalStatus]?.color, fontWeight: 600 }}>
              ● {culturalStatus}
            </span>
          )}
        </div>
      )}
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 12, color: p.color, padding: '2px 0' }}>
          <span style={{ opacity: 0.8 }}>{stateCategories.find(c => c.key === p.dataKey)?.label}</span>
          <span style={{ fontWeight: 600 }}>{p.value ?? '—'}</span>
        </div>
      ))}
    </div>
  )
}

export default function ConditionChart({ data, height = 200, saturation }) {
  const hasData = data?.some(d => d.sleep != null || d.readiness != null || d.stress != null || d.weight != null)

  return (
    <>
      <div className={styles.sectionLabel}>CONDITION</div>
      <div className={styles.container} style={saturation != null ? { filter: `saturate(${saturation})` } : undefined}>
        {!hasData ? (
          <div className={styles.noData} style={{ height }}>
            NO DATA AVAILABLE — 状態系データソースは準備中です
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.25)', fontFamily: "'JetBrains Mono'" }}
                axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.2)', fontFamily: "'JetBrains Mono'" }}
                axisLine={false}
                tickLine={false}
                domain={[0, 'auto']}
              />
              <Tooltip content={<StateTooltip />} />
              {stateCategories.map(c => (
                <Line
                  key={c.key}
                  type="linear"
                  dataKey={c.key}
                  stroke={c.color}
                  strokeWidth={2}
                  strokeOpacity={0.8}
                  dot={{ r: 2, fill: c.color, strokeWidth: 0 }}
                  activeDot={{ r: 4, fill: c.color, stroke: '#07080F', strokeWidth: 2 }}
                  connectNulls={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </>
  )
}
