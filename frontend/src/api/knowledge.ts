import request from '../utils/request'

export interface KnowledgeUploadResponse {
  doc_id: string
  version: number
  chunk_count: number
  status: string
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
