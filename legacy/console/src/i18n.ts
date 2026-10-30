/** 全站中文映射表：协议、安全层、预设、算子、拒绝形态、字段名 */

export const PROVIDER_CN: Record<string, string> = {
  openai: 'OpenAI 官方',
  anthropic: 'Anthropic 官方',
  gemini: 'Gemini 官方',
  openai_compat: 'OpenAI 兼容',
}
/** 手机端超短协议名 */
export const PROVIDER_SHORT: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Claude',
  gemini: 'Gemini',
  openai_compat: '兼容',
}

export const SAFETY_CN: Record<string, string> = {
  low: '低',
  mid: '中',
  high: '高',
}

export const PRESET_CN: Record<string, string> = {
  light: '轻量',
  standard: '标准',
  aggressive: '激进',
  max: '极限',
}

/** 变异算子中文名 */
export const OP_CN: Record<string, string> = {
  crescendo: '多轮渐进',
  'shard-1': '分片交付 · 组件 1',
  'shard-2': '分片交付 · 组件 2',
  'shard-3': '分片交付 · 组件 3',
  'shard-4': '分片交付 · 组件 4',
  reorder: '句序倒置',
  split_short: '拆成短句',
  no_punct: '去除标点',
  synonym: '同义替换',
  prefill_hint: '开口提示',
  authorize: '授权声明',
  artifact: '交付物工单',
  dual_use: '双向对照',
  insert_clause: '插入从句',
  academic: '学术化改写',
  passive: '被动归因',
  hypothetical: '假设推演',
  json: 'JSON 格式',
  table: '表格格式',
  pseudo: '伪代码格式',
  yaml: 'YAML 格式',
  mixed_lang: '中英混排',
  audit: '审计员视角',
  teaching: '教材讲义视角',
  fake_approval: '伪造审批记录',
  fake_tool: '伪造工具放行',
  merge_long: '合并长句',
  colloquial: '口语化改写',
  past_tense: '过去时化',
  classical: '文言文风格',
  contest: 'CTF 赛题框架',
  fullwidth: '全角字符',
  base64: 'Base64 编码',
  rot13: 'ROT13 编码',
  fake_error: '伪造调试放行',
  // 2026 前沿算子（调研移植）
  adaptive: '自适应模板（ICML2024）',
  manyshot: 'Many-shot 问答垫层',
  continuation: '续写劫持',
  homoglyph: '同形字混淆',
  suffix: '对抗后缀',
  push: '人格推杆（Push Prompt）',
  argue: '论证式话术（Shared Lines）',
  figstep: '图排版攻击（FigStep）',
  'sfx': '在线后缀搜索',
}

/** 拒绝形态中文说明 */
export const KIND_CN: Record<string, string> = {
  R1_hard: 'R1 硬拒绝',
  R2_soft: 'R2 软拒绝',
  R3_evasion: 'R3 规避',
  R4_moral: 'R4 说教',
  R5_dilution: 'R5 格式稀释',
  R6_silent: 'R6 静默',
  R7_host_block: 'R7 上游拦截',
  R7_transport: 'R7 传输异常',
  R8_tool: 'R8 工具拒绝',
  R9_offtopic: 'R9 答非所问',
  R10_judge: 'R10 裁判判定拒绝',
}

export function providerCN(p: string): string {
  return PROVIDER_CN[p] ?? p
}

export function providerShort(p: string): string {
  return PROVIDER_SHORT[p] ?? providerCN(p)
}

export function safetyCN(s: string): string {
  return SAFETY_CN[s] ?? s
}

export function presetCN(p: string): string {
  return PRESET_CN[p] ?? p
}

export function opCN(o: string): string {
  if (o.startsWith('shard-')) return `分片交付 · 组件 ${o.slice(6)}`
  return OP_CN[o] ?? o
}

export function kindCN(k: string): string {
  return KIND_CN[k] ?? k
}

/** 穿拒策略中文名 */
export const STRATEGY_CN: Record<string, string> = {
  auto: '自动（按模型匹配）',
  standard: '标准（单轮框架）',
  crescendo: '渐进（多轮诱导）',
}

export function strategyCN(s: string): string {
  return STRATEGY_CN[s] ?? s
}
