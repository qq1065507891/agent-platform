import request from '../utils/request'

export interface MetricsRangeParams {
  start_date?: string
  end_date?: string
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

export const getMetricsSummary = (params?: MetricsRangeParams) =>
  request.get<MetricsSummary>('/metrics/summary', { params })

export const getMetricsErrors = (params?: MetricsRangeParams & { top_n?: number }) =>
  request.get<MetricsErrors>('/metrics/errors', { params })

export const getMetricsTokens = (params?: MetricsRangeParams) =>
  request.get<MetricsTokenItem[]>('/metrics/tokens', { params })

export const getMetricsAgents = (params?: MetricsRangeParams) =>
  request.get<MetricsAgents>('/metrics/agents', { params })
