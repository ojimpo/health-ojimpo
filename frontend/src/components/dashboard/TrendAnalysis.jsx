import styles from './TrendAnalysis.module.css'

const typeColors = {
  positive: '#50FA7B',
  warning: '#FF3366',
  neutral: 'rgba(255,255,255,0.3)',
}

export default function TrendAnalysis({ comments }) {
  return (
    <div className={styles.container}>
      <div className={styles.label}>TREND ANALYSIS</div>
      <div className={styles.list}>
        {comments.map((c, i) => (
          <div
            key={i}
            className={styles.item}
            style={{ animation: `slideIn 0.4s ease-out ${0.2 + i * 0.08}s both` }}
          >
            <div
              className={styles.dot}
              style={{
                background: typeColors[c.type] || typeColors.neutral,
                boxShadow: `0 0 8px ${typeColors[c.type] || typeColors.neutral}`,
              }}
            />
            <span className={styles.text}>{c.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
