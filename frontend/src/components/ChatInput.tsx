import { useEffect, useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { useAppStore } from '../store'
import type { SessionState } from '../types'
import styles from './ChatInput.module.css'

const MAX_LENGTH = 2000

const STATE_LABELS: Record<Exclude<SessionState, 'chat'>, string> = {
  lead_name: 'Оформление заявки — укажите ФИО',
  lead_phone: 'Оформление заявки — укажите телефон',
  lead_company: 'Оформление заявки — укажите компанию',
}

interface Props {
  sessionState: SessionState
  disabled: boolean
  onSend: (text: string) => void
}

export default function ChatInput({ sessionState, disabled, onSend }: Props) {
  const draft = useAppStore((s) => s.draft)
  const setDraft = useAppStore((s) => s.setDraft)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const trimmed = draft.trim()
  const canSend = !disabled && trimmed.length > 0 && draft.length <= MAX_LENGTH

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const maxHeight = parseInt(getComputedStyle(el).maxHeight, 10) || Infinity
    const next = Math.min(el.scrollHeight, maxHeight)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [draft])

  function submit() {
    if (!canSend) return
    onSend(trimmed)
    setDraft('')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className={styles.wrap}>
      {sessionState !== 'chat' && (
        <div className={styles.leadStatus}>{STATE_LABELS[sessionState]}</div>
      )}

      <div className={styles.bar}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          placeholder="Опишите задачу — например, «растут счета за электроэнергию»"
          aria-label="Сообщение"
          value={draft}
          maxLength={MAX_LENGTH + 200}
          rows={1}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          className={styles.send}
          aria-label="Отправить сообщение"
          disabled={!canSend}
          onClick={submit}
        >
          <SendIcon />
        </button>
      </div>

      <div className={styles.footer}>
        <span className={draft.length > MAX_LENGTH ? styles.counterOver : styles.counter}>
          {draft.length}/{MAX_LENGTH}
        </span>
        <span className={styles.disclaimer}>
          Отвечаю на основе базы знаний Energytool. Для сложных технических настроек подключу менеджера.
        </span>
      </div>
    </div>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 17" fill="none" aria-hidden="true">
      <path d="M2 9L16 2L11 16L8.5 10.5L2 9Z" fill="currentColor"/>
    </svg>
  )
}
