import { useState } from 'react'
import { Link } from 'react-router-dom'
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
import StateCards from '../components/dashboard/StateCards'
import RecentActivity from '../components/dashboard/RecentActivity'

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState('3m')
  const [hoveredCategory, setHoveredCategory] = useState(null)
  const { data, loading, error } = useApi(`/api/dashboard?range=${timeRange}`)

  if (loading) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="ADMIN DASHBOARD" subtitle="管理用ダッシュボード" />
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: 2 }}>
          LOADING...
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <Header label="ADMIN DASHBOARD" subtitle="管理用ダッシュボード" />
        <div style={{ textAlign: 'center', padding: '80px 0', color: '#FF3366', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: 2 }}>
          {error || 'データの取得に失敗しました'}
        </div>
      </div>
    )
  }

  const healthConf = healthStatusConfig[data.health_status.status] || healthStatusConfig.NORMAL
  const culturalConf = culturalStatusConfig[data.cultural_status.status] || culturalStatusConfig.RICH

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
      <Header
        label="ADMIN DASHBOARD"
        subtitle="管理用ダッシュボード"
      />

      <div style={{ display: 'inline-block', padding: '4px 12px', border: '1px solid rgba(255,51,102,0.3)', color: '#FF3366', fontSize: 10, letterSpacing: 3, marginBottom: 20 }}>
        ADMIN MODE
      </div>

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

      {/* Trend */}
      <TrendAnalysis comments={data.trend_comments} />

      {/* Time range + chart label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 10, letterSpacing: 3, color: 'rgba(0,240,255,0.5)' }}>CULTURAL ACTIVITY</div>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
      </div>

      {/* Charts */}
      <ActivityChart data={data.activity_chart} hoveredCategory={hoveredCategory} />
      <ConditionChart data={data.condition_chart} />

      {/* Category cards */}
      <CategoryCards cards={data.category_cards} onHover={setHoveredCategory} />

      {/* State cards */}
      <StateCards cards={data.state_cards} />

      {/* Recent activity */}
      <RecentActivity activities={data.recent_activities} />

      {/* Nav links */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginBottom: 24 }}>
        <Link
          to="/"
          style={{ fontSize: 11, letterSpacing: 2, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 2 }}
        >
          PUBLIC VIEW
        </Link>
        <Link
          to="/settings"
          style={{ fontSize: 11, letterSpacing: 2, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 2 }}
        >
          SETTINGS
        </Link>
      </div>

      <Footer />
    </div>
  )
}
