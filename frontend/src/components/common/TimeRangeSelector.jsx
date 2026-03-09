import styles from './TimeRangeSelector.module.css'

const ranges = [
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: '1y', label: '1Y' },
]

export default function TimeRangeSelector({ value, onChange }) {
  return (
    <div className={styles.container}>
      {ranges.map(r => (
        <button
          key={r.value}
          className={`${styles.button} ${value === r.value ? styles.active : ''}`}
          onClick={() => onChange(r.value)}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}
