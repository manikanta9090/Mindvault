/** Reusable typed client for the MindVault backend. */

export interface HealthResponse {
  status: string
  application: string
  version: string
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
)

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError(0, 'Backend is unreachable.')
  }

  if (!response.ok) {
    throw new ApiError(response.status, `Backend returned HTTP ${response.status}.`)
  }

  return (await response.json()) as T
}

export const api = {
  getHealth: (): Promise<HealthResponse> => request<HealthResponse>('/health'),
}
