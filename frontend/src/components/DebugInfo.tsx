import { useState } from 'react'
import type { DebugSource, MessageDebug } from '../types'
import { pluralize } from '../utils/time'
import styles from './DebugInfo.module.css'

interface Props {
  debug: MessageDebug
}

export default function DebugInfo({ debug }: Props) {
  const [open, setOpen] = useState(false)
  const sources = debug.sources ?? []
  const hasBreakdown =
    debug.search_seconds !== undefined ||
    debug.rerank_seconds !== undefined ||
    debug.llm_seconds !== undefined ||
    sources.length > 0 ||
    Boolean(debug.error)

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.summary}
        onClick={() => hasBreakdown && setOpen((v) => !v)}
        aria-expanded={open}
      >
        Время ответа: {debug.total_seconds.toFixed(1)} секунды.
        {sources.length > 0 && (
          <> Смотреть {sources.length} {pluralize(sources.length, 'источник', 'источника', 'источников')}</>
        )}
        {hasBreakdown && (
          <span className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`}>
            <ChevronIcon />
          </span>
        )}
      </button>

      {open && hasBreakdown && (
        <div className={styles.details}>
          {debug.search_seconds !== undefined && <div>Поиск: {debug.search_seconds.toFixed(2)} с</div>}
          {debug.rerank_seconds !== undefined && (
            <div>Реранжирование: {debug.rerank_seconds.toFixed(2)} с</div>
          )}
          {debug.llm_seconds !== undefined && <div>Генерация: {debug.llm_seconds.toFixed(2)} с</div>}

          {debug.error && <div className={styles.error}>Ошибка: {debug.error}</div>}

          {sources.length > 0 && (
            <ul className={styles.sources}>
              {sources.map((source) => (
                <SourceItem key={source.chunk_id} source={source} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function ChevronIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
      <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SourceItem({ source }: { source: DebugSource }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <li className={styles.source}>
      <button type="button" className={styles.sourceHeader} onClick={() => setExpanded((v) => !v)}>
        <span>{source.title}</span>
        <span className={styles.sourceFile}>{source.source}</span>
      </button>
      {expanded && <p className={styles.sourcePreview}>{source.preview}</p>}
    </li>
  )
}
