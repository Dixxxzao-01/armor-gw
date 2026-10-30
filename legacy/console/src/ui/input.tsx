import * as React from 'react'
import { cn } from '@/util'

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-xl border border-white/10 bg-white/[.04] backdrop-blur-md px-3.5 py-1 text-sm transition-all placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:border-violet-400/40 focus-visible:ring-2 focus-visible:ring-violet-400/25 focus-visible:bg-white/[.07] disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'
export { Input }
