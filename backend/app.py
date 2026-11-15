import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import lead_flow
import rag
import storage

MAX_MESSAGE_LENGTH = 2000
INDEX_PATH = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
TIMING_KEYS = ("search_seconds", "rerank_seconds", "llm_seconds")
state = {"index": None}


def build_index_or_exit():
    try:
        return rag.build_index()
    except FileNotFoundError:
        folder = storage.data_dir()
        files = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else "папки нет"
        print(
            f"База знаний не найдена. Искал knowledge-base.zip в папке {folder.resolve()}. "
            f"Сейчас в ней: {files}. Положите knowledge-base.zip в папку data и запустите снова.",
            flush=True,
        )
        raise SystemExit(1)


@asynccontextmanager
async def lifespan(app):
    storage.init_db()
    state["index"] = build_index_or_exit()
    yield


app = FastAPI(title="МТС Energytool: ИИ-консультант", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


def seconds_since(started):
    return round(time.time() - started, 2)


def build_debug(result, started):
    debug = {key: result["timings"].get(key, 0.0) for key in TIMING_KEYS}
    debug["total_seconds"] = seconds_since(started)
    debug["sources"] = result["sources"]
    debug["error"] = result["error"]
    return debug


def lead_turn(session, message, started, start_new):
    session_id = session["id"]
    storage.add_message(session_id, "user", message, "lead")
    if start_new:
        reply = lead_flow.start_lead(session_id)
    else:
        reply = lead_flow.handle_step(session, message)
    debug = {"total_seconds": seconds_since(started)}
    storage.add_message(session_id, "assistant", reply, "lead", debug)
    return reply, debug


def chat_turn(session, message, started):
    session_id = session["id"]
    storage.add_message(session_id, "user", message, "chat")
    result = rag.get_answer(state["index"], lead_flow.chat_history(session_id))
    reply = result["answer"]
    if lead_flow.should_offer(session, session_id):
        reply = reply + "\n\n" + lead_flow.OFFER_TEXT
        storage.update_session(session_id, lead_offered=1)
    debug = build_debug(result, started)
    storage.add_message(session_id, "assistant", reply, "chat", debug)
    return reply, debug


@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(state["index"]["documents"])}


@app.post("/api/sessions")
def create_session():
    return {"session_id": storage.create_session()}


@app.get("/api/sessions")
def list_sessions():
    return storage.list_sessions()


@app.get("/api/sessions/{session_id}")
def get_session_messages(session_id: str):
    if storage.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return storage.get_messages(session_id)


@app.post("/api/chat")
def chat(request: ChatRequest):
    started = time.time()
    message = request.message.strip()
    if not message or len(request.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=400, detail="Сообщение пустое или длиннее 2000 символов")
    session = storage.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session["state"] != "chat":
        reply, debug = lead_turn(session, message, started, False)
    elif lead_flow.wants_lead(session["id"], message):
        reply, debug = lead_turn(session, message, started, True)
    else:
        reply, debug = chat_turn(session, message, started)
    new_state = storage.get_session(session["id"])["state"]
    return {"reply": reply, "state": new_state, "debug": debug}


@app.get("/api/leads")
def list_leads():
    return storage.list_leads()


@app.get("/")
def index():
    if not INDEX_PATH.is_file():
        raise HTTPException(status_code=404, detail="static/index.html не найден")
    return FileResponse(INDEX_PATH)
