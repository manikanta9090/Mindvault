/** Reusable typed client for the MindVault backend. */

export type SourceType = 'NOTE' | 'URL'
export type ItemStatus = 'PROCESSING' | 'COMPLETED' | 'FAILED'
export type IndexingStatus = 'indexed' | 'failed' | 'unavailable'

export interface HealthResponse {
  status: string
  application: string
  version: string
}

export interface KnowledgeItemResponse {
  id: number
  title: string | null
  content: string
  source_type: SourceType
  source_url: string | null
  status: ItemStatus
  created_at: string
  updated_at: string
}

export interface IngestRequest {
  title?: string | null
  content: string
  source_type: SourceType
  source_url?: string | null
}

export interface IngestResponse extends KnowledgeItemResponse {
  indexing_status: IndexingStatus
  indexed_chunk_count: number | null
  indexing_error_code: string | null
}

export interface ListItemsParams {
  limit?: number
  offset?: number
  source_type?: SourceType
  status?: ItemStatus
}

export interface KnowledgeItemListResponse {
  items: KnowledgeItemResponse[]
  total: number
  limit: number
  offset: number
}

export interface QueryRequest {
  question: string
}

export interface QuerySource {
  item_id: number
  title: string | null
  source_type: SourceType
  source_url: string | null
  snippet: string
  citation_id: string
}

export interface QueryResponse {
  answer: string
  sources: QuerySource[]
}

export interface ApiErrorDetail {
  location?: Array<string | number>
  message?: string
}

interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
    details?: ApiErrorDetail[] | null
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
)

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  params?: object
}

function defaultErrorMessage(status: number): string {
  switch (status) {
    case 0:
      return 'Backend is unreachable.'
    case 400:
      return 'The request could not be accepted.'
    case 401:
    case 403:
      return 'You are not allowed to perform this action.'
    case 404:
      return 'The requested resource was not found.'
    case 409:
      return 'The request conflicts with the current state.'
    case 422:
      return 'Please check the submitted fields.'
    case 429:
      return 'Too many requests were made. Please try again shortly.'
    case 502:
      return 'An upstream service could not complete the request.'
    case 503:
      return 'The service is temporarily unavailable.'
    default:
      return `Backend returned HTTP ${status}.`
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | undefined

  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // A non-JSON error still deserves a useful status-based message.
  }

  const errorBody = body?.error
  const details = errorBody && Array.isArray(errorBody.details) ? errorBody.details : null
  const detailMessage = details
    ?.map((detail) => detail.message?.trim())
    .find((message): message is string => Boolean(message))
  const message =
    errorBody?.message?.trim() || detailMessage || defaultErrorMessage(response.status)

  return new ApiError(response.status, message, errorBody?.code ?? null, details)
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly details: ApiErrorDetail[] | null

  constructor(
    status: number,
    message: string,
    code: string | null = null,
    details: ApiErrorDetail[] | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function describeApiError(error: unknown, fallback = 'Something went wrong.'): string {
  if (!(error instanceof ApiError)) {
    return fallback
  }

  const detailMessages = (error.details ?? [])
    .map((detail) => detail.message?.trim())
    .filter((message): message is string => Boolean(message))

  if (detailMessages.length === 0) {
    return error.message || fallback
  }

  return `${error.message} ${detailMessages.slice(0, 2).join(' ')}`.trim()
}

function buildPath(path: string, params?: RequestOptions['params']): string {
  if (!params) {
    return path
  }

  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === 'string' || typeof value === 'number') {
      query.set(key, String(value))
    }
  }

  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${buildPath(path, options.params)}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, defaultErrorMessage(0))
  }

  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(response.status, 'The backend returned an invalid response.')
  }
}

export const api = {
  getHealth: (): Promise<HealthResponse> => request<HealthResponse>('/health'),
  ingestItem: (payload: IngestRequest): Promise<IngestResponse> =>
    request<IngestResponse>('/ingest', { method: 'POST', body: payload }),
  listItems: (params: ListItemsParams = {}): Promise<KnowledgeItemListResponse> =>
    request<KnowledgeItemListResponse>('/items', { params }),
  queryKnowledge: (payload: QueryRequest): Promise<QueryResponse> =>
    request<QueryResponse>('/query', { method: 'POST', body: payload }),
}
