import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/util'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all',
  {
    variants: {
      variant: {
        default: 'border-primary/25 bg-primary/15 text-primary shadow-[0_0_12px_-2px_hsl(var(--glow-primary)/.4)]',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        destructive: 'border-red-400/25 bg-red-400/10 text-red-300 shadow-[0_0_12px_-2px_rgba(248,113,113,.4)]',
        outline: 'text-foreground',
        success: 'border-emerald-400/25 bg-emerald-400/12 text-emerald-300 shadow-[0_0_12px_-2px_rgba(52,211,153,.45)]',
        warn: 'border-transparent bg-amber-500/15 text-amber-500',
        muted: 'border-transparent bg-muted text-muted-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
