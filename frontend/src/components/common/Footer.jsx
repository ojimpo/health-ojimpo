import { useSiteInfo } from '../../hooks/useSiteInfo'
import styles from './Footer.module.css'

export default function Footer() {
  const { domain } = useSiteInfo()
  const displayDomain = domain?.toUpperCase() || 'CULTURAL HEALTH DASHBOARD'

  return (
    <footer className={styles.footer}>
      {displayDomain} — CULTURAL HEALTH DASHBOARD
    </footer>
  )
}
