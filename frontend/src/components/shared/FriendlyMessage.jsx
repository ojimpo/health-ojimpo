import styles from './FriendlyMessage.module.css'

export default function FriendlyMessage({ message, color }) {
  return (
    <div
      className={styles.container}
      style={{
        background: `linear-gradient(135deg, ${color}06 0%, transparent 100%)`,
        borderColor: `${color}15`,
      }}
    >
      <p className={styles.text} style={{ color: `${color}CC` }}>
        {message}
      </p>
    </div>
  )
}
