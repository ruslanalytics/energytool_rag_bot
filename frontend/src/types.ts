export type SessionState = 'chat' | 'lead_name' | 'lead_phone' | 'lead_company'

export interface SessionSummary {
  id: string
  created_at: string
  first_message: string | null
  message_count: number
  lead_count: number
}

export interface DebugSource {
  source: string
  chunk_id: string
  title: string
  preview: string
}

export interface MessageDebug {
  search_seconds?: number
  rerank_seconds?: number
  llm_seconds?: number
  total_seconds: number
  sources?: DebugSource[]
  error?: string | null
}

export type MessageRole = 'user' | 'assistant'
export type MessageKind = 'chat' | 'lead'

export interface SessionMessage {
  role: MessageRole
  content: string
  kind: MessageKind
  debug: MessageDebug | null
  created_at: string
}

export interface ChatResponse {
  reply: string
  state: SessionState
  debug: MessageDebug
}
