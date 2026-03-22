import request from '../utils/request'

export type SkillStatus = 'active' | 'disabled'

export type SkillSourceType =
  | 'builtin'
  | 'github'
  | 'npm'
  | 'http'
  | 'local'
  | 'private_registry'

export interface SkillItem {
  id: string
  skill_id: string
  name: string
  description?: string
  category: string
  source_type: SkillSourceType
  version: string
  status: SkillStatus
  source_url?: string | null
  source_version?: string | null
  current_revision_id?: string | null
}

export interface SkillListParams {
  page?: number
  page_size?: number
  category?: string
  source_type?: SkillSourceType
  status?: SkillStatus
}

export interface DisableSkillPayload {
  reason?: string
}

export interface LoadSkillPayload {
  source_type: SkillSourceType
  source_url?: string
  source_version?: string
  package_path?: string
  expected_hash?: string
  skill_id?: string
  name?: string
}

export interface UploadLocalSkillPayload {
  file: File
  source_version?: string
  expected_hash?: string
  skill_id?: string
  name?: string
}

export interface LoadSkillResponse {
  task_id: string
  skill_id: string
  status: string
}

export interface SkillTaskStatusResponse {
  task_id: string
  status: string
  result?: Record<string, unknown> | null
  error?: string | null
}

export const getSkills = (params?: SkillListParams) => request.get('/skills', { params })

export const disableSkill = (id: string, payload: DisableSkillPayload = {}) =>
  request.post(`/skills/${id}/disable`, payload)

export const enableSkill = (id: string) => request.post(`/skills/${id}/enable`)

export const deleteSkill = (id: string) => request.delete(`/skills/${id}`)

export const loadSkill = (payload: LoadSkillPayload) =>
  request.post<LoadSkillResponse>('/skills/load', payload)

export const uploadLocalSkill = (payload: UploadLocalSkillPayload) => {
  const formData = new FormData()
  formData.append('file', payload.file)
  if (payload.source_version) formData.append('source_version', payload.source_version)
  if (payload.expected_hash) formData.append('expected_hash', payload.expected_hash)
  if (payload.skill_id) formData.append('skill_id', payload.skill_id)
  if (payload.name) formData.append('name', payload.name)
  return request.post<LoadSkillResponse>('/skills/upload', formData)
}

export const getSkillTaskStatus = (taskId: string) =>
  request.get<SkillTaskStatusResponse>(`/skills/tasks/${taskId}`)
