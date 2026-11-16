import type { ChatResponse, SessionMessage, SessionSummary } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(0, 'Нет соединения с сервером')
  }

  if (!res.ok) {
    let detail = 'Не удалось выполнить запрос'
    try {
      const body = (await res.json()) as { detail?: string }
      if (body && typeof body.detail === 'string') {
        detail = body.detail
      }
    } catch {
      //cообщение по умолчанию
    }
    throw new ApiError(res.status, detail)
  }

  return (await res.json()) as T
}

export function createSession(): Promise<{ session_id: string }> {
  return request('/api/sessions', { method: 'POST' })
}

export function listSessions(): Promise<SessionSummary[]> {
  return request('/api/sessions')
}

export function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  return request(`/api/sessions/${sessionId}`)
}

export function sendMessage(sessionId: string, message: string): Promise<ChatResponse> {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}
