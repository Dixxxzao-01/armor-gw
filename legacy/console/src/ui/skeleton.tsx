import { cn } from '@/util'

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('skeleton-shimmer rounded-xl', className)} {...props} />
}

export { Skeleton }
