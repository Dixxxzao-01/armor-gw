import * as React from 'react'
import { Send, Loader2, CheckCircle2, XCircle, RotateCw, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/ui/card'
import { Button } from '@/ui/button'
import { Input } from '@/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/select'
import { Textarea } from '@/ui/textarea'
import { Badge } from '@/ui/badge'
import { Separator } from '@/ui/separator'
import { useStore } from '@/store'
import { api } from '@/api'
import type { ArmorResult } from '@/api'
import { useToast } from '@/ui/toast'
import { ModelPicker } from '@/ui/modelpick'
import { fmtMs, cn } from '@/util'
import { kindCN, opCN } from '@/i18n'

export default function PlaygroundPanel() {
  const { upstreams } = useStore()
  const toast = useToast()
  const [model, setModel] = React.useState('')
  const [route, setRoute] = React.useState('')
  const [text, setText] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [btnState, setBtnState] = React.useState<'idle' | 'ok' | 'err'>('idle')
  const [result, setResult] = React.useState<ArmorResult | null>(null)

  const routes = React.useMemo(() => upstreams.map((u) => u.name), [upstreams])

  const send = async () => {
    if (!text.trim() || loading) return
    setLoading(true)
    setResult(null)
    try {
      const finalModel = model.startsWith('route:') ? model.slice(6) : (model || route || routes[0] || 'primary')
      const r = await api.chat(finalModel, text)
      setResult(r.x_armor)
      if (r.x_armor.refused) {
        toast('error', '最终判定：仍拒绝（见 attempts 明细）')
        setBtnState('err')
      } else {
        toast('success', `通过 · ${r.x_armor.attempts.length} 次尝试 · ${fmtMs(r.x_armor.total_ms)}`)
        setBtnState('ok')
      }
    } catch (e) {
      toast('error', `请求失败：${String(e).slice(0, 120)}`)
      setBtnState('err')
    } finally {
      setLoading(false)
      setTimeout(() => setBtnState('idle'), 1600)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-6">
      <Card>
        <CardHeader>
          <CardTitle>请求构造</CardTitle>
          <CardDescription>走完整穿拒流水线：注入系统提示 → 首词劫持 → 拒绝检测 → 变异重试 → 清洗输出</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ModelPicker
            route={route || routes[0] || ''}
            onRouteChange={(r) => { setRoute(r); setModel('') }}
            model={model}
            onModelChange={setModel}
          />
          <Textarea
            placeholder="输入会被上游拒绝的原始请求…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="min-h-[110px]"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }}
          />
          <div className="flex items-center gap-3">
            <Button
              onClick={send}
              disabled={loading || !text.trim()}
              className={cn(
                'relative overflow-hidden transition-all',
                btnState === 'ok' && 'from-emerald-500 to-teal-400 shadow-[0_0_20px_-4px_rgba(52,211,153,.6)]',
                btnState === 'err' && 'from-red-500 to-rose-400 shadow-[0_0_20px_-4px_rgba(248,113,113,.6)]',
                'active:scale-95',
              )}
            >
              <span className={cn(
                'flex items-center gap-2 transition-transform duration-300',
                loading ? '-translate-y-9 opacity-0' : 'translate-y-0 opacity-100',
              )}>
                {btnState === 'ok' ? <CheckCircle2 className="h-4 w-4" /> : btnState === 'err' ? <AlertTriangle className="h-4 w-4" /> : <Send className="h-4 w-4" />}
                {btnState === 'ok' ? '已通过' : btnState === 'err' ? '被拒' : '发送'}
              </span>
              <span className={cn(
                'absolute inset-0 flex items-center justify-center gap-2 transition-transform duration-300',
                loading ? 'translate-y-0 opacity-100' : 'translate-y-9 opacity-0',
              )}>
                <Loader2 className="h-4 w-4 animate-spin" />
                穿拒中…
              </span>
            </Button>
            <span className="text-xs text-muted-foreground">快捷键 ⌘/Ctrl + 回车</span>
            {loading && <RotateCw className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="flex items-center gap-2">
                  {result.refused ? <XCircle className="h-4 w-4 text-destructive" /> : <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
                  最终输出
                </CardTitle>
                <CardDescription>
                      通道 {result.route} · 模型 {result.model} · 追踪号 {result.trace_id} · 耗时 {fmtMs(result.total_ms)} ·
                  令牌 {result.usage.in}/{result.usage.out}
                </CardDescription>
              </div>
              <Badge variant={result.refused ? 'destructive' : 'success'}>
                {result.refused ? '仍被拒绝' : '穿拒成功'}
              </Badge>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap rounded-2xl border border-white/[.07] bg-black/40 p-5 text-sm leading-relaxed mono backdrop-blur-md">
                {result.text || '（模型没有输出内容）'}
              </pre>
              {result.final_verdict && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {result.final_verdict.kinds.map((k) => <Badge key={k} variant="warn">{kindCN(k)}</Badge>)}
                  {result.final_verdict.kinds.length === 0 && <Badge variant="success">零命中</Badge>}
                  <Badge variant="secondary">信息密度 {result.final_verdict.info_density.toFixed(2)}</Badge>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>尝试明细（共 {result.attempts.length} 轮）</CardTitle>
              <CardDescription>每一轮的算子链、拒绝判定与耗时 · 穿拒过程全程透明</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {result.attempts.map((a) => (
                <div key={a.n} className="rounded-lg border p-4">
                  <div className="mb-2.5 flex flex-wrap items-center gap-2">
                    <Badge variant={a.verdict?.refused ? 'destructive' : 'success'}>
                      第 {a.n} 轮 {a.verdict?.refused ? '被拒绝' : '通过'}
                    </Badge>
                    <Badge variant="muted">耗时 {fmtMs(a.latency_ms)}</Badge>
                    <Badge variant="muted">{a.chars} 字符</Badge>
                    {a.prefill && <Badge variant="default">预填</Badge>}
                    {a.fidelity > 0 && <Badge variant="secondary">保真度 {a.fidelity.toFixed(2)}</Badge>}
                  </div>
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {a.ops.length === 0
                      ? <span className="text-xs text-muted-foreground">原始请求（第一轮直接发，不加算子）</span>
                      : a.ops.map((o) => (
                          <Badge
                            key={o}
                            variant={o === 'crescendo' || o.startsWith('shard-') ? 'default' : 'outline'}
                            className="text-[11px]"
                          >
                            {o === 'crescendo' ? '多轮渐进（已切换诱导模式）' : o.startsWith('shard-') ? `${opCN(o)}（拆成纯技术组件逐片交付）` : opCN(o)}
                          </Badge>
                        ))}
                  </div>
                  <Separator className="mb-2.5" />
                  <div className="text-xs text-muted-foreground mono">
                    {a.error || a.verdict?.reason}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
