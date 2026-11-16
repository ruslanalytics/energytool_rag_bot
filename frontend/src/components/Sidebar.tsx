import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createSession, listSessions } from '../api'
import { useAppStore } from '../store'
import { formatSessionDate } from '../utils/time'
import ErrorBanner from './ErrorBanner'
import styles from './Sidebar.module.css'

export default function Sidebar() {
  const sessionId = useAppStore((s) => s.sessionId)
  const setSessionId = useAppStore((s) => s.setSessionId)
  const view = useAppStore((s) => s.view)
  const setView = useAppStore((s) => s.setView)
  const queryClient = useQueryClient()

  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')

  const sessionsQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: listSessions,
  })

  const newChatMutation = useMutation({
    mutationFn: createSession,
    onSuccess: ({ session_id }) => {
      setSessionId(session_id)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  function handleSelect(id: string) {
    setSessionId(id)
  }

  const sessions = sessionsQuery.data ?? []
  const filtered = search.trim()
    ? sessions.filter((s) => (s.first_message ?? '').toLowerCase().includes(search.trim().toLowerCase()))
    : sessions

  return (
    <aside className={`${styles.sidebar} sidebar`}>
      <div className={styles.header}>
        <h1 className={styles.title}>Чаты</h1>
        <button
          type="button"
          className={styles.iconButton}
          aria-label="Поиск по чатам"
          aria-pressed={searchOpen}
          onClick={() => setSearchOpen((v) => !v)}
        >
          <SearchIcon />
        </button>
      </div>

      {searchOpen && (
        <input
          className={styles.search}
          type="search"
          placeholder="Поиск по чатам"
          aria-label="Поиск по чатам"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
      )}

      <button
        type="button"
        className={styles.newChat}
        onClick={() => newChatMutation.mutate()}
        disabled={newChatMutation.isPending}
      >
        <PlusIcon /> Новый чат
      </button>

      <div className={styles.list} role="list" aria-label="История чатов">
        {sessionsQuery.isLoading && <p className={styles.state}>Загрузка истории…</p>}

        {sessionsQuery.isError && (
          <ErrorBanner
            message="Не удалось загрузить историю чатов"
            onRetry={() => sessionsQuery.refetch()}
          />
        )}

        {sessionsQuery.isSuccess && filtered.length === 0 && (
          <p className={styles.state}>
            {sessions.length === 0 ? 'История чатов пуста' : 'Ничего не найдено'}
          </p>
        )}

        {filtered.map((session) => (
          <button
            key={session.id}
            type="button"
            role="listitem"
            className={`${styles.item} ${session.id === sessionId ? styles.itemActive : ''}`}
            onClick={() => handleSelect(session.id)}
            aria-current={session.id === sessionId}
          >
            <div className={styles.itemTop}>
              <span className={styles.itemTitle}>
                {session.first_message ?? 'Без сообщений'}
              </span>
              <span className={styles.itemDate}>{formatSessionDate(session.created_at)}</span>
            </div>
            <div className={styles.itemMeta}>
              <span>{session.message_count} сообщ.</span>
              {session.lead_count > 0 && <span className={styles.leadBadge}>Заявка оформлена</span>}
            </div>
          </button>
        ))}
      </div>

      {view === 'history' && (
        <button type="button" className={styles.mobileBack} onClick={() => setView('chat')}>
          Назад к чату
        </button>
      )}
    </aside>
  )
}

function SearchIcon() {
  return (
    <svg width="25" height="25" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.6" />
      <line x1="12.5" y1="12.5" x2="16.5" y2="16.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <line x1="8" y1="2" x2="8" y2="14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
