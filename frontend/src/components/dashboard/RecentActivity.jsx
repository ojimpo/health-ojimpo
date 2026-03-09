import styles from './RecentActivity.module.css'

export default function RecentActivity({ activities, dimmed = false }) {
  return (
    <div className={styles.container} style={dimmed ? { opacity: 0.4 } : undefined}>
      <div className={styles.label}>RECENT ACTIVITY</div>
      {activities.map((item, i) => (
        <div key={i} className={styles.item}>
          <span className={styles.icon}>{item.icon}</span>
          <span className={styles.time}>{item.time}</span>
          <span className={styles.text} style={{ color: `${item.color}CC` }}>{item.text}</span>
          {item.detail && <span className={styles.detail}>— {item.detail}</span>}
        </div>
      ))}
      {activities.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '16px 0' }}>
          データがありません
        </div>
      )}
    </div>
  )
}
