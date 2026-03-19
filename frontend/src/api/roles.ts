import request from '../utils/request'

export interface RoleItem {
  id: string
  name: string
  permissions: string[]
}

export interface RolePayload {
  name: string
  permissions: string[]
}

export const getRoles = () => request.get('/roles')

export const createRole = (payload: RolePayload) => request.post('/roles', payload)

export const updateRole = (id: string, payload: RolePayload) => request.put(`/roles/${id}`, payload)
