import styles from './EvaWarningOverlay.module.css'

export default function EvaWarningOverlay() {
  return (
    <div className={styles.overlay}>
      <div className={styles.stripes} />
      <div className={styles.vignette} />
      <div className={styles.topBar} />
      <div className={styles.bottomBar} />
      <span className={`${styles.corner} ${styles.topLeft}`}>WARNING</span>
      <span className={`${styles.corner} ${styles.topRight}`}>WARNING</span>
      <span className={`${styles.corner} ${styles.bottomLeft}`}>WARNING</span>
      <span className={`${styles.corner} ${styles.bottomRight}`}>WARNING</span>
    </div>
  )
}
