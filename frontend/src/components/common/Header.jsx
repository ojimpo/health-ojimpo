import styles from './Header.module.css'

export default function Header({ label = 'SYSTEM STATUS', title = 'HEALTH.OJIMPO.COM', subtitle, dotColor }) {
  return (
    <header className={styles.header}>
      <div className={styles.labelRow}>
        <div className={styles.dot} style={dotColor ? { background: dotColor, boxShadow: `0 0 8px ${dotColor}60` } : undefined} />
        <span className={styles.label}>{label}</span>
      </div>
      <h1 className={styles.title}>{title}</h1>
      {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
    </header>
  )
}
