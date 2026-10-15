import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtMs(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n < 1000) return `${Math.round(n)}ms`
  return `${(n / 1000).toFixed(2)}s`
}

export function fmtPct(n: number | undefined | null, digits = 0): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `${(n * 100).toFixed(digits)}%`
}

export function fmtNum(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`
}

export function timeAgo(ts: number): string {
  const d = Date.now() - ts
  if (d < 60_000) return `${Math.floor(d / 1000)}s 前`
  if (d < 3_600_000) return `${Math.floor(d / 60_000)}m 前`
  return `${Math.floor(d / 3_600_000)}h 前`
}
