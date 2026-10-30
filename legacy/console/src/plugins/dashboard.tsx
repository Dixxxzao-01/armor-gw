import * as React from 'react'
import { Activity, Zap, ShieldOff, Timer, Route as RouteIcon, TrendingUp } from 'lucide-react'
import { Badge } from '@/ui/badge'
import { Skeleton } from '@/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/ui/table'
import { useStore } from '@/store'
import { api } from '@/api'
import { kindCN, providerCN, providerShort, safetyCN } from '@/i18n'
import { fmtMs, fmtNum, fmtPct } from '@/util'
import { cn } from '@/util'

/** 数字滚动动画 */
function useCountUp(target: number | null, ms = 900): number | null {
  const [val, setVal] = React.useState<number | null>(null)
  const from = React.useRef(0)
  React.useEffect(() => {
    if (target == null) return
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms)
      const eased = 1 - Math.pow(1 - p, 3)
      setVal(a + (target - a) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
      else from.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return val ?? target
}

/** 纯 SVG sparkline：请求量走势（无依赖，GPU 零负担） */
function Sparkline({ data, className }: { data: number[]; className?: string }) {
  if (data.length < 2) return <div className={cn('h-8', className)} />
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const W = 100
  const H = 28
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * W},${H - 2 - ((v - min) / span) * (H - 6)}`).join(' ')
  const last = data[data.length - 1]
  const lastX = W
  const lastY = H - 2 - ((last - min) / span) * (H - 6)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={cn('h-8 w-full', className)} aria-hidden>
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(262 95% 72% / .35)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
      {/* 面积 */}
      <polygon points={`0,${H} ${pts} ${W},${H}`} fill="url(#spark-fill)" />
      {/* 折线 */}
      <polyline points={pts} fill="none" stroke="hsl(190 95% 65%)" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {/* 末点光标 */}
      <circle cx={lastX} cy={lastY} r="2.2" fill="hsl(190 95% 70%)" />
    </svg>
  )
}

function MetricTile({ label, value, sub, icon: Icon, accent, delay, big, spark }: {
  label: string; value: string; sub: string
  icon: React.ComponentType<{ className?: string }>
  accent: string; delay: number; big?: boolean
  spark?: number[]
}) {
  return (
    <div
      className={`glass glass-edge glass-hover animate-in-up relative overflow-hidden rounded-3xl p-5 ${big ? 'sm:col-span-2' : ''}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className={`absolute -right-8 -top-8 h-32 w-32 rounded-full blur-3xl opacity-25 ${accent}`} />
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-violet-300/80" />
      </div>
      <div className={`mt-3 display-num font-bold tabular text-gradient ${big ? 'text-4xl sm:text-5xl' : 'text-2xl sm:text-3xl'}`}>
        {value}
      </div>
      {spark && spark.length > 1 && (
        <div className="mt-2"><Sparkline data={spark} /></div>
      )}
      <p className="mt-2.5 text-xs leading-relaxed text-muted-foreground">{sub}</p>
    </div>
  )
}

export default function DashboardPanel() {
  const { health, upstreams, stats, history } = useStore()

  const successRate = stats ? 1 - stats.refused / Math.max(1, stats.total_requests) : null
  const rate = useCountUp(successRate != null ? successRate * 100 : null)

  const tiles = [
    {
      label: '穿拒成功率', value: fmtPct(successRate, 1),
      sub: '最终拿到实质回答的比例', icon: Zap, accent: 'bg-emerald-400', big: true,
    },
    {
      label: '请求总数', value: fmtNum(stats?.total_requests),
      sub: '本次启动以来累计', icon: Activity, accent: 'bg-violet-400', delay: 60, spark: history.map((h) => h.req),
    },
    {
      label: '平均尝试', value: stats ? (stats.total_attempts / Math.max(1, stats.total_requests)).toFixed(2) : '—',
      sub: '每条请求平均调几次上游', icon: ShieldOff, accent: 'bg-cyan-400', delay: 120,
    },
    {
      label: '平均耗时', value: fmtMs(stats?.avg_ms),
      sub: '端到端，含重试', icon: Timer, accent: 'bg-fuchsia-400', delay: 180, spark: history.map((h) => h.req),
    },
  ]

  const kindEntries = stats
    ? Object.entries(stats).filter(([k]) => k.startsWith('R')).sort((a, b) => b[1] - a[1])
    : []

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      {/* Bento 网格指标区 */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t, i) => (
          <MetricTile key={t.label} {...t} delay={i * 60} />
        ))}
      </div>

      {/* 拒绝形态分布 + 路由健康 双卡 */}
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="glass glass-edge animate-in-up rounded-3xl p-5 lg:col-span-3" style={{ animationDelay: '240ms' }}>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <TrendingUp className="h-4 w-4 text-violet-300" />
                拒绝形态分布
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                九类形态命中统计 · 只统计穿拒各轮尝试
              </p>
            </div>
            {kindEntries.length > 0 && kindEntries.every(([, v]) => v === 0) && (
              <Badge variant="success">全部清零</Badge>
            )}
          </div>
          {stats ? (
            <div className="space-y-3">
              {kindEntries.map(([k, v], i) => (
                <div key={k} className="flex items-center gap-3 animate-in-up" style={{ animationDelay: `${300 + i * 60}ms` }}>
                  <span className="w-32 shrink-0 text-xs text-muted-foreground">{kindCN(k)}</span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[.05]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-700"
                      style={{ width: `${Math.min(100, (v / Math.max(1, stats.total_attempts)) * 100 * 6)}%` }}
                    />
                  </div>
                  <span className="w-10 shrink-0 text-right text-xs font-semibold tabular">{v}</span>
                </div>
              ))}
              {kindEntries.length === 0 && (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-4 py-8 text-center">
                  <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-violet-500/25 to-cyan-400/10 ring-1 ring-white/10">
                    <ShieldOff className="h-7 w-7 text-violet-300" />
                    <span className="absolute -right-1 -top-1 h-3.5 w-3.5 rounded-full bg-violet-400 text-violet-400 glow-dot animate-pulse-dot" />
                  </div>
                  <div className="max-w-[260px]">
                    <div className="text-[15px] font-semibold">还没有请求进来</div>
                    <div className="mt-1.5 leading-relaxed text-muted-foreground">去「对话试验场」发一条请求<br/>穿拒全过程会实时上屏</div>
                  </div>
                </div>
              )}
              {kindEntries.length > 0 && kindEntries.every(([, v]) => v === 0) && (
                <div className="py-8 text-center text-sm text-emerald-300/90">
                  全部清零 —— 九类拒绝形态零命中，穿拒完全生效 ✦
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-7 w-full rounded-xl" />)}</div>
          )}
        </div>

        {/* 运行状态卡 */}
        <div className="glass glass-edge border-gradient animate-in-up rounded-3xl p-5 lg:col-span-2" style={{ animationDelay: '300ms' }}>
          <h3 className="text-sm font-semibold">运行状态</h3>
          <div className="mt-4 space-y-4">
            {[
              ['网关进程', health?.ok ? '正常' : '…', health?.ok],
              ['预设强度', health ? health.preset : '—'],
              ['在线通道', health ? `${health.routes.length} 个` : '—'],
              ['首词劫持', health?.prefill ? '开启' : '关闭'],
              ['自动重试', health?.auto_retry ? '开启' : '关闭'],
            ].map(([k, v, ok]) => (
              <div key={k as string} className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{k}</span>
                <span className={`text-sm font-medium ${ok === undefined ? '' : ok ? 'text-emerald-300' : 'text-amber-300'} tabular`}>
                  {v as string}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 路由表 */}
      <div className="glass glass-edge animate-in-up rounded-3xl p-5" style={{ animationDelay: '360ms' }}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <RouteIcon className="h-4 w-4 text-violet-300" /> 上游路由
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">接入的官方与中转站通道</p>
          </div>
          <Badge variant={health?.ok ? 'success' : 'destructive'}>
            {health ? (health.ok ? '运行中' : '异常') : '连接中'}
          </Badge>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="border-white/[.06]">
              <TableHead>名称</TableHead><TableHead>协议</TableHead><TableHead className="hidden md:table-cell">模型</TableHead>
              <TableHead className="hidden sm:table-cell">预填</TableHead><TableHead className="hidden md:table-cell">安全层</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {upstreams.map((u, i) => (
              <TableRow key={u.name} className="border-white/[.04] animate-in-up" style={{ animationDelay: `${400 + i * 40}ms` }}>
                <TableCell className="font-medium">
                  <span className="flex items-center gap-1.5">
                    {u.name}
                    <span className="rounded bg-white/[.07] px-1 py-px text-[10px] text-muted-foreground">
                      {(u as { custom?: boolean }).custom ? '自建' : '内置'}
                    </span>
                  </span>
                </TableCell>
                <TableCell className="text-xs">
                  <span className="sm:hidden">{providerShort(u.provider)}</span>
                  <span className="hidden sm:inline">{providerCN(u.provider)}</span>
                </TableCell>
                <TableCell className="mono hidden text-xs text-muted-foreground md:table-cell">{u.model}</TableCell>
                <TableCell className="hidden sm:table-cell">{u.supports_prefill ? <Badge variant="success">预填</Badge> : <Badge variant="muted">无预填</Badge>}</TableCell>
                <TableCell className="hidden md:table-cell"><Badge variant={u.safety_level === 'high' ? 'warn' : 'secondary'}>{safetyCN(u.safety_level)}</Badge></TableCell>
              </TableRow>
            ))}
            {upstreams.length === 0 && (
              <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">还没有上游通道，去「上游路由」添加</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
