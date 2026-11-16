import { create } from 'zustand'

const SESSION_ID_KEY = 'energytool_session_id'
const DEBUG_MODE_KEY = 'energytool_debug_mode'

export function readStoredSessionId(): string | null {
  try {
    return window.localStorage.getItem(SESSION_ID_KEY)
  } catch {
    return null
  }
}

export function writeStoredSessionId(id: string | null): void {
  try {
    if (id === null) {
      window.localStorage.removeItem(SESSION_ID_KEY)
    } else {
      window.localStorage.setItem(SESSION_ID_KEY, id)
    }
  } catch {
    // localStorage недоступен (приватный режим и т.п.) — просто не сохраняем
  }
}

export function readStoredDebugMode(): boolean {
  try {
    return window.localStorage.getItem(DEBUG_MODE_KEY) === '1'
  } catch {
    return false
  }
}

export function writeStoredDebugMode(value: boolean): void {
  try {
    window.localStorage.setItem(DEBUG_MODE_KEY, value ? '1' : '0')
  } catch {
    // игнорируем ошибку записи
  }
}

export type ScreenView = 'chat' | 'history'

interface AppState {
  sessionId: string | null
  debugMode: boolean
  view: ScreenView
  draft: string
  setSessionId: (id: string) => void
  setDebugMode: (value: boolean) => void
  toggleDebugMode: () => void
  setView: (view: ScreenView) => void
  setDraft: (draft: string) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  sessionId: readStoredSessionId(),
  debugMode: readStoredDebugMode(),
  view: 'chat',
  draft: '',

  setSessionId: (id) => {
    writeStoredSessionId(id)
    set({ sessionId: id, view: 'chat' })
  },

  setDebugMode: (value) => {
    writeStoredDebugMode(value)
    set({ debugMode: value })
  },

  toggleDebugMode: () => {
    const next = !get().debugMode
    writeStoredDebugMode(next)
    set({ debugMode: next })
  },

  setView: (view) => set({ view }),

  setDraft: (draft) => set({ draft }),
}))
