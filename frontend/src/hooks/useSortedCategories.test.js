import { describe, it, expect } from 'vitest'
import { sortCategoriesByStability } from './useSortedCategories'

const cats = [
  { key: 'a', label: 'A' },
  { key: 'b', label: 'B' },
  { key: 'c', label: 'C' },
]

describe('sortCategoriesByStability', () => {
  it('データなしは元の順序を返す', () => {
    expect(sortCategoriesByStability(null, cats)).toEqual(cats)
    expect(sortCategoriesByStability([], cats)).toEqual(cats)
  })

  it('変動係数の小さい（安定した）カテゴリが先頭になる', () => {
    const data = [
      { a: 100, b: 10, c: 50 },
      { a: 100, b: 200, c: 55 },
      { a: 100, b: 0, c: 45 },
    ]
    const sorted = sortCategoriesByStability(data, cats)
    // a: 完全に一定(cv=0) → 最安定、b: 激しく変動 → 最後
    expect(sorted.map((c) => c.key)).toEqual(['a', 'c', 'b'])
  })

  it('欠損キーは0として扱う', () => {
    const data = [{ a: 100 }, { a: 100 }]
    const sorted = sortCategoriesByStability(data, cats)
    expect(sorted[0].key).toBe('a')
  })

  it('元の配列を破壊しない', () => {
    const data = [{ a: 1, b: 100 }, { a: 1, b: 0 }]
    const original = [...cats]
    sortCategoriesByStability(data, cats)
    expect(cats).toEqual(original)
  })
})
