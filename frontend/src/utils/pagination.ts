export interface PaginationState {
  page: number
  pageSize: number
}

export interface PagedListResult<T> {
  list: T[]
  total: number
}

export const buildPageParams = <T extends Record<string, unknown>>(
  pagination: PaginationState,
  extra?: T,
) => ({
  page: pagination.page,
  page_size: pagination.pageSize,
  ...(extra || {}),
})

export const extractPagedList = <T>(payload: any): PagedListResult<T> => {
  const data = payload?.data ?? payload
  const list = Array.isArray(data?.list) ? (data.list as T[]) : []
  const total = Number(data?.total || 0)
  return { list, total }
}
