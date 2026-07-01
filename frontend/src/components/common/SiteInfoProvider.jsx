import { useApi } from '../../hooks/useApi'
import { SiteInfoContext } from '../../hooks/useSiteInfo'

export default function SiteInfoProvider({ children }) {
  const { data, loading } = useApi('/api/site-info')
  const value = {
    username: data?.username || '',
    domain: data?.domain || '',
    loaded: !loading,
  }
  return (
    <SiteInfoContext.Provider value={value}>
      {children}
    </SiteInfoContext.Provider>
  )
}
