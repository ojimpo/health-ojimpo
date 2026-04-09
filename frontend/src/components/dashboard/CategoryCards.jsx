import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useSortedCategories } from '../../hooks/useSortedCategories'
import styles from './CategoryCards.module.css'

export default function CategoryCards({ cards, onHover, small = false, chartData }) {
  const sortedCategories = useSortedCategories(chartData)

  const sortedCards = useMemo(() => {
    const orderMap = new Map(sortedCategories.map((c, i) => [c.key, i]))
    return [...cards].sort((a, b) => (orderMap.get(a.key) ?? 999) - (orderMap.get(b.key) ?? 999))
  }, [cards, sortedCategories])

  return (
    <div className={styles.grid} style={small ? { gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' } : undefined}>
      {sortedCards.map((card, i) => (
        <motion.div
          key={card.key}
          layout
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          className={styles.card}
          onMouseEnter={() => onHover?.(card.key)}
          onMouseLeave={() => onHover?.(null)}
          style={{ animation: `fadeInUp 0.4s ease-out ${0.3 + i * 0.04}s both` }}
        >
          <div className={styles.labelRow}>
            <div
              className={styles.icon}
              style={{
                background: card.color,
                boxShadow: `0 0 8px ${card.color}60`,
                width: small ? 8 : 10,
                height: small ? 8 : 10,
              }}
            />
            <span className={styles.categoryLabel}>{card.label}</span>
          </div>
          <div className={styles.valueRow}>
            <span
              className={styles.value}
              style={{
                color: card.color,
                fontSize: small ? 20 : 22,
              }}
            >
              {Math.round(card.current)}
            </span>
            <span
              className={styles.change}
              style={{ color: card.change >= 0 ? '#50FA7B' : '#FF3366' }}
            >
              {card.change >= 0 ? '+' : ''}{Math.round(card.change)}
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  )
}
