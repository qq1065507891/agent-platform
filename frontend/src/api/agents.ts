import request from '../utils/request'

export interface AgentPayload {
  name: string
  description?: string
  prompt_template: string
  skills?: Array<{ skill_id: string }>
  is_public?: boolean
  status?: string
}

export interface AgentListParams {
  page?: number
  page_size?: number
  keyword?: string
  is_public?: boolean
  mine?: boolean
}

export const getAgents = (params?: AgentListParams) => request.get('/agents', { params })

export const getAgentDetail = (id: string) => request.get(`/agents/${id}`)

export const createAgent = (payload: AgentPayload) => request.post('/agents', payload)

export const updateAgent = (id: string, payload: Partial<AgentPayload>) =>
  request.put(`/agents/${id}`, payload)

export const listUserConversations = (params?: { agent_id?: string }) =>
  request.get('/conversations', { params })
