import { beforeEach, describe, expect, it } from 'vitest'
import {
  readStoredDebugMode,
  readStoredSessionId,
  useAppStore,
  writeStoredDebugMode,
  writeStoredSessionId,
} from './store'

beforeEach(() => {
  window.localStorage.clear()
  useAppStore.setState({ sessionId: null, debugMode: false, view: 'chat', draft: '' })
})

describe('localStorage: session_id', () => {
  it('возвращает null, если ключ не записан', () => {
    expect(readStoredSessionId()).toBeNull()
  })

  it('читает и записывает session_id', () => {
    writeStoredSessionId('abc123')
    expect(window.localStorage.getItem('energytool_session_id')).toBe('abc123')
    expect(readStoredSessionId()).toBe('abc123')
  })
})

describe('localStorage: debug_mode', () => {
  it('по умолчанию выключен', () => {
    expect(readStoredDebugMode()).toBe(false)
  })

  it('читает и записывает флаг режима отладки', () => {
    writeStoredDebugMode(true)
    expect(window.localStorage.getItem('energytool_debug_mode')).toBe('1')
    expect(readStoredDebugMode()).toBe(true)

    writeStoredDebugMode(false)
    expect(readStoredDebugMode()).toBe(false)
  })
})

describe('useAppStore', () => {
  it('смена сессии обновляет состояние и localStorage', () => {
    useAppStore.getState().setSessionId('session-42')
    expect(useAppStore.getState().sessionId).toBe('session-42')
    expect(window.localStorage.getItem('energytool_session_id')).toBe('session-42')
  })

  it('смена сессии возвращает экран в chat', () => {
    useAppStore.setState({ view: 'history' })
    useAppStore.getState().setSessionId('session-7')
    expect(useAppStore.getState().view).toBe('chat')
  })

  it('toggleDebugMode переключает режим отладки и сохраняет его', () => {
    expect(useAppStore.getState().debugMode).toBe(false)
    useAppStore.getState().toggleDebugMode()
    expect(useAppStore.getState().debugMode).toBe(true)
    expect(window.localStorage.getItem('energytool_debug_mode')).toBe('1')

    useAppStore.getState().toggleDebugMode()
    expect(useAppStore.getState().debugMode).toBe(false)
    expect(window.localStorage.getItem('energytool_debug_mode')).toBe('0')
  })

  it('setDraft обновляет черновик сообщения', () => {
    useAppStore.getState().setDraft('привет')
    expect(useAppStore.getState().draft).toBe('привет')
  })
})
