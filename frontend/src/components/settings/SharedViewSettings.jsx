import ToggleSwitch from '../common/ToggleSwitch'
import styles from './SharedViewSettings.module.css'

export default function SharedViewSettings({ settings, onToggle }) {
  if (!settings) return null

  return (
    <div className={styles.container}>
      <div className={styles.title}>SHARED VIEW</div>
      <div className={styles.row}>
        <span className={styles.url}>{settings.url}</span>
        <ToggleSwitch
          label="公開"
          checked={settings.enabled}
          onChange={onToggle}
        />
      </div>
    </div>
  )
}
