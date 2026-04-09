import { useMemo } from 'react'
import { activityCategories } from '../constants/categories'

function cv(values) {
  const mean = values.reduce((s, v) => s + v, 0) / values.length
  if (mean === 0) return 0
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length
  return Math.sqrt(variance) / mean
}

export function sortCategoriesByStability(data, categories) {
  if (!data?.length) return categories
  return [...categories].sort((a, b) => cv(data.map(d => d[a.key] || 0)) - cv(data.map(d => d[b.key] || 0)))
}

export function useSortedCategories(chartData) {
  return useMemo(() => sortCategoriesByStability(chartData, activityCategories), [chartData])
}
