import * as React from 'react'
import { ShieldCheck, Menu, X, Sparkles, Zap } from 'lucide-react'
import { cn, fmtPct } from '@/util'
import { presetCN } from '@/i18n'
import { useStore } from '@/store'
import { PLUGINS, PLUGIN_GROUPS } from '@/registry'
import { QuickTest } from '@/ui/quicktest'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/ui/tooltip'

/** 面板级错误边界：单个面板崩了给出提示，不拖垮整站 */
class PanelBoundary extends React.Component<{ children: React.ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: unknown) {
    return { err: String(e).slice(0, 200) }
  }
  componentDidCatch(e: unknown) { console.error('[panel]', e) }
  render() {
    if (this.state.err) {
      return (
        <div className="mx-auto max-w-lg p-6">
          <div className="glass glass-edge rounded-3xl p-6 text-center">
            <div className="text-sm font-medium text-red-300">这个面板加载出错了</div>
            <div className="mt-2 mono break-all rounded-xl bg-black/40 p-3 text-left text-xs text-muted-foreground">{this.state.err}</div>
            <button
              onClick={() => this.setState({ err: null })}
              className="mt-4 rounded-xl bg-gradient-to-r from-violet-500 to-cyan-400 px-4 py-2 text-sm text-white active:scale-95"
            >
              重试
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export function Shell() {
  const { active, setActive, health, policy } = useStore()
  const [open, setOpen] = React.useState(false)
  const [quickOpen, setQuickOpen] = React.useState(false)

  const activePlugin = PLUGINS.find((p) => p.id === active) ?? PLUGINS[0]

  return (
    <TooltipProvider delayDuration={200}>
      <QuickTest open={quickOpen} onOpenChange={setQuickOpen} />
      {/* 极光背景 + 噪点 */}
      <div className="aurora noise" />

      <div className="flex h-full w-full">
        {/* ===== 侧栏：液态玻璃 ===== */}
        <aside
          className={cn(
            'glass glass-edge fixed inset-y-0 left-0 z-40 flex w-[min(16.5rem,84vw)] flex-col transition-transform duration-300 rounded-r-3xl lg:static lg:w-64 lg:translate-x-0 lg:rounded-none',
            'rounded-none lg:rounded-r-3xl lg:my-3 lg:ml-3 lg:h-[calc(100%-1.5rem)]',
            open ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          {/* Logo：霓虹渐变 */}
          <div className="flex h-16 items-center gap-3 px-6">
            <div className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/30 to-cyan-400/20 ring-1 ring-white/10">
              <ShieldCheck className="h-5 w-5 text-gradient" strokeWidth={2.2} />
              <div className="absolute inset-0 rounded-2xl bg-violet-500/20 blur-lg -z-10" />
            </div>
            <div>
              <div className="text-base font-bold tracking-tight text-gradient">armor-gw</div>
              <div className="text-[11px] text-muted-foreground">穿拒网关 · 控制台</div>
            </div>
          </div>

          <nav className="flex-1 overflow-y-auto px-3 py-2">
            {PLUGIN_GROUPS.map((g, gi) => (
              <div key={g.key} className={cn('mb-4', gi === 0 && 'mt-1')}>
                <div className="mb-2 px-3 text-[11px] font-medium text-muted-foreground/70">
                  {g.label}
                </div>
                {PLUGINS.filter((p) => (p.group ?? 'core') === g.key).map((p, i) => {
                  const Icon = p.icon
                  const isActive = p.id === active
                  return (
                    <Tooltip key={p.id}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => { setActive(p.id); setOpen(false) }}
                          className={cn(
                            'group relative mb-1 flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm transition-all duration-300',
                            'animate-in-up',
                            isActive
                              ? 'bg-gradient-to-r from-violet-500/20 via-violet-500/10 to-transparent text-white font-medium'
                              : 'text-muted-foreground hover:bg-white/[.06] hover:text-foreground',
                          )}
                          style={{ animationDelay: `${gi * 90 + i * 45}ms` }}
                        >
                          {/* 激活指示条：霓虹发光 */}
                          {isActive && (
                            <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-gradient-to-b from-violet-400 to-cyan-400 glow-dot text-violet-400" />
                          )}
                          <Icon className={cn('h-4 w-4 shrink-0 transition-transform duration-300 group-hover:scale-110', isActive && 'text-violet-300')} />
                          <span className="truncate">{p.name}</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="right" className="glass border-white/10">{p.description}</TooltipContent>
                    </Tooltip>
                  )
                })}
              </div>
            ))}
          </nav>

          {/* 状态条 */}
          <div className="p-3">
            <div className="glass glass-edge flex items-center justify-between rounded-2xl px-4 py-3 text-xs shimmer">
              <span className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2 w-2 rounded-full glow-dot',
                    health?.ok ? 'bg-emerald-400 text-emerald-400' : 'bg-destructive text-destructive',
                  )}
                  style={{ animation: health?.ok ? 'pulse-dot 1.8s ease-in-out infinite' : undefined }}
                />
                <span className="text-foreground/90">{health ? `${health.routes.length} 个通道在线` : '连接中…'}</span>
              </span>
              <span className="rounded-full bg-white/[.06] px-2.5 py-0.5 text-[11px] text-muted-foreground">
                {policy ? presetCN(policy.preset) : '—'}
              </span>
            </div>
          </div>
        </aside>

        {/* 移动端遮罩 */}
        {open && <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden animate-in-fade" onClick={() => setOpen(false)} />}

        {/* ===== 主区 ===== */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 顶栏：悬浮玻璃 Dock */}
          <header className="sticky top-0 z-20 px-3 pt-3">
            <div className="glass glass-edge flex h-14 items-center gap-3 rounded-2xl px-5 shimmer">
              <button
                className="rounded-xl p-2 hover:bg-white/[.08] transition-colors lg:hidden"
                onClick={() => setOpen(!open)}
              >
                {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <activePlugin.icon className="h-4 w-4 text-violet-300" />
                  <span className="truncate text-[15px] font-semibold">{activePlugin.name}</span>
                </div>
                <div className="truncate text-xs text-muted-foreground">{activePlugin.description}</div>
              </div>
              <div className="ml-auto flex shrink-0 items-center gap-2">
                {/* 快速测试：任何页面一键发真请求 */}
                <button
                  onClick={() => setQuickOpen(true)}
                  className="flex shrink-0 items-center gap-1.5 rounded-xl border border-violet-400/25 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-200 transition-all hover:bg-violet-400/20 active:scale-95"
                  aria-label="快速测试"
                >
                  <Zap className="h-3.5 w-3.5" />
                  <span>快速测试</span>
                </button>
                <span className="hidden items-center gap-1.5 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-300 md:flex">
                  <Sparkles className="h-3.5 w-3.5" />
                  穿拒成功率 <span className="font-bold tabular">{fmtPct(1)}</span>
                </span>
              </div>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto">
            <PanelBoundary>
            <React.Suspense
              fallback={
                <div className="flex h-full items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-10 w-10 rounded-full border-2 border-violet-400/30 border-t-violet-400 animate-spin-slow" />
                    <span className="text-sm text-muted-foreground">面板加载中…</span>
                  </div>
                </div>
              }
            >
              <activePlugin.component />
            </React.Suspense>
            </PanelBoundary>
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
