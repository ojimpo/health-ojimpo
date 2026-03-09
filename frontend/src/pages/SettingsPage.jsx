import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, apiPut } from '../hooks/useApi'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import SourceCard from '../components/settings/SourceCard'
import ThresholdSettings from '../components/settings/ThresholdSettings'
import SharedViewSettings from '../components/settings/SharedViewSettings'

const phaseFilters = [
  { value: 'all', label: 'ALL' },
  { value: 'mvp', label: 'MVP' },
  { value: 'phase2', label: 'PHASE 2' },
  { value: 'phase3', label: 'PHASE 3' },
]

export default function SettingsPage() {
  const [phaseFilter, setPhaseFilter] = useState('all')
  const { data: sources, refetch: refetchSources } = useApi('/api/settings/sources')
  const { data: thresholds } = useApi('/api/settings/thresholds')
  const { data: sharedSettings, refetch: refetchShared } = useApi('/api/settings/shared')

  const filteredSources = sources
    ? phaseFilter === 'all'
      ? sources
      : sources.filter(s => s.phase === phaseFilter)
    : []

  const activeCount = sources ? sources.filter(s => s.status === 'active').length : 0
  const totalCount = sources ? sources.length : 0

  const handleSourceUpdate = async (sourceId, updates) => {
    await apiPut(`/api/settings/sources/${sourceId}`, updates)
    refetchSources()
  }

  const handleSharedToggle = async (enabled) => {
    await apiPut('/api/settings/shared', { enabled })
    refetchShared()
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

      {/* Phase filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {phaseFilters.map(f => (
          <button
            key={f.value}
            onClick={() => setPhaseFilter(f.value)}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: 1,
              padding: '6px 16px',
              borderRadius: 6,
              border: '1px solid',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              background: phaseFilter === f.value ? 'rgba(0,240,255,0.1)' : 'transparent',
              borderColor: phaseFilter === f.value ? 'var(--cyan)' : 'var(--border-subtle)',
              color: phaseFilter === f.value ? 'var(--cyan)' : 'var(--text-subtle)',
            }}
          >
            {f.label}
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

      {/* Shared view settings */}
      <SharedViewSettings settings={sharedSettings} onToggle={handleSharedToggle} />

      <Footer />
    </div>
  )
}
