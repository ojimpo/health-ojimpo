import styles from './StatusCard.module.css'

export default function StatusCard({ label, status, score, message, color, delay = 0 }) {
  return (
    <div
      className={styles.card}
      style={{
        background: `linear-gradient(135deg, ${color}08 0%, transparent 50%)`,
        borderColor: `${color}30`,
        animationDelay: `${delay}s`,
      }}
    >
      <div className={styles.labelRow}>
        <div
          className={styles.dot}
          style={{
            background: color,
            boxShadow: `0 0 10px ${color}60`,
          }}
        />
        <span className={styles.statusLabel} style={{ color }}>
          {status}
        </span>
      </div>
      <div className={styles.score} style={{ color, textShadow: `0 0 20px ${color}40` }}>
        {typeof score === 'number' ? score.toFixed(1) : score}
      </div>
      <div className={styles.message}>{message}</div>
    </div>
  )
}
