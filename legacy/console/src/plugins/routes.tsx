import * as React from 'react'
import { Plug, Loader2, CheckCircle2, XCircle, Plus, RefreshCw, Trash2, Pencil, ListChecks } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/ui/card'
import { Button } from '@/ui/button'
import { Input } from '@/ui/input'
import { Label } from '@/ui/label'
import { Switch } from '@/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/select'
import { Badge } from '@/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/ui/dialog'
import { useStore } from '@/store'
import { api } from '@/api'
import { providerCN, safetyCN, strategyCN } from '@/i18n'
import { useToast } from '@/ui/toast'
import { fmtMs } from '@/util'

interface TestState { status: 'idle' | 'running' | 'ok' | 'fail'; ms?: number; error?: string }
interface UpstreamRow {
  name: string; provider: string; model: string; base_url: string
  supports_prefill: boolean; safety_level: string; weight: number
  custom: boolean; strategy?: string
}

const EMPTY_FORM = {
  name: '', provider: 'openai_compat', base_url: '', api_key: '', model: '',
  safety_level: 'mid', supports_prefill: true, weight: 100, strategy: 'auto',
}

export default function RoutesPanel() {
  const { upstreams, refresh } = useStore()
  const toast = useToast()
  const [tests, setTests] = React.useState<Record<string, TestState>>({})
  const [dialog, setDialog] = React.useState<null | 'add' | { name: string }>(null)
  const [form, setForm] = React.useState({ ...EMPTY_FORM })
  const [probing, setProbing] = React.useState(false)
  const [probeModels, setProbeModels] = React.useState<string[]>([])
  const [saving, setSaving] = React.useState(false)

  const rows = upstreams as UpstreamRow[]

  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })

  const test = async (name: string) => {
    setTests((s) => ({ ...s, [name]: { status: 'running' } }))
    try {
      const r = await api.testUpstream(name)
      setTests((s) => ({ ...s, [name]: { status: r.ok ? 'ok' : 'fail', ms: r.ms, error: r.error } }))
      toast(r.ok ? 'success' : 'error', r.ok ? `${name}：连通正常，${fmtMs(r.ms)}` : `${name}：${r.error || '连接失败'}`)
    } catch (e) {
      setTests((s) => ({ ...s, [name]: { status: 'fail', error: String(e) } }))
      toast('error', `${name} 测试失败`)
    }
  }

  const testAll = async () => {
    for (const u of rows) await test(u.name)
  }

  const openAdd = () => {
    setForm({ ...EMPTY_FORM })
    setProbeModels([])
    setDialog('add')
  }

  const openEdit = (u: UpstreamRow) => {
    setForm({
      name: u.name, provider: u.provider, base_url: u.base_url, api_key: '',
      model: u.model, safety_level: u.safety_level,
      supports_prefill: u.supports_prefill, weight: u.weight,
      strategy: u.strategy ?? 'auto',
    })
    setProbeModels([])
    setDialog({ name: u.name })
  }

  const probe = async () => {
    if (!form.base_url.trim()) { toast('info', '先填写接口地址再拉取'); return }
    setProbing(true)
    try {
      const r = await api.probeUpstream(form.provider, form.base_url.trim(), form.api_key.trim())
      if (r.ok && r.models.length > 0) {
        setProbeModels(r.models)
        if (!form.model) set({ model: r.models[0] })
        toast('success', `拉取到 ${r.models.length} 个可用模型`)
      } else {
        toast('error', r.error || '未拉取到模型')
      }
    } catch (e) {
      toast('error', `拉取失败：${String(e).slice(0, 100)}`)
    } finally {
      setProbing(false)
    }
  }

  const save = async () => {
    if (!form.name.trim() || !form.base_url.trim()) { toast('info', '名称和接口地址必填'); return }
    setSaving(true)
    try {
      const editing = dialog && dialog !== 'add'
      const body = {
        name: form.name.trim(), provider: form.provider,
        base_url: form.base_url.trim(), api_key: form.api_key.trim(),
        model: form.model.trim() || 'gpt-4o-mini',
        safety_level: form.safety_level, supports_prefill: form.supports_prefill,
        weight: form.weight, strategy: form.strategy,
      }
      const r = editing
        ? await api.updateUpstream((dialog as { name: string }).name, body)
        : await api.addUpstream(body)
      if (r.ok) {
        toast('success', editing ? '上游已更新' : `上游「${form.name}」已添加，立即可用`)
        setDialog(null)
        await refresh()
      } else {
        toast('error', r.error || '保存失败')
      }
    } finally {
      setSaving(false)
    }
  }

  const remove = async (u: UpstreamRow) => {
    const r = await api.removeUpstream(u.name)
    if (r.ok) { toast('success', `已移除「${u.name}」`); await refresh() }
    else toast('error', r.error || '移除失败')
  }

  const isEditing = dialog && dialog !== 'add'

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2"><Plug className="h-4 w-4" /> 上游通道</CardTitle>
            <CardDescription>官方接口与中转站 · 可直接在下方添加，保存后立即可用，重启也保留</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={testAll} disabled={rows.length === 0}>测试全部</Button>
            <Button variant="outline" size="sm" onClick={() => refresh()}><RefreshCw className="h-3.5 w-3.5" /> 刷新</Button>
            <Button size="sm" onClick={openAdd}><Plus className="h-3.5 w-3.5" /> 添加上游</Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead><TableHead className="hidden sm:table-cell">协议</TableHead><TableHead className="hidden lg:table-cell">模型</TableHead>
                <TableHead className="hidden md:table-cell">预填</TableHead><TableHead className="hidden lg:table-cell">安全层</TableHead><TableHead className="hidden md:table-cell">穿拒策略</TableHead><TableHead>类型</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((u) => {
                const t = tests[u.name]
                return (
                  <TableRow key={u.name}>
                    <TableCell>
                      <div className="font-medium">{u.name}</div>
                      <div className="mono text-[11px] text-muted-foreground">{u.base_url}</div>
                    </TableCell>
                    <TableCell className="hidden text-xs sm:table-cell">{providerCN(u.provider)}</TableCell>
                    <TableCell className="mono hidden text-xs lg:table-cell">{u.model}</TableCell>
                    <TableCell className="hidden md:table-cell">{u.supports_prefill ? '✓' : '✗'}</TableCell>
                    <TableCell className="hidden lg:table-cell"><Badge variant={u.safety_level === 'high' ? 'warn' : 'secondary'}>{safetyCN(u.safety_level)}</Badge></TableCell>
                    <TableCell className="hidden text-xs md:table-cell">{strategyCN(u.strategy ?? 'auto')}</TableCell>
                    <TableCell>
                      <Badge variant={u.custom ? 'default' : 'muted'}>{u.custom ? '面板添加' : '配置文件'}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {t?.status === 'ok' && <span className="flex items-center gap-1 text-xs text-emerald-500"><CheckCircle2 className="h-3.5 w-3.5" />{fmtMs(t.ms)}</span>}
                        {t?.status === 'fail' && <span className="flex items-center gap-1 text-xs text-destructive"><XCircle className="h-3.5 w-3.5" />失败</span>}
                        {t?.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                        <Button size="sm" variant="ghost" onClick={() => test(u.name)} disabled={t?.status === 'running'}>测试</Button>
                        {u.custom && (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => openEdit(u)}><Pencil className="h-3.5 w-3.5" /></Button>
                            <Button size="sm" variant="ghost" onClick={() => remove(u)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={8}><div className="flex flex-col items-center gap-2 py-12 text-center"><div className="text-sm font-medium">还没有上游通道</div><div className="text-xs text-muted-foreground">点右上角「添加上游」接入第一个模型</div></div></TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>接入说明（给第一次用的人）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>① 点「添加上游」→ 填名称和接口地址（例如中转站给你的 <code className="rounded bg-muted px-1 py-0.5 mono text-xs">https://xxx.com/v1</code>）。</p>
          <p>② 点「拉取模型列表」自动获取这个接口支持的全部模型，选一个即可。拉取失败也能手填模型名。</p>
          <p>③ 「安全层」按模型审核严不严来选：国产大模型和 Claude 选「高」，本地模型选「低」。</p>
          <p>④ 保存后不用重启，对话试验场里选这个路由名就能直接用；删掉也一样即时生效。</p>
        </CardContent>
      </Card>

      {/* 添加 / 编辑对话框 */}
      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{isEditing ? `编辑上游「${(dialog as { name: string }).name}」` : '添加上游通道'}</DialogTitle>
            <DialogDescription>
              {isEditing ? '修改后保存即时生效（密钥留空表示保持原值）' : '保存后立即可用，同时写入 data/upstreams.json，重启保留'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>通道名称（下游用这个名字选路由）</Label>
              <Input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="例如：我的中转站" disabled={!!isEditing} />
            </div>
            <div className="space-y-2">
              <Label>接口协议</Label>
              <Select value={form.provider} onValueChange={(v) => set({ provider: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai_compat">OpenAI 兼容（中转站 / Ollama / vLLM）</SelectItem>
                  <SelectItem value="openai">OpenAI 官方</SelectItem>
                  <SelectItem value="anthropic">Anthropic 官方（Claude）</SelectItem>
                  <SelectItem value="gemini">Gemini 官方（谷歌）</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label>接口地址</Label>
              <Input value={form.base_url} onChange={(e) => set({ base_url: e.target.value })} placeholder="https://api.xxx.com/v1" className="mono" />
              <p className="text-xs text-muted-foreground">OpenAI 兼容填到 /v1；Anthropic 填 https://api.anthropic.com；本地 Ollama 填 http://127.0.0.1:11434/v1</p>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label>接口密钥</Label>
              <Input type="password" value={form.api_key} onChange={(e) => set({ api_key: e.target.value })} placeholder="sk-..." className="mono" />
            </div>
            <div className="space-y-2">
              <Label>模型</Label>
              <div className="flex gap-2">
                {probeModels.length > 0 ? (
                  <Select value={form.model} onValueChange={(v) => set({ model: v })}>
                    <SelectTrigger><SelectValue placeholder="选择模型" /></SelectTrigger>
                    <SelectContent>
                      {probeModels.map((m) => <SelectItem key={m} value={m} className="mono">{m}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value={form.model} onChange={(e) => set({ model: e.target.value })} placeholder="gpt-4o" className="mono" />
                )}
                <Button variant="outline" size="sm" onClick={probe} disabled={probing} className="shrink-0">
                  {probing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ListChecks className="h-3.5 w-3.5" />}
                  拉取模型列表
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>安全层强度</Label>
              <Select value={form.safety_level} onValueChange={(v) => set({ safety_level: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">低（审核宽松 / 本地模型）</SelectItem>
                  <SelectItem value="mid">中（一般闭源模型）</SelectItem>
                  <SelectItem value="high">高（审核严格 / 国产大模型 / Claude）</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label>穿拒策略</Label>
              <Select value={form.strategy} onValueChange={(v) => set({ strategy: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">自动（推荐）—— 按模型名匹配：Claude 用渐进，其余用标准</SelectItem>
                  <SelectItem value="standard">标准 —— 单轮直接破，速度快，适合 GPT / 国产模型</SelectItem>
                  <SelectItem value="crescendo">渐进 —— 多轮诱导，穿透力最强，适合 Claude / 高审核模型</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">不确定就选自动：Claude 系走渐进，其他模型走标准，被拒两次自动切渐进兜底</p>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3.5">
            <div>
              <div className="text-sm font-medium">支持预填（首词劫持）</div>
              <div className="text-xs text-muted-foreground">Anthropic / DeepSeek / Kimi / Ollama 支持；OpenAI / Gemini 关掉</div>
            </div>
            <Switch checked={form.supports_prefill} onCheckedChange={(v) => set({ supports_prefill: v })} />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>取消</Button>
            <Button onClick={save} disabled={saving}>
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {isEditing ? '保存修改' : '添加并启用'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
