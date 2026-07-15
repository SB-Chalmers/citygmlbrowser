import type { ApiErrorResponse, ApiSuccess, GraphPayload } from '../types/graph'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const API_BASE_LABEL = API_BASE || window.location.origin

export class ApiError extends Error {
  code: string
  requestId?: string

  constructor(message: string, code = 'unknown_error', requestId?: string) {
    super(message)
    this.code = code
    this.requestId = requestId
  }
}

function asApiError(payload: unknown): ApiError {
  const err = payload as Partial<ApiErrorResponse>
  const message = err?.error?.message ?? 'Request failed'
  const code = err?.error?.code ?? 'unknown_error'
  const requestId = err?.error?.requestId
  return new ApiError(message, code, requestId)
}

export async function uploadGraph(file: File): Promise<ApiSuccess<GraphPayload>> {
  const formData = new FormData()
  formData.append('file', file)

  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/v1/graph-file`, {
      method: 'POST',
      body: formData,
    })
  } catch {
    throw new ApiError(
      `Cannot reach backend at ${API_BASE_LABEL}. Start it with \"npm run dev\" (repo root) or \"npm run dev:backend\".`,
      'backend_unreachable',
    )
  }

  let payload: ApiSuccess<GraphPayload> | ApiErrorResponse
  try {
    payload = (await response.json()) as ApiSuccess<GraphPayload> | ApiErrorResponse
  } catch {
    throw new ApiError('Backend returned a non-JSON response', 'invalid_backend_response')
  }

  if (!response.ok || payload.status === 'error') {
    throw asApiError(payload)
  }

  return payload
}
