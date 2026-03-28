import axios, { AxiosError, type AxiosRequestConfig, type AxiosResponse } from 'axios'

const TRACE_KEY = 'x_request_id'

const getRequestId = () => {
  const existing = sessionStorage.getItem(TRACE_KEY)
  if (existing) return existing
  const created = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  sessionStorage.setItem(TRACE_KEY, created)
  return created
}

export interface ApiErrorShape {
  code?: number
  message?: string
  detail?: string | { reason?: string; [key: string]: unknown }
}

export const getApiErrorMessage = (error: unknown, fallback = '请求失败') => {
  const err = error as any

  if (typeof err?.message === 'string' && err.message) {
    return err.message
  }

  const responseData = err?.response?.data
  if (typeof responseData?.message === 'string' && responseData.message) {
    return responseData.message
  }
  if (typeof responseData?.detail === 'string' && responseData.detail) {
    return responseData.detail
  }
  if (typeof responseData?.detail?.reason === 'string' && responseData.detail.reason) {
    return responseData.detail.reason
  }

  if (typeof err?.detail === 'string' && err.detail) {
    return err.detail
  }
  if (typeof err?.detail?.reason === 'string' && err.detail.reason) {
    return err.detail.reason
  }

  return fallback
}

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
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

http.interceptors.response.use(
  (response: AxiosResponse<any>) => {
    const payload = response.data
    if (payload && typeof payload === 'object' && 'code' in payload) {
      if (payload.code === 0) {
        return payload.data
      }
      const message = payload?.detail?.reason || payload?.detail || payload?.message || '请求失败'
      return Promise.reject({ ...payload, message })
    }
    return payload
  },
  (error: AxiosError<ApiErrorShape>) => {
    const status = error?.response?.status
    const data = error?.response?.data
    const normalizedMessage =
      getApiErrorMessage({ ...error, response: { ...error.response, data } }, '请求失败')

    if (status === 401 || status === 403) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    return Promise.reject({
      ...error,
      message: normalizedMessage,
      detail: data?.detail,
      code: data?.code,
    })
  }
)

interface RequestClient {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
}

const request: RequestClient = {
  get: (url, config) => http.get(url, config) as unknown as Promise<any>,
  post: (url, data, config) => http.post(url, data, config) as unknown as Promise<any>,
  put: (url, data, config) => http.put(url, data, config) as unknown as Promise<any>,
  patch: (url, data, config) => http.patch(url, data, config) as unknown as Promise<any>,
  delete: (url, config) => http.delete(url, config) as unknown as Promise<any>,
}

export default request
