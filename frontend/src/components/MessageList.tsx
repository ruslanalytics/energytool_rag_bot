import { useEffect, useRef, useState } from 'react'
import type { SessionMessage } from '../types'
import MessageBubble from './MessageBubble'
import ErrorBanner from './ErrorBanner'
import styles from './MessageList.module.css'

interface Props {
  messages: SessionMessage[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  isSending: boolean
}

export default function MessageList({ messages, isLoading, isError, onRetry, isSending }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [stickToBottom, setStickToBottom] = useState(true)

  useEffect(() => {
    const el = containerRef.current
    if (el && stickToBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, isSending, stickToBottom])

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setStickToBottom(distanceFromBottom < 80)
  }

  return (
    <div
      className={styles.container}
      ref={containerRef}
      onScroll={handleScroll}
      aria-live="polite"
      aria-label="Диалог"
    >
      {isLoading && <p className={styles.state}>Загрузка диалога…</p>}

      {isError && <ErrorBanner message="Не удалось загрузить сообщения" onRetry={onRetry} />}

      {!isLoading && !isError && messages.length === 0 && (
        <div className={styles.empty}>
          <p>Опишите задачу своими словами — например, «растут счета за электроэнергию».</p>
          <p className={styles.emptyHint}>Я подберу решение Energytool и, если нужно, передам заявку менеджеру.</p>
        </div>
      )}

      {messages.map((message, index) => (
        <MessageBubble key={`${message.created_at}-${index}`} message={message} />
      ))}

      {isSending && (
        <div className={styles.typing} aria-label="Бот печатает ответ">
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
        </div>
      )}
    </div>
  )
}
