import type { SessionMessage } from '../types'
import { useAppStore } from '../store'
import { formatMessageTime } from '../utils/time'
import DebugInfo from './DebugInfo'
import styles from './MessageBubble.module.css'

interface Props {
  message: SessionMessage
}

export default function MessageBubble({ message }: Props) {
  const debugMode = useAppStore((s) => s.debugMode)

  if (message.kind === 'lead') {
    return (
      <div className={`${styles.row} ${styles.leadRow}`}>
        <div className={styles.leadBubble}>{message.content}</div>
      </div>
    )
  }

  if (message.role === 'user') {
    return (
      <div className={`${styles.row} ${styles.userRow}`}>
        <div className={styles.userBubble}>{message.content}</div>
        <time className={styles.timeRight}>{formatMessageTime(message.created_at)}</time>
      </div>
    )
  }

  return (
    <div className={`${styles.row} ${styles.assistantRow}`}>
      {debugMode && message.debug && <DebugInfo debug={message.debug} />}
      <div className={styles.assistantText}>{message.content}</div>
      <time className={styles.timeLeft}>{formatMessageTime(message.created_at)}</time>
    </div>
  )
}
