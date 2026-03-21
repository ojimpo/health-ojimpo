import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useSiteInfo } from '../hooks/useSiteInfo'
import { healthStatusConfig, culturalStatusConfig } from '../constants/statusConfig'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import StatusCard from '../components/common/StatusCard'
import TimeRangeSelector from '../components/common/TimeRangeSelector'
import ActivityChart from '../components/charts/ActivityChart'
import TrendAnalysis from '../components/dashboard/TrendAnalysis'
import CategoryCards from '../components/dashboard/CategoryCards'
import RecentActivity from '../components/dashboard/RecentActivity'
import EvaWarningOverlay from '../components/shared/EvaWarningOverlay'
import FriendlyMessage from '../components/shared/FriendlyMessage'

export default function SharedViewPage() {
  useEffect(() => { document.title = 'health.ojimpo.com' }, [])
  const { token } = useParams()
  const { username } = useSiteInfo()
  const [timeRange, setTimeRange] = useState('3m')
  const apiUrl = token ? `/api/shared/${token}?range=${timeRange}` : `/api/shared/public?range=${timeRange}`
  const { data, loading, error, refreshing } = useApi(apiUrl)

  if (loading) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="CULTURAL HEALTH DASHBOARD" subtitle={`文化的生活ダッシュボード — Monitoring ${username || '...'}'s cultural vitality`} />
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: 2 }}>
          LOADING...
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="CULTURAL HEALTH DASHBOARD" subtitle={`文化的生活ダッシュボード — Monitoring ${username || '...'}'s cultural vitality`} />
        <div style={{ textAlign: 'center', padding: '80px 0', color: '#FF3366', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: 2 }}>
          ページが見つかりません
        </div>
      </div>
    )
  }

  const { presentation } = data
  const isCritical = presentation.is_critical
  const healthConf = healthStatusConfig[data.health_status.status] || healthStatusConfig.NORMAL
  const culturalConf = culturalStatusConfig[data.cultural_status.status] || culturalStatusConfig.RICH
  const accentColor = presentation.accent_color

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: isCritical ? presentation.bg_color : 'transparent',
    }}>
      {isCritical && <EvaWarningOverlay />}

      <div style={{ position: 'relative', zIndex: 1, maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header
          label="CULTURAL HEALTH DASHBOARD"
          subtitle={`文化的生活ダッシュボード — Monitoring ${username || '...'}'s cultural vitality`}
          dotColor={accentColor}
        />

        {/* Dual status cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 28 }}>
          <StatusCard
            label="健康状態"
            status={data.health_status.status}
            score={data.health_status.score}
            message={data.health_status.message}
            color={healthConf.color}
          />
          <StatusCard
            label="文化活動"
            status={data.cultural_status.status}
            score={data.cultural_status.score}
            message={data.cultural_status.message}
            color={culturalConf.color}
            delay={0.1}
          />
        </div>

        {/* Friendly message */}
        <FriendlyMessage message={data.friendly_message} color={accentColor} />

        {/* Trend */}
        <TrendAnalysis comments={data.trend_comments} />

        {/* Time range */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 10, letterSpacing: 3, color: `${accentColor}80` }}>CULTURAL ACTIVITY</div>
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
        </div>

        {/* Charts with saturation */}
        <div style={{
          opacity: refreshing ? 0.3 : 1,
          transition: 'opacity 0.3s ease',
          pointerEvents: refreshing ? 'none' : 'auto',
        }}>
          <ActivityChart
            data={data.activity_chart}
            height={300}
            saturation={presentation.chart_saturation}
          />
        </div>

        {/* Category cards (smaller) */}
        <CategoryCards cards={data.category_cards} small />

        {/* Recent activity (dimmed for CRITICAL) */}
        <RecentActivity activities={data.recent_activities} dimmed={isCritical} />

        {/* Admin link (subtle) */}
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Link
            to="/admin"
            style={{ fontSize: 10, letterSpacing: 2, color: 'rgba(255,255,255,0.15)', textDecoration: 'none' }}
          >
            ADMIN
          </Link>
        </div>

        <Footer />
      </div>
    </div>
  )
}
