import { defineStore } from 'pinia'

interface UserInfo {
  id: string
  username: string
  email?: string
  role?: string
}

interface AuthState {
  token: string
  user: UserInfo | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: localStorage.getItem('access_token') ?? '',
    user: (() => {
      const raw = localStorage.getItem('user')
      return raw ? (JSON.parse(raw) as UserInfo) : null
    })(),
  }),
  actions: {
    setAuth(token: string, user: UserInfo) {
      this.token = token
      this.user = user
      localStorage.setItem('access_token', token)
      localStorage.setItem('user', JSON.stringify(user))
    },
    clearAuth() {
      this.token = ''
      this.user = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
    },
  },
})
