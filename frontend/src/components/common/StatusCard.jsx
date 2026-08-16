import styles from './StatusCard.module.css'

// 計測が壊れているソースがあって軸から外したカテゴリは、必ずカード上に出す。
// 黙って外すとスコアだけが上がり「全部正常」に見えてしまい、ソース悪化の
// 見逃しそのものになる。measurable=false のときはスコアを主役から降ろす。
export default function StatusCard({
  status,
  score,
  message,
  color,
  delay = 0,
  unmeasured = [],
  measurable = true,
}) {
  const hasUnmeasured = unmeasured.length > 0

  return (
    <div
      className={styles.card}
      style={{
        background: `linear-gradient(135deg, ${color}08 0%, transparent 50%)`,
        borderColor: `${color}30`,
        animationDelay: `${delay}s`,
      }}
    >
      <div className={styles.labelRow}>
        <div
          className={styles.dot}
          style={{
            background: color,
            boxShadow: `0 0 10px ${color}60`,
          }}
        />
        <span className={styles.statusLabel} style={{ color }}>
          {measurable ? status : 'UNRELIABLE'}
        </span>
      </div>
      <div
        className={styles.score}
        style={{
          color,
          textShadow: `0 0 20px ${color}40`,
          opacity: measurable ? 1 : 0.4,
        }}
      >
        {typeof score === 'number' ? score.toFixed(1) : score}
      </div>
      <div className={styles.message}>{message}</div>
      {hasUnmeasured && (
        <div className={styles.unmeasured} title="計測が壊れているため、この軸の計算から外しています">
          <span className={styles.unmeasuredMark}>⚪</span>
          計測不能: {unmeasured.join('・')}
        </div>
      )}
      {!measurable && (
        <div className={styles.unreliable}>
          計測できている指標が少なすぎます。この数値は当てになりません
        </div>
      )}
    </div>
  )
}
