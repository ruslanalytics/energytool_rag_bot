# energytool_rag_bot

ИИ-консультант для сайта МТС Energytool (кейс Hack&Change 2026). Ведёт клиента от описания проблемы до заявки менеджеру: ищет ответ по базе знаний Energytool (RAG), а когда клиент готов, собирает ФИО, телефон, компанию и формирует резюме диалога для менеджера.

## Структура

```
.
├── backend/
│   ├── app.py              FastAPI-приложение, роуты /api, /health, раздача фронтенда
│   ├── rag.py               поиск по базе знаний: чанкинг, эмбеддинги, ChromaDB, BM25
│   ├── lead_flow.py         логика диалога и сбора заявки (ФИО → телефон → компания)
│   ├── storage.py           хранение сессий, сообщений, заявок
│   ├── test_backend.py
│   └── env.example
├── frontend/                веб-чат (React + Vite + TypeScript), подробности — frontend/README.md
├── data/
│   └── knowledge-base.zip   база знаний Energytool — распаковывается и индексируется при старте
├── Dockerfile               сборка фронта (Node) и бэкенда (Python) в один образ
├── compose.yaml             запуск через docker compose
└── requirements.txt         зависимости Python-бэкенда
```

## Запуск через Docker

```bash
cp backend/env.example backend/.env   # заполнить, если нужны внешние ключи
docker compose up --build
```

- `http://localhost:8000/` — чат (бэкенд собирает фронтенд на этапе сборки образа и раздаёт его как статику)
- `http://localhost:8000/health` — статус индекса базы знаний
- `http://localhost:8000/docs` — Swagger

## Локальная разработка без Docker

Бэкенд:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn app:app --reload --port 8000
```

Фронтенд, отдельным терминалом:

```bash
cd frontend
npm install
npm run dev
```

`vite.config.ts` проксирует `/api` и `/health` на `localhost:8000`, поэтому оба процесса работают вместе без дополнительной настройки CORS.

## API

REST-контракт бэкенда: `POST /api/sessions`, `GET /api/sessions`, `GET /api/sessions/{id}`, `POST /api/chat`, `GET /api/leads`, `GET /health`. Формат запросов/ответов и коды ошибок — в докстрингах `backend/app.py` и в Swagger (`/docs`).

## Поиск по базе знаний

Эмбеддинги хранятся в ChromaDB, чанкинг — через `langchain-text-splitters`, поиск гибридный: векторный (ChromaDB) + BM25 (`bm25s`). Детали реализации — в `backend/rag.py`.

## Ограничения

- Реальных интеграций с CRM или почтой нет, заявка хранится внутри сервиса.
- После «Нового диалога» или закрытия чата контекст предыдущей сессии не используется, но сама история всех сессий (включая без заявки) сохраняется и доступна для просмотра.

## Стек

Backend: Python, FastAPI, ChromaDB, BM25 (bm25s). Frontend: React, Vite, TypeScript, Zustand, TanStack Query. Docker: двухстадийная сборка — Node собирает фронтенд, Python его раздаёт.
