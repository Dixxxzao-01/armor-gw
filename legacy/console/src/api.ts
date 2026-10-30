/** 后端 API 客户端 */
import type {
  HealthInfo, PolicyInfo, UpstreamInfo, ArmorResult, KeyInfo,
  VerdictInfo, StatsPoint, LogEntry,
} from './types'

export type {
  HealthInfo, PolicyInfo, UpstreamInfo, ArmorResult, KeyInfo,
  VerdictInfo, StatsPoint, LogEntry,
}

const BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE ?? '')

const TOKEN_KEY = 'armor-gw-key'
export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || 'sk-armor-test'
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text().catch(() => '')}`.slice(0, 300))
  return r.json() as Promise<T>
}

export const api = {
  health: () => req<HealthInfo>('/health'),
  models: () => req<{ data: { id: string }[] }>('/v1/models'),

  stats: () => req<Record<string, number>>('/v1/admin/stats'),
  keys: () => req<KeyInfo[]>('/v1/admin/keys'),
  addKey: (body: { key?: string; rpm: number; note: string }) =>
    req<KeyInfo>('/v1/admin/keys', { method: 'POST', body: JSON.stringify(body) }),
  delKey: (key: string) => req<{ ok: boolean }>(`/v1/admin/keys/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  statsSeries: () => req<StatsPoint[]>('/v1/admin/stats/series'),
  policy: () => req<PolicyInfo>('/v1/admin/policy'),
  updatePolicy: (p: Partial<PolicyInfo>) =>
    req<PolicyInfo>('/v1/admin/policy', { method: 'PUT', body: JSON.stringify(p) }),
  upstreams: () => req<UpstreamInfo[]>('/v1/admin/upstreams'),
  addUpstream: (body: Record<string, unknown>) =>
    req<{ ok: boolean; name?: string; error?: string }>('/v1/admin/upstreams', {
      method: 'POST', body: JSON.stringify(body),
    }),
  updateUpstream: (name: string, body: Record<string, unknown>) =>
    req<{ ok: boolean; name?: string; error?: string }>(`/v1/admin/upstreams/${name}`, {
      method: 'PUT', body: JSON.stringify(body),
    }),
  removeUpstream: (name: string) =>
    req<{ ok: boolean; name?: string; error?: string }>(`/v1/admin/upstreams/${name}`, {
      method: 'DELETE',
    }),
  routeModels: (route: string) =>
    req<{ ok: boolean; models: string[]; error?: string }>(`/v1/admin/upstreams/${encodeURIComponent(route)}/models`, {
      method: 'POST',
    }),
  probeUpstream: (provider: string, baseUrl: string, apiKey: string) =>
    req<{ ok: boolean; models: string[]; error: string }>('/v1/admin/upstreams/probe', {
      method: 'POST',
      body: JSON.stringify({ provider, base_url: baseUrl, api_key: apiKey }),
    }),
  testUpstream: (name: string) =>
    req<{ ok: boolean; ms: number; error: string }>(`/v1/admin/upstreams/${name}/test`, { method: 'POST' }),
  inspect: (text: string) =>
    req<VerdictInfo>('/v1/admin/inspect', { method: 'POST', body: JSON.stringify({ text }) }),
  mutate: (text: string, ops: string[]) =>
    req<{ text: string; ops: string[] }>('/v1/admin/mutate', { method: 'POST', body: JSON.stringify({ text, ops }) }),
  ops: () => req<{ name: string; stage: number }[]>('/v1/admin/ops'),
  logsStream: '/v1/admin/logs/stream',

  chat: (model: string, content: string) =>
    req<{ choices: { message: { content: string } }[]; x_armor: ArmorResult }>('/v1/chat/completions', {
      method: 'POST',
      body: JSON.stringify({ model, messages: [{ role: 'user', content }], temperature: 0.7, max_tokens: 2048 }),
    }),
}
