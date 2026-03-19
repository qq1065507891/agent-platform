import request from '../utils/request'

export interface UserItem {
  id: string
  username: string
  email: string
  role: string
  status: 'active' | 'disabled'
  created_at?: string
}

export interface UserListParams {
  page?: number
  page_size?: number
  keyword?: string
}

export interface CreateUserPayload {
  username: string
  email: string
  password: string
  role: string
  status?: 'active' | 'disabled'
}

export interface UpdateUserPayload {
  username?: string
  email?: string
  password?: string
  role?: string
  status?: 'active' | 'disabled'
}

export interface ImportUsersPayload {
  users: CreateUserPayload[]
}

export const getUsers = (params?: UserListParams) => request.get('/users', { params })

export const createUser = (payload: CreateUserPayload) => request.post('/users', payload)

export const updateUser = (id: string, payload: UpdateUserPayload) => request.put(`/users/${id}`, payload)

export const importUsers = (payload: ImportUsersPayload) => request.post('/users/import', payload)
