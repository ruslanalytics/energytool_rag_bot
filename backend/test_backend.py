import os
import sys
import tempfile
import types
import unittest

TMP = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = TMP.name

try:
    import rag
except ImportError:
    rag = types.ModuleType("rag")
    sys.modules["rag"] = rag

from fastapi.testclient import TestClient

calls = {"answer": [], "summary": []}
SOURCE = {"source": "doc.md", "chunk_id": "doc.md_0", "title": "Тест", "preview": "текст"}
TIMINGS = {"search_seconds": 0.1, "rerank_seconds": 0.0, "llm_seconds": 0.2, "total_seconds": 0.3}


def fake_build_index():
    return {"documents": [1, 2, 3]}


def fake_get_answer(index, messages):
    calls["answer"].append(messages)
    return {"answer": "Ответ бота", "sources": [SOURCE], "timings": TIMINGS, "error": None}


def fake_make_summary(messages):
    calls["summary"].append(messages)
    return "Резюме диалога"


rag.build_index = fake_build_index
rag.get_answer = fake_get_answer
rag.make_summary = fake_make_summary

import app
import lead_flow

NAME = "Иван Тестовый"
PHONE = "+7 900 000-00-00"
COMPANY = "ООО Тест"
client = None


def setUpModule():
    global client
    client = TestClient(app.app)
    client.__enter__()


def tearDownModule():
    client.__exit__(None, None, None)
    TMP.cleanup()


def new_session():
    return client.post("/api/sessions").json()["session_id"]


def say(session_id, text):
    return client.post("/api/chat", json={"session_id": session_id, "message": text})


def say_json(session_id, text):
    return say(session_id, text).json()


def session_at_offer():
    session_id = new_session()
    say(session_id, "Первый вопрос")
    say(session_id, "Второй вопрос")
    return session_id


def session_in_lead():
    session_id = new_session()
    say(session_id, "Хочу оставить заявку")
    return session_id


class BackendTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(client.get("/health").json(), {"status": "ok", "chunks": 3})

    def test_new_session_does_not_see_old_one(self):
        old_id = new_session()
        say(old_id, "Секретный вопрос старой сессии")
        new_id = new_session()
        say(new_id, "Новый вопрос")
        self.assertEqual(calls["answer"][-1], [{"role": "user", "content": "Новый вопрос"}])

    def test_context_kept_inside_session(self):
        session_id = new_session()
        say(session_id, "Первый")
        say(session_id, "Второй")
        say(session_id, "Третий")
        roles = [m["role"] for m in calls["answer"][-1]]
        contents = [m["content"] for m in calls["answer"][-1]]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant", "user"])
        self.assertEqual(contents[0], "Первый")
        self.assertEqual(contents[-1], "Третий")
        self.assertNotIn(lead_flow.OFFER_TEXT, " ".join(contents))

    def test_offer_after_second_message_only_once(self):
        session_id = new_session()
        replies = [say_json(session_id, f"Вопрос {i}")["reply"] for i in range(4)]
        has_offer = [lead_flow.OFFER_TEXT in reply for reply in replies]
        self.assertEqual(has_offer, [False, True, False, False])

    def test_yes_without_offer_does_not_start_lead(self):
        session_id = new_session()
        data = say_json(session_id, "да")
        self.assertEqual(data["state"], "chat")
        self.assertEqual(data["reply"], "Ответ бота")

    def test_yes_right_after_offer_starts_lead(self):
        session_id = session_at_offer()
        data = say_json(session_id, "Да")
        self.assertEqual(data["state"], "lead_name")
        self.assertEqual(data["reply"], lead_flow.FIRST_QUESTION)

    def test_yes_later_than_offer_does_not_start_lead(self):
        session_id = session_at_offer()
        say(session_id, "Расскажите подробнее")
        data = say_json(session_id, "да")
        self.assertEqual(data["state"], "chat")

    def test_keywords_start_lead(self):
        phrases = [
            "Хочу оставить заявку",
            "Перезвоните мне",
            "Позвоните завтра",
            "Хочу связаться с менеджером",
            "Свяжитесь со мной, пожалуйста",
        ]
        for phrase in phrases:
            session_id = new_session()
            self.assertEqual(say_json(session_id, phrase)["state"], "lead_name", phrase)

    def test_phone_validation(self):
        session_id = session_in_lead()
        say(session_id, NAME)
        for bad in ["123", "телефон", "1234567890123456"]:
            data = say_json(session_id, bad)
            self.assertEqual(data["state"], "lead_phone", bad)
            self.assertEqual(data["reply"], lead_flow.PHONE_RETRY)
        self.assertEqual(say_json(session_id, PHONE)["state"], "lead_company")

    def test_cancel_on_every_step(self):
        leads_before = len(client.get("/api/leads").json())
        for steps in ([], [NAME], [NAME, PHONE]):
            session_id = session_in_lead()
            for step in steps:
                say(session_id, step)
            data = say_json(session_id, "отмена")
            self.assertEqual(data["state"], "chat")
            self.assertEqual(data["reply"], lead_flow.CANCEL_REPLY)
            self.assertEqual(say_json(session_id, "Обычный вопрос")["reply"], "Ответ бота")
        self.assertEqual(len(client.get("/api/leads").json()), leads_before)

    def test_lead_saved_and_summary_uses_chat_only(self):
        session_id = session_at_offer()
        say(session_id, "да")
        say(session_id, NAME)
        say(session_id, PHONE)
        data = say_json(session_id, COMPANY)
        self.assertEqual(data["state"], "chat")
        self.assertIn("Резюме диалога", data["reply"])
        summary_input = calls["summary"][-1]
        self.assertEqual([m["role"] for m in summary_input], ["user", "assistant", "user", "assistant"])
        self.assertNotIn(lead_flow.OFFER_TEXT, str(summary_input))
        lead = client.get("/api/leads").json()[0]
        self.assertEqual(lead["session_id"], session_id)
        self.assertEqual((lead["name"], lead["phone"], lead["company"]), (NAME, PHONE, COMPANY))
        self.assertEqual(lead["summary"], "Резюме диалога")

    def test_lead_steps_never_reach_rag(self):
        session_id = session_at_offer()
        for step in ["да", NAME, PHONE, COMPANY, "Ещё вопрос"]:
            say(session_id, step)
        everything = str(calls["answer"][-5:]) + str(calls["summary"][-1])
        for secret in (NAME, PHONE, COMPANY):
            self.assertNotIn(secret, everything)
        self.assertEqual(calls["answer"][-1][-1]["content"], "Ещё вопрос")

    def test_session_without_lead_in_history(self):
        session_id = new_session()
        say(session_id, "Просто вопрос")
        listed = {s["id"]: s for s in client.get("/api/sessions").json()}
        self.assertEqual(listed[session_id]["first_message"], "Просто вопрос")
        self.assertEqual(listed[session_id]["message_count"], 2)
        self.assertEqual(listed[session_id]["lead_count"], 0)
        messages = client.get(f"/api/sessions/{session_id}").json()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual({m["kind"] for m in messages}, {"chat"})

    def test_sessions_newest_first(self):
        first = new_session()
        second = new_session()
        ids = [s["id"] for s in client.get("/api/sessions").json()]
        self.assertLess(ids.index(second), ids.index(first))

    def test_debug_in_answers_and_history(self):
        session_id = new_session()
        debug = say_json(session_id, "Вопрос")["debug"]
        for key in ("search_seconds", "rerank_seconds", "llm_seconds", "total_seconds", "sources", "error"):
            self.assertIn(key, debug)
        self.assertEqual(debug["sources"], [SOURCE])
        messages = client.get(f"/api/sessions/{session_id}").json()
        self.assertIsNone(messages[0]["debug"])
        self.assertEqual(messages[1]["debug"]["sources"], [SOURCE])

    def test_debug_in_lead_steps_has_only_total(self):
        session_id = session_in_lead()
        debug = say_json(session_id, NAME)["debug"]
        self.assertEqual(list(debug), ["total_seconds"])

    def test_error_codes(self):
        session_id = new_session()
        self.assertEqual(say(session_id, "").status_code, 400)
        self.assertEqual(say(session_id, "   ").status_code, 400)
        self.assertEqual(say(session_id, "а" * 2001).status_code, 400)
        self.assertEqual(say(session_id, "а" * 2000).status_code, 200)
        self.assertEqual(say("unknown", "Вопрос").status_code, 404)
        self.assertEqual(client.get("/api/sessions/unknown").status_code, 404)


if __name__ == "__main__":
    unittest.main()
