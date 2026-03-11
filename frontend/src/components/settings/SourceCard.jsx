import { useState, useEffect } from 'react'
import ToggleSwitch from '../common/ToggleSwitch'
import styles from './SourceCard.module.css'

export default function SourceCard({ source, onUpdate, delay = 0 }) {
  const [expanded, setExpanded] = useState(false)
  const isActive = source.status === 'active'

  const [baseValue, setBaseValue] = useState(source.base_value)
  const [aggPeriod, setAggPeriod] = useState(source.aggregation_period)
  const [spontCoeff, setSpontCoeff] = useState(source.spontaneity_coefficient)

  useEffect(() => {
    setBaseValue(source.base_value)
    setAggPeriod(source.aggregation_period)
    setSpontCoeff(source.spontaneity_coefficient)
  }, [source.base_value, source.aggregation_period, source.spontaneity_coefficient])

  const handleToggle = (field, value) => {
    onUpdate?.(source.id, { [field]: value })
  }

  const handleBlur = (field, value, original) => {
    const num = parseFloat(value)
    if (!isNaN(num) && num !== original) {
      onUpdate?.(source.id, { [field]: num })
    }
  }

  return (
    <div
      className={`${styles.card} ${isActive ? styles.active : styles.comingSoon}`}
      style={{
        borderColor: isActive ? `${source.color}30` : undefined,
        animation: `fadeInUp 0.4s ease-out ${delay}s both`,
      }}
    >
      <div className={styles.header} onClick={() => isActive && setExpanded(!expanded)}>
        <div className={styles.headerLeft}>
          <span className={styles.icon}>{source.icon}</span>
          <span className={styles.name}>{source.name}</span>
          {!isActive && <span className={styles.comingSoonLabel}>Coming Soon</span>}
        </div>
        <div className={styles.headerRight}>
          {isActive ? (
            <>
              <div className={styles.toggleGroup}>
                <ToggleSwitch
                  label="本人"
                  checked={source.show_personal}
                  onChange={v => handleToggle('show_personal', v)}
                  color={source.color}
                />
                <ToggleSwitch
                  label="共有"
                  checked={source.show_shared}
                  onChange={v => handleToggle('show_shared', v)}
                  color={source.color}
                />
              </div>
              <span className={`${styles.expandIcon} ${expanded ? styles.expanded : ''}`}>▼</span>
            </>
          ) : (
            <span className={styles.statusLabel}>未接続</span>
          )}
        </div>
      </div>

      {expanded && isActive && (
        <div className={styles.panel}>
          {/* Period & Base Value */}
          <div className={styles.section}>
            <div className={styles.sectionLabel}>集計期間 & 基準値</div>
            <div className={styles.row}>
              <div className={styles.inputGroup}>
                <span className={styles.inputLabel}>期間 (日)</span>
                <input
                  className={styles.input}
                  type="number"
                  value={aggPeriod}
                  onChange={e => setAggPeriod(e.target.value)}
                  onBlur={() => handleBlur('aggregation_period', aggPeriod, source.aggregation_period)}
                  style={{ width: 60 }}
                />
              </div>
              <div className={styles.inputGroup}>
                <span className={styles.inputLabel}>基準値</span>
                <input
                  className={styles.input}
                  type="number"
                  value={baseValue}
                  onChange={e => setBaseValue(e.target.value)}
                  onBlur={() => handleBlur('base_value', baseValue, source.base_value)}
                  style={{ color: source.color }}
                />
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 16 }}>
                {source.base_unit}
              </span>
            </div>
          </div>

          {/* Classification & Type */}
          <div className={styles.section}>
            <div className={styles.sectionLabel}>分類</div>
            <div className={styles.row} style={{ gap: 24 }}>
              <div>
                <div className={styles.inputLabel} style={{ marginBottom: 6 }}>指標分類</div>
                <div className={styles.classButtons}>
                  {['baseline', 'event', 'both'].map(c => (
                    <button
                      key={c}
                      className={`${styles.classBtn} ${source.classification === c ? styles.selected : ''}`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className={styles.inputLabel} style={{ marginBottom: 6 }}>表示タイプ</div>
                <div className={styles.classButtons}>
                  {['activity', 'state'].map(t => (
                    <button
                      key={t}
                      className={`${styles.classBtn} ${source.display_type === t ? styles.selected : ''}`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Spontaneity coefficient */}
          <div className={styles.section}>
            <div className={styles.sectionLabel}>自発性係数</div>
            <div className={styles.slider}>
              <input
                className={styles.sliderInput}
                type="range"
                min="0"
                max="1.5"
                step="0.1"
                value={spontCoeff}
                onChange={e => {
                  setSpontCoeff(parseFloat(e.target.value))
                  onUpdate?.(source.id, { spontaneity_coefficient: parseFloat(e.target.value) })
                }}
              />
              <span className={styles.sliderValue} style={{ color: source.color }}>
                {spontCoeff}
              </span>
            </div>
          </div>

          {/* Baseline history */}
          {source.baseline_history && source.baseline_history.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionLabel}>基準値履歴</div>
              {source.baseline_history.map((h, i) => (
                <div key={i} className={styles.historyItem}>
                  <span className={styles.historyDate}>{h.effective_from}〜</span>
                  <span className={styles.historyValue} style={{ color: source.color }}>
                    {h.base_value} {h.base_unit}
                  </span>
                  {h.memo && <span className={styles.historyMemo}>{h.memo}</span>}
                </div>
              ))}
            </div>
          )}

          <button className={styles.addBtn}>+ 新しい基準値を追加</button>
        </div>
      )}
    </div>
  )
}
