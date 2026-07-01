import { createContext, useContext } from 'react'

export const SiteInfoContext = createContext({
  username: '',
  domain: '',
  loaded: false,
})

export function useSiteInfo() {
  return useContext(SiteInfoContext)
}
