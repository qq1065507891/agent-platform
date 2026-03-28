import request from '../utils/request'

export interface MessageSource {
  doc_id?: string
  source?: string
  version?: number | string
  chunk_index?: number | string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  pending?: boolean
  interrupted?: boolean
  sources?: MessageSource[]
}

export interface ConversationItem {
  id: string
  agent_id: string
  title?: string
  messages: ChatMessage[]
  agent_name?: string
  agent_description?: string
  created_at?: string
}

export const createConversation = (payload: { agent_id: string; title?: string }) =>
  request.post<ConversationItem>('/conversations', payload)

export const getConversation = (id: string) =>
  request.get<ConversationItem>(`/conversations/${id}`)

export const listConversations = (params?: { agent_id?: string }) =>
  request.get<ConversationItem[]>('/conversations', { params })

export const renameConversation = (id: string, payload: { title: string }) =>
  request.patch(`/conversations/${id}`, payload)

export const deleteConversation = (id: string) => request.delete(`/conversations/${id}`)
