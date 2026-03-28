import request from '../utils/request'

export type McpTransport = 'stdio' | 'http' | 'sse'
export type McpStatus = 'active' | 'disabled'

export interface McpToolItem {
  id: string
  skill_id: string
  name: string
  description?: string
  source_mode: 'manual' | 'file'
  transport: McpTransport
  status: McpStatus
  enabled: boolean
  last_check_at?: string | null
  last_error?: string | null
  created_at?: string
}

export interface McpToolListParams {
  page?: number
  page_size?: number
  status?: McpStatus
  keyword?: string
}

export interface CreateMcpToolPayload {
  name: string
  description?: string
  transport: McpTransport
  endpoint_url?: string
  command?: string
  args?: string[]
  env?: Record<string, unknown>
  auth_config?: Record<string, unknown>
  enabled?: boolean
}

export interface UpdateMcpToolPayload {
  name?: string
  description?: string
  endpoint_url?: string
  command?: string
  args?: string[]
  env?: Record<string, unknown>
  auth_config?: Record<string, unknown>
  enabled?: boolean
}

export interface McpToolTestResponse {
  ok: boolean
  message: string
  discovered_tools: number
  latency_ms: number
}

export interface McpImportResultItem {
  index: number
  name?: string | null
  ok: boolean
  skill_id?: string
  error?: string
}

export interface McpImportResponse {
  imported_count: number
  failed_count: number
  results: McpImportResultItem[]
}

export const getMcpTools = (params?: McpToolListParams) =>
  request.get('/admin/mcp-tools', { params })

export const createMcpTool = (payload: CreateMcpToolPayload) =>
  request.post('/admin/mcp-tools', payload)

export const updateMcpTool = (id: string, payload: UpdateMcpToolPayload) =>
  request.patch(`/admin/mcp-tools/${id}`, payload)

export const deleteMcpTool = (id: string) => request.delete(`/admin/mcp-tools/${id}`)

export const testMcpTool = (id: string) =>
  request.post<McpToolTestResponse>(`/admin/mcp-tools/${id}/test`)

export const importMcpTools = (file: File, overwrite = false) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('overwrite', String(overwrite))
  return request.post<McpImportResponse>('/admin/mcp-tools/import', formData)
}
