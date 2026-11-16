import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createSession, getSessionMessages, sendMessage } from './api'

function mockFetchOnce(response: { ok: boolean; status: number; json: () => Promise<unknown> }) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ...response,
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api.ts', () => {
  it('разбирает успешный ответ POST /api/sessions', async () => {
    mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => ({ session_id: 'abc123' }),
    })

    const result = await createSession()
    expect(result).toEqual({ session_id: 'abc123' })
  })

  it('разбирает успешный ответ POST /api/chat', async () => {
    mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => ({
        reply: 'Привет!',
        state: 'chat',
        debug: { total_seconds: 1.2, sources: [], error: null },
      }),
    })

    const result = await sendMessage('session-1', 'Привет')
    expect(result.reply).toBe('Привет!')
    expect(result.state).toBe('chat')
  })

  it('пробрасывает ошибку 400 с текстом detail', async () => {
    mockFetchOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Сообщение не может быть пустым' }),
    })

    await expect(sendMessage('session-1', '')).rejects.toMatchObject({
      status: 400,
      message: 'Сообщение не может быть пустым',
    })
  })

  it('пробрасывает ошибку 404 для неизвестной сессии', async () => {
    mockFetchOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Сессия не найдена' }),
    })

    await expect(getSessionMessages('unknown')).rejects.toMatchObject({
      status: 404,
    })
  })

  it('пробрасывает ошибку 422 при некорректном теле запроса', async () => {
    mockFetchOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'Поле message обязательно' }),
    })

    await expect(sendMessage('session-1', 'текст')).rejects.toBeInstanceOf(ApiError)
  })

  it('оборачивает сетевой сбой в ApiError со статусом 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    await expect(createSession()).rejects.toMatchObject({ status: 0 })
  })
})
