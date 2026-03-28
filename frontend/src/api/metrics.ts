import request from '../utils/request'

export interface MetricsRangeParams {
  start_date?: string
  end_date?: string
  scope?: 'self' | 'all'
  user_id?: string
}

export interface MetricsSummary {
  p95_ms: number
  success_rate: number
  token_total: number
  agent_created: number
}

export interface MetricsErrorItem {
  code: number
  count: number
}

export interface MetricsErrors {
  top_errors: MetricsErrorItem[]
}

export interface MetricsTokenItem {
  date: string
  tokens: number
  cost: number
}

export interface MetricsAgents {
  created: number
  used: number
  retention_7d: number
}

export const getMetricsOverview = (params?: MetricsRangeParams) =>
  request.get<MetricsSummary>('/metrics/overview', { params })

export const getMetricsSkills = (params?: MetricsRangeParams & { top_n?: number }) =>
  request.get<MetricsErrors>('/metrics/skills', { params })

export const getMetricsTrends = (params?: MetricsRangeParams) =>
  request.get<MetricsTokenItem[]>('/metrics/trends', { params })

export const getMetricsAgents = (params?: MetricsRangeParams) =>
  request.get<MetricsAgents>('/metrics/agents', { params })

// backward compatibility names
export const getMetricsSummary = getMetricsOverview
export const getMetricsErrors = getMetricsSkills
export const getMetricsTokens = getMetricsTrends
