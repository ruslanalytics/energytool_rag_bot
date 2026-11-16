import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createSession,
  getSessionMessages,
  sendMessage,
} from "./api";
import type { SessionMessage, SessionState } from "./types";
import { useAppStore } from "./store";
import Sidebar from "./components/Sidebar";
import ChatHeader from "./components/ChatHeader";
import MessageList from "./components/MessageList";
import ChatInput from "./components/ChatInput";
import ErrorBanner from "./components/ErrorBanner";
import styles from "./App.module.css";

export default function App() {
  const sessionId = useAppStore((s) => s.sessionId);
  const setSessionId = useAppStore((s) => s.setSessionId);
  const setDraft = useAppStore((s) => s.setDraft);
  const view = useAppStore((s) => s.view);

  const queryClient = useQueryClient();
  const [bootError, setBootError] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>("chat");
  const [sendError, setSendError] = useState<string | null>(null);
  const sessionStateRef = useRef<SessionState>("chat");
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    async function bootstrap() {
      try {
        if (!sessionId) {
          const { session_id } = await createSession();
          setSessionId(session_id);
          return;
        }
        try {
          await getSessionMessages(sessionId);
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            const { session_id } = await createSession();
            setSessionId(session_id);
          } else {
            throw err;
          }
        }
      } catch {
        setBootError(
          "Не удалось подключиться к серверу. Проверьте соединение и обновите страницу.",
        );
      }
    }

    bootstrap();
  }, [sessionId, setSessionId]);

  useEffect(() => {
    sessionStateRef.current = "chat";
    setSessionState("chat");
  }, [sessionId]);

  const messagesQuery = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => getSessionMessages(sessionId as string),
    enabled: Boolean(sessionId),
    retry: false,
  });

  useEffect(() => {
    if (!messagesQuery.isError || !sessionId) return;
    const err = messagesQuery.error;
    if (err instanceof ApiError && err.status === 404) {
      createSession().then(({ session_id }) => {
        setSessionId(session_id);
        queryClient.invalidateQueries({ queryKey: ["sessions"] });
      });
    }
  }, [
    messagesQuery.isError,
    messagesQuery.error,
    sessionId,
    setSessionId,
    queryClient,
  ]);

  const sendMutation = useMutation({
    mutationFn: (text: string) => sendMessage(sessionId as string, text),

    onMutate: async (text: string) => {
      setSendError(null);
      const key = ["messages", sessionId] as const;
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SessionMessage[]>(key);
      const prevState = sessionStateRef.current;
      const optimisticKind = prevState === "chat" ? "chat" : "lead";
      const optimistic: SessionMessage = {
        role: "user",
        content: text,
        kind: optimisticKind,
        debug: null,
        created_at: new Date().toISOString(),
      };
      queryClient.setQueryData<SessionMessage[]>(
        key,
        (old: SessionMessage[] | undefined) => [...(old ?? []), optimistic],
      );
      return { previous, prevState, key };
    },

    onSuccess: (data, _text, context) => {
      if (!context) return
      const newState = data.state
      const finalKind: SessionMessage['kind'] =
        context.prevState !== 'chat' || newState !== 'chat' ? 'lead' : 'chat'

      const botMessage: SessionMessage = {
        role: 'assistant',
        content: data.reply,
        kind: finalKind,
        debug: data.debug,
        created_at: new Date().toISOString(),
      }

      queryClient.setQueryData<SessionMessage[]>(context.key, (old) => {
        const list = old ?? []
        const withoutLastKindFix = list.map((m, i) =>
          i === list.length - 1 && m.role === 'user' ? { ...m, kind: finalKind } : m,
        )
        return [...withoutLastKindFix, botMessage]
      })

      sessionStateRef.current = newState
      setSessionState(newState)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },

    onError: (err, text, context) => {
      if (context) {
        queryClient.setQueryData(context.key, context.previous);
      }
      setDraft(text);
      if (err instanceof ApiError && err.status === 404) {
        createSession().then(({ session_id }) => {
          setSessionId(session_id);
          setSendError(
            "Сессия устарела, начат новый диалог. Отправьте сообщение ещё раз.",
          );
        });
      } else if (err instanceof ApiError) {
        setSendError(err.message);
      } else {
        setSendError(
          "Не удалось отправить сообщение. Проверьте соединение и попробуйте снова.",
        );
      }
    },
  });

  if (bootError) {
    return (
      <div className={styles.fatalError}>
        <ErrorBanner message={bootError} />
      </div>
    );
  }

  const messages = messagesQuery.data ?? [];
  const firstUserMessage = messages.find(
    (m) => m.kind === "chat" && m.role === "user",
  );
  const is404 =
    messagesQuery.error instanceof ApiError &&
    messagesQuery.error.status === 404;

  return (
    <div
      className={`${styles.app} ${view === "history" ? styles.showHistory : styles.showChat}`}
    >
      <Sidebar />
      <main className={styles.chatPanel}>
        <ChatHeader title={firstUserMessage?.content ?? null} />
        <MessageList
          messages={messages}
          isLoading={messagesQuery.isLoading}
          isError={messagesQuery.isError && !is404}
          onRetry={() => messagesQuery.refetch()}
          isSending={sendMutation.isPending}
        />
        {sendError && <ErrorBanner message={sendError} />}
        <ChatInput
          sessionState={sessionState}
          disabled={!sessionId || sendMutation.isPending}
          onSend={(text) => sendMutation.mutate(text)}
        />
      </main>
    </div>
  );
}
