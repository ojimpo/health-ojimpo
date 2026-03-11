import { useState, useEffect, useCallback } from 'react'

export function useApi(url, options = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(async () => {
    setError(null)
    try {
      const resp = await fetch(url, options)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const json = await resp.json()
      setData(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [url])

  useEffect(() => {
    if (data === null) {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    fetchData()
  }, [fetchData])

  return { data, loading, error, refreshing, refetch: fetchData }
}

export async function apiPut(url, body) {
  const resp = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function apiPost(url, body = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function apiDelete(url) {
  const resp = await fetch(url, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}
