import request from '../utils/request'

export interface KnowledgeUploadResponse {
  doc_id: string
  version: number
  chunk_count: number
  status: string
}

export interface KnowledgeDocumentItem {
  doc_id: string
  source: string
  version: number
  chunk_count: number
  status: string
  created_at?: string
}

export interface KnowledgeDocumentsResponse {
  list: KnowledgeDocumentItem[]
  total: number
  page: number
  page_size: number
}

export const uploadKnowledge = (file: File, agent_id?: string) => {
  const formData = new FormData()
  formData.append('file', file)
  if (agent_id) {
    formData.append('agent_id', agent_id)
  }
  return request.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const getKnowledgeDocuments = (params: {
  agent_id: string
  page?: number
  page_size?: number
  keyword?: string
}) => request.get('/knowledge/documents', { params })

export const deleteKnowledgeDocument = (
  doc_id: string,
  agent_id: string,
  delete_mode: 'soft' | 'hard' = 'soft'
) => request.delete(`/knowledge/documents/${doc_id}`, { params: { agent_id, delete_mode } })

export interface BatchDeleteKnowledgeResultItem {
  doc_id: string
  deleted: boolean
  deleted_chunks: number
}

export interface BatchDeleteKnowledgeResponse {
  results: BatchDeleteKnowledgeResultItem[]
  success_count: number
  total: number
}

export const batchDeleteKnowledgeDocuments = (payload: {
  agent_id: string
  doc_ids: string[]
  delete_mode?: 'soft' | 'hard'
}) => request.post('/knowledge/documents/batch-delete', payload)

export interface KnowledgeTaskStatusResponse {
  task_id: string
  state: 'PENDING' | 'STARTED' | 'RETRY' | 'FAILURE' | 'SUCCESS' | string
  result?: Record<string, any>
  error?: string
}

export const getKnowledgeTaskStatus = (task_id: string) => request.get(`/knowledge/tasks/${task_id}`)

export const purgeDeletedKnowledgeDocuments = (payload: { agent_id?: string; doc_ids?: string[] }) =>
  request.post('/knowledge/documents/purge-deleted', payload)
