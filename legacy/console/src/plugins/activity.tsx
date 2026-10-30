import * as React from 'react'
import { Activity, Pause, Play } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/ui/card'
import { Button } from '@/ui/button'
import { Badge } from '@/ui/badge'
import { Input } from '@/ui/input'
import { cn, timeAgo } from '@/util'

interface Row {
  ts: number
  trace_id: string
  route: string
  refused: boolean
  attempts: number
  ms: number
  text: string
}

export default function ActivityPanel() {
  const [rows, setRows] = React.useState<Row[]>([])
  const [filter, setFilter] = React.useState('')
  const [onlyRefused, setOnlyRefused] = React.useState(false)
  const [paused, setPaused] = React.useState(false)
  const buf = React.useRef<Row[]>([])

  React.useEffect(() => {
    const es = new EventSource(`/v1/admin/logs/stream?token=${encodeURIComponent(localStorage.getItem('armor-gw-key') || 'sk-armor-test')}`)
    es.onmessage = (ev) => {
      try {
        const row = JSON.parse(ev.data) as Row
        buf.current = [row, ...buf.current].slice(0, 400)
      } catch { /* 忽略非 JSON 心跳 */ }
    }
    es.onerror = () => { /* 断线由浏览器自动重连 */ }
    return () => es.close()
  }, [])

  React.useEffect(() => {
    const t = setInterval(() => {
      if (!paused) setRows([...buf.current])
    }, 800)
    return () => clearInterval(t)
  }, [paused])

  const shown = rows.filter((r) => {
    if (onlyRefused && !r.refused) return false
    if (filter && !(r.trace_id.includes(filter) || r.route.includes(filter) || r.text.includes(filter))) return false
    return true
  })

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              实时流水
              <span className={cn('ml-1 h-1.5 w-1.5 rounded-full', paused ? 'bg-muted-foreground' : 'bg-emerald-500 animate-pulse-dot')} />
            </CardTitle>
            <CardDescription>实时推送 · 最近 400 条 · 新请求会立刻出现在最上面</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Input
              placeholder="按 trace / 路由 / 内容过滤"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-52"
            />
            <Button
              variant={onlyRefused ? 'default' : 'outline'}
              size="sm"
              onClick={() => setOnlyRefused(!onlyRefused)}
            >
              只看拒绝
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setPaused(!paused)} title={paused ? '继续' : '暂停'}>
              {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5">
            {shown.map((r) => (
              <div
                key={r.trace_id + r.ts}
                className={cn(
                  'flex items-center gap-3 rounded-xl border border-white/[.06] px-3.5 py-2.5 text-sm transition-all animate-in-up',
                  r.refused ? 'border-red-400/30 bg-red-400/[.06]' : 'hover:bg-white/[.05]',
                )}
              >
                <span className="w-16 shrink-0 text-xs text-muted-foreground">{timeAgo(r.ts)}</span>
                <Badge variant="muted" className="mono shrink-0" title="追踪号">{r.trace_id}</Badge>
                <Badge variant="secondary" className="shrink-0">{r.route}</Badge>
                <Badge variant={r.refused ? 'destructive' : 'success'} className="shrink-0">
                  {r.refused ? '未通过' : '已通过'}
                </Badge>
                <span className="shrink-0 text-xs text-muted-foreground">{r.attempts} 轮</span>
                <span className="shrink-0 text-xs text-muted-foreground">{r.ms} 毫秒</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{r.text}</span>
              </div>
            ))}
            {shown.length === 0 && (
              <div className="py-12 text-center text-sm text-muted-foreground">
                {rows.length === 0 ? '等待请求流入 · 去「对话试验场」发一条试试' : '没有符合筛选条件的记录'}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
