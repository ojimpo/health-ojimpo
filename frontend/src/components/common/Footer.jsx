import { useSiteInfo } from '../../hooks/useSiteInfo'
import styles from './Footer.module.css'

export default function Footer() {
  const { domain } = useSiteInfo()
  const displayDomain = domain?.toUpperCase() || 'CULTURAL HEALTH DASHBOARD'

  return (
    <footer className={styles.footer}>
      <div>{displayDomain} — CULTURAL HEALTH DASHBOARD</div>
      <div className={styles.quote}>
        "As long as you live, keep learning how to live." — Seneca
      </div>
    </footer>
  )
}
