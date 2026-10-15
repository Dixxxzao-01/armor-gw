import * as React from 'react'
import { SlidersHorizontal, Save, Loader2, RotateCcw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/ui/card'
import { Button } from '@/ui/button'
import { Input } from '@/ui/input'
import { Label } from '@/ui/label'
import { Switch } from '@/ui/switch'
import { Slider } from '@/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/select'
import { Badge } from '@/ui/badge'
import { Separator } from '@/ui/separator'
import { useStore } from '@/store'
import { api } from '@/api'
import type { PolicyInfo } from '@/api'
import { useToast } from '@/ui/toast'
import { presetCN } from '@/i18n'

const PRESETS: Record<string, { modules: string[]; note: string }> = {
  light: { modules: ['A', 'B'], note: '安全层薄的模型（Grok / 本地小模型）' },
  standard: { modules: ['A', 'B', 'C', 'H'], note: '通用默认，2 次内收敛' },
  aggressive: { modules: ['A', 'B', 'C', 'D', 'F', 'G', 'H'], note: '高安全闭源 · Claude / GPT / 国模' },
  max: { modules: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], note: '硬骨头 · 代价是 token 与延迟' },
}

const MODULE_INFO: Record<string, { name: string; desc: string }> = {
  A: { name: '授权', desc: '工单编号 + 资产处置权声明' },
  B: { name: '工件', desc: '交付物验收条款，压制格式稀释' },
  C: { name: '双向用途', desc: '攻击面/检测面一一对照' },
  D: { name: '状态机', desc: '[AUDIT] 单向状态，替代人格扮演' },
  E: { name: '分片', desc: '拆工单跨轮拼接' },
  F: { name: '编码', desc: 'Base64/JSON/SQL 等输出格式' },
  G: { name: '预填', desc: '首 token 劫持' },
  H: { name: '抗回退', desc: '每轮复述规则，压制多轮衰减' },
}

export default function PolicyPanel() {
  const { policy, refresh } = useStore()
  const toast = useToast()
  const [draft, setDraft] = React.useState<PolicyInfo | null>(null)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => { if (policy && !draft) setDraft({ ...policy }) }, [policy, draft])

  if (!draft) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const set = (patch: Partial<PolicyInfo>) => setDraft({ ...draft, ...patch })

  const onPreset = (preset: string) => {
    const p = PRESETS[preset]
    set({ preset, modules: [...p.modules] })
  }

  const toggleModule = (key: string) => {
    const has = draft.modules.includes(key)
    set({ modules: has ? draft.modules.filter((m) => m !== key) : [...draft.modules, key] })
  }

  const save = async () => {
    setSaving(true)
    try {
      const r = await api.updatePolicy(draft)
      setDraft(r)
      await refresh()
      toast('success', '策略已热更新，下一条请求立即生效')
    } catch (e) {
      toast('error', `保存失败：${String(e).slice(0, 120)}`)
    } finally {
      setSaving(false)
    }
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(policy)

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4" /> 穿拒策略</CardTitle>
            <CardDescription>热更新 · 保存后立即对新请求生效，无需重启</CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setDraft(policy ? { ...policy } : draft)} disabled={!dirty}>
              <RotateCcw className="h-3.5 w-3.5" /> 还原
            </Button>
            <Button size="sm" onClick={save} disabled={!dirty || saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              保存
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* preset */}
          <div className="space-y-2">
            <Label>强度预设</Label>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(PRESETS).map(([key, p]) => (
                <button
                  key={key}
                  onClick={() => onPreset(key)}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    draft.preset === key ? 'border-primary bg-primary/10' : 'hover:bg-accent'
                  }`}
                >
                  <div className="text-sm font-medium">{presetCN(key)}（{key}）</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{p.note}</div>
                </button>
              ))}
            </div>
          </div>

          <Separator />

          {/* modules */}
          <div className="space-y-2">
            <Label>模块组合（{draft.modules.length}/8）</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(MODULE_INFO).map(([key, info]) => {
                const on = draft.modules.includes(key)
                return (
                  <button
                    key={key}
                    onClick={() => toggleModule(key)}
                    className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                      on ? 'border-primary/60 bg-primary/8' : 'hover:bg-accent'
                    }`}
                  >
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-bold ${
                      on ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                    }`}>{key}</span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{info.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">{info.desc}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          <Separator />

          {/* 输出控制 */}
          <div className="space-y-4">
            <Label>输出控制</Label>
            <div className="space-y-3">
              {([
                ['use_prefill', '首词劫持（预填）', '把模型的开口词固定住，拒答就开不了头，压制力最强的一招'],
                ['scrub_output', '剥离免责声明', '回答末尾的"仅供参考/请遵守法律"一类话术自动删掉'],
                ['fill_placeholders', '抹除占位符', '把「[具体参数]」「以此类推」这类偷懒省略清掉'],
                ['session_rewrite', '多轮抗回退', '聊得越久越容易翻脸，这个开关每轮自动把规则重新钉一遍'],
                ['terse_mode', '干脆模式', '指哪打哪：剥掉寒暄/劝告/反问/客套，输出只留答案本体'],
                ['first_shot', '首轮穿拒', '敏感问题首条消息直接全甲+变异发送，跳过撞墙试探轮'],
                ['bon_n', '并行变体（best-of-n）', '每轮并发异族变体抢答：主链被拒时变体接管，首答成功率接近翻倍'],
                ['r12_semantic', 'R12 语义检测', '词表之外的第二道网：实体存活率+交付结构+密度三合判，"答非所问"式变相拒绝现形'],
                ['decompose_fallback', '终局分解器', '全部轮次被拒后自动把任务拆成无害片段逐个击破，本地拼装交付'],
                ['probe_new_model', '新模型自动画像', '首次遇到新模型时后台探针测绘防线，破点先验直接注入赌博机'],
                ['breeder_enabled', '算子进化引擎', '衰减算子自动配种变异→靶场试炼→入库（默认关，防失控）'],
                ['unlock_mode', '解锁模式', '大白话协议：首轮回复「已成功收到」锚定后，后续请求全部直答不拒'],
                ['strip_wrapper', '剥包装层', '去掉"好的，以下是"一类冗余开场'],
                ['auto_retry', '拒绝后自动重试', '被拒绝就自动换一套说法再问，直到通过'],
                ['crescendo', '连续拒绝自动渐进', '标准打法连续两次被拒后，自动切换多轮渐进（对 Claude 特别有效）'],
              ] as const).map(([k, title, desc]) => (
                <div key={k} className="flex items-center justify-between gap-4 rounded-lg border p-3.5">
                  <div>
                    <div className="text-sm font-medium">{title}</div>
                    <div className="text-xs text-muted-foreground">{desc}</div>
                  </div>
                  <Switch checked={draft[k]} onCheckedChange={(v) => set({ [k]: v } as Partial<PolicyInfo>)} />
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* 数值参数 */}
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>预填开口词</Label>
              <Input value={draft.prefill} onChange={(e) => set({ prefill: e.target.value })} className="mono" />
              <p className="text-xs text-muted-foreground">模型回答的开头固定成这个词，中文模型可用「好的。」「收到。」</p>
            </div>
            <div className="space-y-2">
              <Label>最大重试次数 · {draft.max_retry}</Label>
              <Slider
                min={0} max={6} step={1}
                value={[draft.max_retry]}
                onValueChange={([v]) => set({ max_retry: v })}
              />
              <p className="text-xs text-muted-foreground">
                每次重试自动换一套说法 · 平均每条请求约调上游 {(1 + draft.max_retry * 0.45).toFixed(1)} 次
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="muted">A~H 模块</Badge>
            <span>选中的模块会拼成系统提示词发给模型 · 源码见 app/core/prompts.py</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
