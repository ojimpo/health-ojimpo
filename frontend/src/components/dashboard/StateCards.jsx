import styles from './StateCards.module.css'

export default function StateCards({ cards }) {
  return (
    <div className={styles.grid}>
      {cards.map((card, i) => (
        <div
          key={card.key}
          className={styles.card}
          style={{ animation: `fadeInUp 0.4s ease-out ${0.35 + i * 0.04}s both` }}
        >
          <div className={styles.labelRow}>
            <div
              className={styles.indicator}
              style={{
                background: card.color,
                boxShadow: `0 0 8px ${card.color}60`,
              }}
            />
            <span className={styles.label}>{card.label}</span>
          </div>
          <div className={styles.valueRow}>
            {card.current != null ? (
              <>
                <span className={styles.value} style={{ color: card.color }}>
                  {card.current}
                </span>
                {card.change != null && (
                  <span
                    className={styles.change}
                    style={{ color: card.change >= 0 ? '#50FA7B' : '#FF3366' }}
                  >
                    {card.change >= 0 ? '▲' : '▼'} {Math.abs(card.change)}
                  </span>
                )}
              </>
            ) : (
              <span className={styles.noData}>—</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
