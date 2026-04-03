import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useApi, apiPut } from '../hooks/useApi'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import SourceCard from '../components/settings/SourceCard'
import ThresholdSettings from '../components/settings/ThresholdSettings'

const CATEGORY_LABELS = {
  music: '音楽',
  exercise: '運動',
  reading: '読書',
  movie: '映画',
  sns: 'SNS',
  coding: 'コード',
  calendar: '予定',
  live: 'ライブ',
  shopping: '買い物',
  fitness: 'フィットネス',
  sleep: '睡眠',
  weight: '体重',
}

export default function SettingsPage() {
  useEffect(() => { document.title = 'settings | health.ojimpo.com' }, [])
  const [categoryFilter, setCategoryFilter] = useState('all')
  const { data: sources, refetch: refetchSources } = useApi('/api/settings/sources')
  const { data: thresholds } = useApi('/api/settings/thresholds')


  // Build category list from sources
  const categories = sources
    ? [...new Set(sources.map(s => s.category))].sort()
    : []

  const filteredSources = sources
    ? categoryFilter === 'all'
      ? sources
      : sources.filter(s => s.category === categoryFilter)
    : []

  const activeCount = sources ? sources.filter(s => s.status === 'active').length : 0
  const totalCount = sources ? sources.length : 0

  const handleSourceUpdate = async (sourceId, updates) => {
    await apiPut(`/api/settings/sources/${sourceId}`, updates)
    refetchSources()
  }


  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <Header
        label="SETTINGS"
        title="DATA SOURCES"
        subtitle={`${activeCount} / ${totalCount} ソースが有効`}
      />

      {/* Back to dashboard */}
      <div style={{ marginBottom: 20 }}>
        <Link
          to="/"
          style={{ fontSize: 11, letterSpacing: 2, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 2 }}
        >
          ← DASHBOARD
        </Link>
      </div>

      {/* Category filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        <button
          onClick={() => setCategoryFilter('all')}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: 1,
            padding: '6px 16px',
            borderRadius: 6,
            border: '1px solid',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            background: categoryFilter === 'all' ? 'rgba(0,240,255,0.1)' : 'transparent',
            borderColor: categoryFilter === 'all' ? 'var(--cyan)' : 'var(--border-subtle)',
            color: categoryFilter === 'all' ? 'var(--cyan)' : 'var(--text-subtle)',
          }}
        >
          ALL
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setCategoryFilter(cat)}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: 1,
              padding: '6px 16px',
              borderRadius: 6,
              border: '1px solid',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              background: categoryFilter === cat ? 'rgba(0,240,255,0.1)' : 'transparent',
              borderColor: categoryFilter === cat ? 'var(--cyan)' : 'var(--border-subtle)',
              color: categoryFilter === cat ? 'var(--cyan)' : 'var(--text-subtle)',
            }}
          >
            {CATEGORY_LABELS[cat] || cat}
          </button>
        ))}
      </div>

      {/* Source cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {filteredSources.map((source, i) => (
          <SourceCard
            key={source.id}
            source={source}
            onUpdate={handleSourceUpdate}
            delay={i * 0.03}
          />
        ))}
      </div>

      {/* Threshold settings */}
      <ThresholdSettings thresholds={thresholds} />

      <Footer />
    </div>
  )
}
