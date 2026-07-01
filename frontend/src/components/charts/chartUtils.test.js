import { describe, it, expect } from 'vitest'
import { getTickInterval, getYMax } from './chartUtils'
import { activityCategories } from '../../constants/categories'

describe('getTickInterval', () => {
  it('デスクトップ: 1M(30点)は全ラベル表示', () => {
    expect(getTickInterval(30, false)).toBe(0)
  })
  it('デスクトップ: 3M(90点)は6個おき', () => {
    expect(getTickInterval(90, false)).toBe(6)
  })
  it('デスクトップ: 1Y(52点週次)は3個おき', () => {
    expect(getTickInterval(120, false)).toBe(3)
  })
  it('モバイルはより広い間引き', () => {
    expect(getTickInterval(30, true)).toBe(6)
    expect(getTickInterval(90, true)).toBe(20)
  })
})

describe('getYMax', () => {
  const point = (v) =>
    Object.fromEntries(activityCategories.map((c) => [c.key, v / activityCategories.length]))

  it('データなしは undefined', () => {
    expect(getYMax(null)).toBeUndefined()
    expect(getYMax([])).toBeUndefined()
  })

  it('積み上げ合計の中央値×1.2を50単位に切り上げる', () => {
    const data = [point(100), point(200), point(300)]
    // median=200, ×1.2=240 → 250
    expect(getYMax(data)).toBe(250)
  })

  it('単発スパイクに引きずられない', () => {
    const data = [point(100), point(100), point(100), point(100), point(5000)]
    // median=100, ×1.2=120 → 150（スパイク5000は無視）
    expect(getYMax(data)).toBe(150)
  })
})
