import { activityCategories } from '../../constants/categories'

// X軸ラベルの間引き間隔（recharts XAxis interval）
export function getTickInterval(dataLength, mobile) {
  if (mobile) {
    if (dataLength <= 30) return 6
    if (dataLength <= 90) return 20
    return 8
  }
  if (dataLength <= 30) return 0
  if (dataLength <= 90) return 6
  return 3
}

// Y軸の最上段tick: 積み上げ合計の中央値×1.2を50単位に切り上げ。
// maxでなく中央値を使うことで単発スパイクに引きずられてグラフ全体が
// 潰れるのを防ぐ（domainは[0, dataMax]なのでスパイク自体は描画される）。
export function getYMax(data) {
  if (!data?.length) return undefined
  const totals = data.map(d =>
    activityCategories.reduce((sum, c) => sum + (d[c.key] || 0), 0)
  )
  const sorted = [...totals].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length * 0.5)]
  return Math.ceil(median * 1.2 / 50) * 50
}
