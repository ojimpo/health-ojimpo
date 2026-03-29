import { useState, useEffect } from 'react'
import { apiPost } from '../../hooks/useApi'
import styles from './NotificationSubscribe.module.css'

// QRコード風のダミーパターン（LINE info未取得時のフォールバック）
function QrPlaceholder() {
  const pattern = [
    1,1,1,0,1,0,1,1,
    1,0,1,1,0,1,0,1,
    1,1,1,0,1,1,1,1,
    0,0,0,1,0,0,0,0,
    1,0,1,1,1,0,1,0,
    0,1,0,0,1,1,0,1,
    1,1,1,0,0,1,1,1,
    1,0,1,1,1,0,1,1,
  ]
  return (
    <div className={styles.qrPlaceholder}>
      <div className={styles.qrGrid}>
        {pattern.map((fill, i) => (
          <div key={i} className={styles.qrCell} style={{ opacity: fill ? 1 : 0 }} />
        ))}
      </div>
    </div>
  )
}

export default function NotificationSubscribe() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [lineInfo, setLineInfo] = useState(null)

  useEffect(() => {
    fetch('/api/notification/line/info')
      .then(r => r.json())
      .then(setLineInfo)
      .catch(() => {})
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email || submitting) return
    setSubmitting(true)
    setResult(null)
    try {
      const data = await apiPost('/api/notification/subscribe/email', { email })
      setResult({ success: true, message: data.message })
      setEmail('')
    } catch {
      setResult({ success: false, message: '登録に失敗しました。しばらく後にお試しください' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.section}>
      <div className={styles.header}>NOTIFICATIONS</div>
      <div className={styles.subtitle}>コンディション低下時に通知を受け取れます</div>

      <div className={styles.cards}>
        {/* LINE */}
        <div className={styles.card}>
          <div className={`${styles.cardLabel} ${styles.lineLabelColor}`}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.365 9.863c.349 0 .63.285.63.631 0 .345-.281.63-.63.63H17.61v1.125h1.755c.349 0 .63.283.63.63 0 .344-.281.629-.63.629h-2.386c-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63h2.386c.346 0 .627.285.627.63 0 .349-.281.63-.63.63H17.61v1.125h1.755zm-3.855 3.016c0 .27-.174.51-.432.596-.064.021-.133.031-.199.031-.211 0-.391-.09-.51-.25l-2.443-3.317v2.94c0 .344-.279.629-.631.629-.346 0-.626-.285-.626-.629V8.108c0-.271.173-.508.43-.595.06-.023.136-.033.194-.033.195 0 .375.104.495.254l2.462 3.33V8.108c0-.345.282-.63.63-.63.345 0 .63.285.63.63v4.771zm-5.741 0c0 .344-.282.629-.631.629-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63.346 0 .628.285.628.63v4.771zm-2.466.629H4.917c-.345 0-.63-.285-.63-.629V8.108c0-.345.285-.63.63-.63.348 0 .63.285.63.63v4.141h1.756c.348 0 .629.283.629.63 0 .344-.282.629-.629.629M24 10.314C24 4.943 18.615.572 12 .572S0 4.943 0 10.314c0 4.811 4.27 8.842 10.035 9.608.391.082.923.258 1.058.59.12.301.079.766.038 1.08l-.164 1.02c-.045.301-.24 1.186 1.049.645 1.291-.539 6.916-4.078 9.436-6.975C23.176 14.393 24 12.458 24 10.314" />
            </svg>
            LINE
          </div>
          <div className={styles.lineContent}>
            {lineInfo?.available ? (
              <a href={lineInfo.add_friend_url} target="_blank" rel="noopener noreferrer">
                <img
                  src={`https://qr-official.line.me/gs/M_${lineInfo.bot_basic_id.replace('@', '')}_GW.png?oat_content=qr`}
                  alt="LINE QR"
                  width="96"
                  height="96"
                  style={{ borderRadius: 6 }}
                />
              </a>
            ) : (
              <QrPlaceholder />
            )}
            <div>
              <div className={styles.lineInfo}>
                友だち追加で通知を受け取れます
              </div>
              <div className={styles.lineId}>
                {lineInfo?.available ? lineInfo.bot_basic_id : 'Coming soon'}
              </div>
            </div>
          </div>
        </div>

        {/* Email */}
        <div className={styles.card}>
          <div className={`${styles.cardLabel} ${styles.emailLabelColor}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M22 7l-10 7L2 7" />
            </svg>
            EMAIL
          </div>
          {result?.success ? (
            <div className={styles.successMsg}>{result.message}</div>
          ) : (
            <>
              <form className={styles.emailForm} onSubmit={handleSubmit}>
                <input
                  type="email"
                  className={styles.emailInput}
                  placeholder="email@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={submitting}
                />
                <button type="submit" className={styles.submitBtn} disabled={submitting}>
                  {submitting ? '...' : 'SUBSCRIBE'}
                </button>
              </form>
              {result?.success === false ? (
                <div className={styles.errorMsg}>{result.message}</div>
              ) : (
                <div className={styles.emailNote}>確認メールをお送りします</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
