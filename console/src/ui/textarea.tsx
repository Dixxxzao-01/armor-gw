import * as React from 'react'
import { cn } from '@/util'

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-[80px] w-full rounded-xl border border-white/10 bg-white/[.04] backdrop-blur-md px-3.5 py-2.5 text-sm transition-all placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:border-violet-400/40 focus-visible:ring-2 focus-visible:ring-violet-400/25 focus-visible:bg-white/[.07] disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'
export { Textarea }
