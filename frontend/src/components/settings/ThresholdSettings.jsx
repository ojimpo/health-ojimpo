import styles from './ThresholdSettings.module.css'

export default function ThresholdSettings({ thresholds }) {
  if (!thresholds) return null

  const normal = thresholds.score_normal_threshold
  const caution = thresholds.score_caution_threshold

  return (
    <div className={styles.container}>
      <div className={styles.title}>THRESHOLD SETTINGS</div>
      <div className={styles.note}>
        健康スコアと文化スコアは同じ閾値で判定されます（SCOREモードグラフの背景帯と一致）
      </div>
      <div className={styles.grid}>
        <div className={styles.section}>
          <div className={styles.sectionTitle} style={{ color: '#50FA7B' }}>
            健康指標（ベースライン）
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#50FA7B', boxShadow: '0 0 6px #50FA7B60' }} />
            <span className={styles.label} style={{ color: '#50FA7B' }}>NORMAL</span>
            <span className={styles.value}>&gt;= {normal}</span>
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#FFB86C', boxShadow: '0 0 6px #FFB86C60' }} />
            <span className={styles.label} style={{ color: '#FFB86C' }}>CAUTION</span>
            <span className={styles.value}>{caution} - {normal}</span>
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#FF1744', boxShadow: '0 0 6px #FF174460' }} />
            <span className={styles.label} style={{ color: '#FF1744' }}>CRITICAL</span>
            <span className={styles.value}>&lt; {caution}</span>
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle} style={{ color: '#00F0FF' }}>
            文化的指標（活動量）
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#00F0FF', boxShadow: '0 0 6px #00F0FF60' }} />
            <span className={styles.label} style={{ color: '#00F0FF' }}>RICH</span>
            <span className={styles.value}>&gt;= {normal}%</span>
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#FFB86C', boxShadow: '0 0 6px #FFB86C60' }} />
            <span className={styles.label} style={{ color: '#FFB86C' }}>MODERATE</span>
            <span className={styles.value}>{caution} - {normal}%</span>
          </div>
          <div className={styles.row}>
            <div className={styles.indicator} style={{ background: '#FF3366', boxShadow: '0 0 6px #FF336660' }} />
            <span className={styles.label} style={{ color: '#FF3366' }}>LOW</span>
            <span className={styles.value}>&lt; {caution}%</span>
          </div>
        </div>
      </div>
    </div>
  )
}
