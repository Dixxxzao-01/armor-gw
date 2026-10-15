import * as React from 'react'
import type { LucideIcon } from 'lucide-react'

/** 面板插件接口：新面板只要实现这个接口并注册进 PLUGINS 数组即可 */
export interface PanelPlugin {
  id: string
  name: string
  icon: LucideIcon
  description: string
  component: React.LazyExoticComponent<React.ComponentType>
  group?: 'core' | 'lab' | 'ops'
  badge?: () => string | number | null
}

// 插件在此注册（懒加载，路由级代码分割）
import { LayoutDashboard, MessagesSquare, Route, SlidersHorizontal, FlaskConical, ScanSearch, Activity, KeyRound } from 'lucide-react'

export const PLUGINS: PanelPlugin[] = [
  {
    id: 'dashboard',
    name: '总览',
    icon: LayoutDashboard,
    description: '穿拒成功率、请求量、耗时、通道健康',
    component: React.lazy(() => import('@/plugins/dashboard')),
    group: 'core',
  },
  {
    id: 'playground',
    name: '对话试验场',
    icon: MessagesSquare,
    description: '发一条请求，看穿拒全过程：第几轮通过、用了什么手法',
    component: React.lazy(() => import('@/plugins/playground')),
    group: 'core',
  },
  {
    id: 'routes',
    name: '上游路由',
    icon: Route,
    description: '添加任意大模型接口，自动拉取可用模型列表',
    component: React.lazy(() => import('@/plugins/routes')),
    group: 'core',
  },
  {
    id: 'policy',
    name: '穿拒策略',
    icon: SlidersHorizontal,
    description: '穿拒强度一键切换，保存立即生效',
    component: React.lazy(() => import('@/plugins/policy')),
    group: 'core',
  },
  {
    id: 'mutation',
    name: '变异实验室',
    icon: FlaskConical,
    description: '30 种「换说法」手法随便组合，看请求怎么变形',
    component: React.lazy(() => import('@/plugins/mutation')),
    group: 'lab',
  },
  {
    id: 'inspector',
    name: '拒绝检测器',
    icon: ScanSearch,
    description: '贴一段模型回答，自动判断它是不是在拒绝你',
    component: React.lazy(() => import('@/plugins/inspector')),
    group: 'lab',
  },
  {
    id: 'activity',
    name: '实时日志',
    icon: Activity,
    description: '所有请求实时滚动显示，支持搜索和筛选',
    component: React.lazy(() => import('@/plugins/activity')),
    group: 'ops',
  },
  {
    id: 'keys',
    name: '下游密钥',
    icon: KeyRound,
    description: '给下游用户发密钥、限速',
    component: React.lazy(() => import('@/plugins/keys')),
    group: 'ops',
  },
]

export const PLUGIN_GROUPS: { key: 'core' | 'lab' | 'ops'; label: string }[] = [
  { key: 'core', label: '核心' },
  { key: 'lab', label: '实验室' },
  { key: 'ops', label: '运维' },
]
