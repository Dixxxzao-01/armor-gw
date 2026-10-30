import * as React from 'react'
import { RefreshCw, Loader2, Search } from 'lucide-react'
import { Input } from '@/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/select'
import { useStore } from '@/store'
import { api } from '@/api'

/** 两级联动选模器：先选上游路由 → 拉取该路由可用模型 → 选模型。
 *  任何面板复用（快速测试 / 对话试验场）。 */
export function ModelPicker({
  route, onRouteChange,
  model, onModelChange,
  className,
}: {
  route: string
  onRouteChange: (r: string) => void
  model: string
  onModelChange: (m: string) => void
  className?: string
}) {
  const { upstreams } = useStore()
  const [models, setModels] = React.useState<string[]>([])
  const [loading, setLoading] = React.useState(false)
  const [fetchedFor, setFetchedFor] = React.useState('')
  const [query, setQuery] = React.useState('')
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return models
    return models.filter((m) => m.toLowerCase().includes(q))
  }, [models, query])

  const routeNames = upstreams.map((u) => u.name)
  const active = upstreams.find((u) => u.name === route)

  // 拉取该路由的模型列表：优先用缓存（upstreams.json 的 models），空则实时探测
  const loadModels = React.useCallback(async (force = false) => {
    if (!active) { setModels([]); return }
    const cached = (active as { models?: string[] }).models || []
    if (cached.length && !force) { setModels(cached); setFetchedFor(route); return }
    setLoading(true)
    try {
      // 网关侧持密钥拉取该路由模型列表（面板不接触 key）
      const r = await api.routeModels(route)
      if (r.ok && r.models.length) {
        setModels(r.models)
        setFetchedFor(route)
      } else {
        setModels([])
      }
    } catch {
      setModels([])
    } finally {
      setLoading(false)
    }
  }, [active, route])

  // 切换路由：模型列表与已选模型联动重置
  React.useEffect(() => {
    if (route !== fetchedFor) {
      onModelChange('')
      loadModels(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route])

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-2">
        {/* 第一级：上游路由 */}
        <Select value={route} onValueChange={onRouteChange}>
          <SelectTrigger className="min-w-[7.5rem] max-w-[11rem] flex-1">
            <SelectValue placeholder="选择上游路由" />
          </SelectTrigger>
          <SelectContent>
            {routeNames.map((r) => (
              <SelectItem key={r} value={r}>
                {r}{upstreams.find((u) => u.name === r)?.custom === false ? ' ·内置' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 第二级：该路由可用模型 */}
        <Select value={model} onValueChange={onModelChange}>
          <SelectTrigger className="min-w-[9rem] flex-[1.6]">
            <SelectValue placeholder={loading ? '模型列表获取中…' : (models.length ? `选模型（${models.length} 个）` : '该路由默认模型')} />
          </SelectTrigger>
          <SelectContent>
            {/* 模型搜索框：150+ 模型秒查 */}
            <div className="sticky top-0 z-10 border-b border-white/[.07] bg-black/60 p-2 backdrop-blur-md">
              <div className="flex items-center gap-2 rounded-lg bg-white/[.06] px-2.5">
                <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={`搜 ${models.length} 个模型…`}
                  className="h-8 w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground/60"
                  onKeyDown={(e) => e.stopPropagation()}
                />
              </div>
            </div>
            {/* 路由直连（用路由名当模型）始终置顶 */}
            <SelectItem value={`route:${route}`}>直连 {route}（路由默认）</SelectItem>
            {filtered.map((m) => (
              <SelectItem key={m} value={m} className="mono text-xs">{m}</SelectItem>
            ))}
            {query.trim() && filtered.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                没有匹配「{query}」的模型
              </div>
            )}
          </SelectContent>
        </Select>

        {/* 刷新模型列表 */}
        <button
          onClick={() => loadModels(true)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[.04] transition-colors hover:bg-white/[.09] active:scale-95"
          aria-label="重新获取模型列表"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin text-violet-300" /> : <RefreshCw className="h-4 w-4 text-muted-foreground" />}
        </button>
      </div>
      {/* 状态说明行 */}
      <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
        <span>
          {models.length
            ? `已加载 ${models.length} 个可用模型 · 由路由 ${route} 实时校验`
            : loading ? '正在从上游拉取模型列表…' : '无缓存列表，点 ↻ 从上游实时获取'}
        </span>
      </div>
    </div>
  )
}
