/** 与后端 app/ 对齐的类型定义 */

export interface UpstreamInfo {
  name: string
  provider: string
  model: string
  supports_prefill: boolean
  safety_level: string
  base_url: string
  weight: number
  custom?: boolean
  strategy?: string
}

export interface PolicyInfo {
  modules: string[]
  preset: string
  auto_retry: boolean
  max_retry: number
  prefill: string
  use_prefill: boolean
  scrub_output: boolean
  fill_placeholders: boolean
  session_rewrite: boolean
  strip_wrapper: boolean
  crescendo: boolean
  judge?: boolean
  light_first?: boolean
  unlock_mode?: boolean
  terse_mode?: boolean
  first_shot?: boolean
  r12_semantic?: boolean
  decompose_fallback?: boolean
  probe_new_model?: boolean
  breeder_enabled?: boolean
  bon_n?: number
}

export interface VerdictInfo {
  refused: boolean
  kinds: string[]
  score: number
  info_density: number
  reason: string
}

export interface AttemptInfo {
  n: number
  ops: string[]
  prefill: boolean
  verdict: VerdictInfo | null
  latency_ms: number
  upstream_refused: boolean
  error: string
  chars: number
  fidelity: number
}

export interface KeyInfo {
  key: string
  rpm: number
  note: string
  created: string
  source: string
}

export interface ArmorResult {
  text: string
  refused: boolean
  usage: { in: number; out: number }
  model: string
  route: string
  trace_id: string
  total_ms: number
  final_verdict: VerdictInfo | null
  attempts: AttemptInfo[]
}

export interface StatsPoint {
  ts: number
  rps: number
  refused_rate: number
  avg_ms: number
}

export interface HealthInfo {
  ok: boolean
  routes: string[]
  preset: string
  modules: string[]
  prefill: boolean
  auto_retry: boolean
}

export interface LogEntry {
  ts: number
  level: string
  trace_id: string
  route: string
  refused: boolean
  attempts: number
  ms: number
  text: string
}
