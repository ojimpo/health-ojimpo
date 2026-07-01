import Header from './Header'

// ローディング中／エラー時のページ全体表示（Header + 中央メッセージ）
export default function PageStatus({ label, subtitle, error }) {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
      <Header label={label} subtitle={subtitle} />
      <div style={{
        textAlign: 'center',
        padding: '80px 0',
        color: error ? '#FF3366' : 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        letterSpacing: 2,
      }}>
        {error || 'LOADING...'}
      </div>
    </div>
  )
}
