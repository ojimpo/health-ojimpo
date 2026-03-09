import styles from './ToggleSwitch.module.css'

export default function ToggleSwitch({ label, checked, onChange, color = '#00F0FF', disabled = false }) {
  return (
    <div className={styles.container}>
      {label && <span className={styles.label}>{label}</span>}
      <div
        className={`${styles.track} ${checked ? styles.checked : ''} ${disabled ? styles.disabled : ''}`}
        style={checked ? { background: `${color}40` } : undefined}
        onClick={() => !disabled && onChange(!checked)}
      >
        <div
          className={`${styles.thumb} ${checked ? styles.checked : ''}`}
          style={checked ? { background: color, boxShadow: `0 0 6px ${color}60` } : undefined}
        />
      </div>
    </div>
  )
}
