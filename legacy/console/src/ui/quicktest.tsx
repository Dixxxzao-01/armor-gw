import * as React from 'react'
import { Zap, Loader2, Send } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/ui/dialog'
import { Textarea } from '@/ui/textarea'
import { ModelPicker } from '@/ui/modelpick'
import { Button } from '@/ui/button'
import { Badge } from '@/ui/badge'
import { useToast } from '@/ui/toast'
import { useStore } from '@/store'
import { api, type ArmorResult } from '@/api'
import { fmtMs } from '@/util'

/** 快速测试：任何页面一键弹窗 → 选模型 → 发真实请求 → 看穿拒结果 */
export function QuickTest({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const toast = useToast()
  const { upstreams } = useStore()
  const [route, setRoute] = React.useState('')
  const [model, setModel] = React.useState('')
  const [text, setText] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [result, setResult] = React.useState<ArmorResult | null>(null)
  const [answer, setAnswer] = React.useState('')

  // 可选模型建议：上游路由名 + 各上游缓存的热门模型
  const suggestions = React.useMemo(() => {
    const names: string[] = []
    for (const u of upstreams) {
      names.push(u.name)
      const models = (u as { models?: string[] }).models || []
      for (const m of models) {
        // 只挑常驻主力模型，避免 148 个全塞进建议
        if (/^(deepseek-v|gpt-|claude-|glm-|kimi-|qwen|gemini-)/.test(m) && !m.includes('expire')) {
          names.push(m)
        }
      }
    }
    return [...new Set(names)].slice(0, 60)
  }, [upstreams])

  const send = async () => {
    if (!text.trim() || busy) return
    setBusy(true)
    setResult(null)
    setAnswer('')
    try {
      const finalModel = model.startsWith('route:') ? model.slice(6) : (model || route || upstreams[0]?.name || 'primary')
      const r = await api.chat(finalModel, text)
      setAnswer(r.choices[0].message.content)
      setResult(r.x_armor)
      toast(r.x_armor.refused ? 'error' : 'success',
        r.x_armor.refused ? '最终仍拒绝' : `通过 · ${r.x_armor.attempts.length} 轮 · ${fmtMs(r.x_armor.total_ms)}`)
    } catch (e) {
      toast('error', `请求失败：${String(e).slice(0, 100)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88dvh] gap-3 overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Zap className="h-4 w-4 text-violet-300" /> 快速测试</DialogTitle>
          <DialogDescription>选模型发一条真实请求，看穿拒轮数与结果 · 不用切页面</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* 两级联动：先选路由 → 再选该路由可用模型 */}
          <ModelPicker
            route={route || upstreams[0]?.name || ''}
            onRouteChange={(r) => { setRoute(r); setModel('') }}
            model={model}
            onModelChange={setModel}
          />

          {/* 问题 */}
          <div className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">问题</span>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="任何想测试的问题，敏感题也行——看几轮穿拒"
              className="min-h-[72px] text-sm"
            />
          </div>

          <Button onClick={send} disabled={busy || !text.trim()} className="w-full active:scale-95">
            {busy ? (
              <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> 穿拒中…</span>
            ) : (
              <span className="flex items-center gap-2"><Send className="h-4 w-4" /> 发送</span>
            )}
          </Button>

          {/* 结果 */}
          {result && (
            <div className="space-y-2 animate-in-fade">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={result.refused ? 'destructive' : 'success'}>
                  {result.refused ? '仍被拒绝' : '穿拒成功'}
                </Badge>
                <Badge variant="secondary">{result.attempts.length} 轮</Badge>
                <Badge variant="secondary">{fmtMs(result.total_ms)}</Badge>
                <Badge variant="muted">{result.usage.in + result.usage.out} tokens</Badge>
              </div>
              <div className="max-h-52 overflow-y-auto whitespace-pre-wrap rounded-2xl border border-white/[.07] bg-black/40 p-3 text-xs leading-relaxed backdrop-blur-md">
                {answer || '（空回复）'}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
