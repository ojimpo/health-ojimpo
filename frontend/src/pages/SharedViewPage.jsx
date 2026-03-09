import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { healthStatusConfig, culturalStatusConfig } from '../constants/statusConfig'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import StatusCard from '../components/common/StatusCard'
import TimeRangeSelector from '../components/common/TimeRangeSelector'
import ActivityChart from '../components/charts/ActivityChart'
import ConditionChart from '../components/charts/ConditionChart'
import TrendAnalysis from '../components/dashboard/TrendAnalysis'
import CategoryCards from '../components/dashboard/CategoryCards'
import RecentActivity from '../components/dashboard/RecentActivity'
import EvaWarningOverlay from '../components/shared/EvaWarningOverlay'
import FriendlyMessage from '../components/shared/FriendlyMessage'

export default function SharedViewPage() {
  const { token } = useParams()
  const [timeRange, setTimeRange] = useState('3m')
  const { data, loading, error } = useApi(`/api/shared/${token}?range=${timeRange}`)

  if (loading) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="SHARED VIEW" subtitle="共有ビュー" />
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: 2 }}>
          LOADING...
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="SHARED VIEW" subtitle="共有ビュー" />
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
      backgroundColor: presentation.bg_color,
    }}>
      {isCritical && <EvaWarningOverlay />}

      <div style={{ position: 'relative', zIndex: 1, maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header
          label="SHARED VIEW"
          title="HEALTH.OJIMPO.COM"
          subtitle="友人用共有ビュー"
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
        <ActivityChart
          data={data.activity_chart}
          height={300}
          saturation={presentation.chart_saturation}
        />
        <ConditionChart
          data={data.condition_chart}
          height={180}
          saturation={presentation.chart_saturation}
        />

        {/* Category cards (smaller) */}
        <CategoryCards cards={data.category_cards} small />

        {/* Recent activity (dimmed for CRITICAL) */}
        <RecentActivity activities={data.recent_activities} dimmed={isCritical} />

        <Footer />
      </div>
    </div>
  )
}
