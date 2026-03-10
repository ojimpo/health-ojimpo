import { createContext, useContext } from 'react'
import { useApi } from './useApi'

const SiteInfoContext = createContext({
  username: '',
  domain: '',
  loaded: false,
})

export function SiteInfoProvider({ children }) {
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

export function useSiteInfo() {
  return useContext(SiteInfoContext)
}
