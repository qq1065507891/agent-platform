import axios from 'axios'

const TRACE_KEY = 'x_request_id'

const getRequestId = () => {
  const existing = sessionStorage.getItem(TRACE_KEY)
  if (existing) return existing
  const created = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  sessionStorage.setItem(TRACE_KEY, created)
  return created
}

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  const requestId = getRequestId()
  config.headers = config.headers ?? {}
  config.headers['X-Request-Id'] = requestId
  config.headers['X-Trace-Id'] = requestId
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => {
    const payload = response.data
    if (payload && typeof payload === 'object' && 'code' in payload) {
      if (payload.code === 0) {
        return payload.data
      }
      return Promise.reject(payload)
    }
    return payload
  },
  (error) => {
    const status = error?.response?.status
    if (status === 401 || status === 403) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default request
