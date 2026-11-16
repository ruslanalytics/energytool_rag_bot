import { useAppStore } from "../store";
import styles from "./ChatHeader.module.css";

interface Props {
  title: string | null;
}

export default function ChatHeader({ title }: Props) {
  const debugMode = useAppStore((s) => s.debugMode);
  const toggleDebugMode = useAppStore((s) => s.toggleDebugMode);
  const setView = useAppStore((s) => s.setView);

  const label = title ? truncate(title, 40) : "Новый чат";

  return (
    <header className={styles.header}>
      <button
        type="button"
        className={styles.historyButton}
        onClick={() => setView("history")}
        aria-label="Открыть историю чатов"
      >
        <ListIcon />
      </button>

      <span className={styles.breadcrumb}>/{label}</span>

      <label className={styles.debugToggle}>
        <span className={styles.debugLabel}>Отладка</span>
        <span className={styles.switch}>
          <input
            type="checkbox"
            className={styles.switchInput}
            checked={debugMode}
            onChange={() => toggleDebugMode()}
            aria-label="Режим отладки"
          />
          <span className={styles.switchTrack}>
            <span className={styles.switchThumb} />
          </span>
        </span>
      </label>
    </header>
  );
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function ListIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
    >
      <line
        x1="2"
        y1="4"
        x2="16"
        y2="4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <line
        x1="2"
        y1="9"
        x2="16"
        y2="9"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <line
        x1="2"
        y1="14"
        x2="16"
        y2="14"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
