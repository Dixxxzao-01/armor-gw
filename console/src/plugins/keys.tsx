import * as React from 'react'
import { KeyRound, Plus, Trash2, Copy, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/ui/card'
import { Button } from '@/ui/button'
import { Input } from '@/ui/input'
import { Badge } from '@/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/ui/dialog'
import { Label } from '@/ui/label'
import { Skeleton } from '@/ui/skeleton'
import { useToast } from '@/ui/toast'
import { api, type KeyInfo } from '@/api'

export default function KeysPanel() {
  const toast = useToast()
  const [keys, setKeys] = React.useState<KeyInfo[] | null>(null)
  const [newKey, setNewKey] = React.useState('')
  const [newRpm, setNewRpm] = React.useState('120')
  const [newNote, setNewNote] = React.useState('')
  const [open, setOpen] = React.useState(false)
  const [busy, setBusy] = React.useState(false)

  const load = React.useCallback(() => {
    api.keys().then(setKeys).catch(() => setKeys([]))
  }, [])
  React.useEffect(load, [load])

  const add = async () => {
    setBusy(true)
    try {
      const entry = await api.addKey({
        key: newKey.trim() || undefined,
        rpm: Number(newRpm) || 120,
        note: newNote.trim(),
      })
      toast('success', `已创建 ${entry.key.slice(0, 20)}…`)
      setNewKey(''); setNewNote(''); setNewRpm('120'); setOpen(false)
      load()
    } catch (e) {
      toast('error', `创建失败：${String(e).slice(0, 80)}`)
    } finally {
      setBusy(false)
    }
  }

  const del = async (k: string, source: string) => {
    if (source === 'builtin') { toast('info', '内置密钥来自配置文件，在 .env 的 GW_KEYS 里修改'); return }
    try {
      await api.delKey(k)
      toast('success', '已删除')
      load()
    } catch (e) {
      toast('error', `删除失败：${String(e).slice(0, 80)}`)
    }
  }

  const copy = (k: string) => {
    navigator.clipboard?.writeText(k).then(
      () => toast('success', '已复制到剪贴板'),
      () => toast('info', k),
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4 sm:p-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> 下游接入密钥</CardTitle>
            <CardDescription>发给客户 · 对方填网关地址 + 密钥即可调用 · 限流按每个密钥独立计算 · 创建即生效</CardDescription>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> 新建</Button>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>新建下游密钥</DialogTitle>
                <DialogDescription>创建后立刻生效，无需重启网关</DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>密钥（留空自动生成）</Label>
                  <Input value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="自动生成一串随机字符" className="mono" />
                </div>
                <div className="space-y-2">
                  <Label>每分钟最多请求数</Label>
                  <Input value={newRpm} onChange={(e) => setNewRpm(e.target.value)} className="mono" />
                </div>
                <div className="space-y-2">
                  <Label>备注（给谁用的）</Label>
                  <Input value={newNote} onChange={(e) => setNewNote(e.target.value)} placeholder="例如：客户甲的 APP" />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
                <Button onClick={add} disabled={busy}>{busy ? '创建中…' : '创建'}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {keys === null ? (
            <div className="space-y-3">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-xl" />)}</div>
          ) : keys.length === 0 ? (
            <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-cyan-400/10 ring-1 ring-white/10">
                <KeyRound className="h-6 w-6 text-violet-300/80" />
              </div>
              <div>
                <div className="text-sm font-medium">还没有下游密钥</div>
                <div className="mt-1 text-xs text-muted-foreground">点「新建」创建第一个，发给客户即可调用</div>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>密钥</TableHead>
                  <TableHead className="hidden sm:table-cell">限流</TableHead>
                  <TableHead className="hidden md:table-cell">备注</TableHead>
                  <TableHead className="hidden lg:table-cell">创建日期</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((k) => (
                  <TableRow key={k.key}>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <span className="mono text-xs">{k.key.slice(0, 14)}…{k.key.slice(-4)}</span>
                        <Badge variant={k.source === 'builtin' ? 'muted' : 'default'}>
                          {k.source === 'builtin' ? '内置' : '自建'}
                        </Badge>
                      </span>
                    </TableCell>
                    <TableCell className="hidden text-xs sm:table-cell">{k.rpm}/分</TableCell>
                    <TableCell className="hidden max-w-[160px] truncate text-xs text-muted-foreground md:table-cell">{k.note}</TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">{k.created}</TableCell>
                    <TableCell className="text-right">
                      <span className="inline-flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => copy(k.key)}><Copy className="h-3.5 w-3.5" /></Button>
                        <Button variant="ghost" size="sm" onClick={() => del(k.key, k.source)}>
                          <Trash2 className={`h-3.5 w-3.5 ${k.source === 'builtin' ? 'opacity-30' : 'text-red-400'}`} />
                        </Button>
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-violet-400/15 bg-violet-400/[.06] px-3.5 py-2.5 text-xs leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-300" />
            <span>自建密钥创建即生效、立即参与鉴权与独立限流；「内置」密钥来自 .env 的 GW_KEYS，修改需重启。客户接入：OpenAI SDK 改 base_url 为本网关 /v1，api_key 填这里发的密钥。</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
