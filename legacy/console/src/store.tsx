import * as React from 'react'
import { api, type HealthInfo, type PolicyInfo, type UpstreamInfo } from '@/api'

type Stats = Record<string, number>

interface Store {
  health: HealthInfo | null
  policy: PolicyInfo | null
  upstreams: UpstreamInfo[]
  active: string
  setActive: (id: string) => void
  refresh: () => Promise<void>
  stats: Stats | null
  history: { t: number; req: number }[]
}

const Ctx = React.createContext<Store>(null as unknown as Store)
export const useStore = () => React.useContext(Ctx)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = React.useState<HealthInfo | null>(null)
  const [policy, setPolicy] = React.useState<PolicyInfo | null>(null)
  const [upstreams, setUpstreams] = React.useState<UpstreamInfo[]>([])
  const [active, setActive] = React.useState('dashboard')
  const [stats, setStats] = React.useState<Stats | null>(null)
  const [history, setHistory] = React.useState<{ t: number; req: number }[]>([])

  const refresh = React.useCallback(async () => {
    try {
      const [h, p, u] = await Promise.all([
        api.health().catch(() => null),
        api.policy().catch(() => null),
        api.upstreams().catch(() => []),
      ])
      if (h) setHealth(h)
      if (p) setPolicy(p)
      setUpstreams(u)
    } catch { /* 网关卡死时保持旧值 */ }
  }, [])

  React.useEffect(() => {
    refresh()
    const t = setInterval(refresh, 10_000)
    // stats 历史采样（sparkline 数据源，每 5 秒一个点，保留 40 点）
    const tick = async () => {
      try {
        const st = await api.stats()
        setStats(st)
        setHistory((h) => [...h, { t: Date.now(), req: st.total_requests }].slice(-40))
      } catch { /* 忽略 */ }
    }
    tick()
    const t2 = setInterval(tick, 5000)
    return () => { clearInterval(t); clearInterval(t2) }
  }, [refresh])

  return (
    <Ctx.Provider value={{ health, policy, upstreams, active, setActive, refresh, stats, history }}>
      {children}
    </Ctx.Provider>
  )
}
