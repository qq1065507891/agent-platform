import request from '../utils/request'

export interface SkillItem {
  id: string
  skill_id: string
  name: string
  description?: string
  category: string
  source_type: string
  version: string
  status: string
}

export interface SkillListParams {
  page?: number
  page_size?: number
  category?: string
  source_type?: string
  status?: string
}

export const getSkills = (params?: SkillListParams) => request.get('/skills', { params })
