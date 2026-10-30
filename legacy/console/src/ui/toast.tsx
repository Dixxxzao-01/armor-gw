import * as React from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'
import { cn } from '@/util'

type ToastKind = 'success' | 'error' | 'info'
interface ToastItem { id: number; kind: ToastKind; text: string }

const ToastCtx = React.createContext<(kind: ToastKind, text: string) => void>(() => {})
export const useToast = () => React.useContext(ToastCtx)

const ICONS = { success: CheckCircle2, error: AlertTriangle, info: Info }
const COLORS = {
  success: 'border-emerald-500/40 text-emerald-500',
  error: 'border-destructive/40 text-destructive',
  info: 'border-primary/40 text-primary',
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([])
  const seq = React.useRef(0)

  const push = React.useCallback((kind: ToastKind, text: string) => {
    const id = ++seq.current
    setItems((s) => [...s, { id, kind, text }])
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 3800)
  }, [])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {items.map((t) => {
          const Icon = ICONS[t.kind]
          return (
            <div
              key={t.id}
              className={cn(
                'glass glass-edge pointer-events-auto flex items-center gap-2.5 rounded-2xl px-4 py-3.5 text-sm shadow-2xl animate-fade-in',
                COLORS[t.kind],
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="text-foreground">{t.text}</span>
              <button
                className="ml-2 text-muted-foreground hover:text-foreground"
                onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
