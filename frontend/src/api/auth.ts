import request from '../utils/request'

export interface LoginPayload {
  username: string
  password: string
  login_type?: 'password'
}

export interface LoginResponse {
  access_token: string
  expires_in: number
  user: {
    id: string
    username: string
    email?: string
    role?: string
  }
}

export interface RegisterPayload {
  username: string
  email: string
  password: string
}

export interface RegisterResponse {
  id: string
  username: string
  email: string
  role: string
  status: string
  created_at?: string
}

export const login = (payload: LoginPayload) =>
  request.post<LoginResponse>('/auth/login', payload)

export const register = (payload: RegisterPayload) =>
  request.post<RegisterResponse>('/auth/register', payload)

export const logout = () => request.post('/auth/logout')
