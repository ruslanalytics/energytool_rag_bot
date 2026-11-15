import re

import rag
import storage

OFFER_TEXT = "Если хотите, передам заявку менеджеру. Для этого нужны ФИО, телефон и название компании. Напишите «да», и я оформлю заявку."
FIRST_QUESTION = "Оформим заявку менеджеру. Укажите, пожалуйста, ФИО. Используйте только тестовые данные. Чтобы отменить, напишите «отмена»."
PHONE_QUESTION = "Укажите, пожалуйста, телефон, например +7 900 000-00-00."
PHONE_RETRY = "Не получилось распознать номер: нужно от 10 до 15 цифр. Пример: +7 900 000-00-00."
COMPANY_QUESTION = "Укажите, пожалуйста, название компании."
CANCEL_REPLY = "Заявку отменил. Можем продолжить консультацию."
DONE_START = "Заявка передана менеджеру. Резюме диалога:\n"
DONE_END = "\n\nМожем продолжить консультацию."

START_RE = re.compile(
    r"заявк|перезвон|позвон|связаться с менеджером|свяжитесь со мной|свяжитесь",
    re.IGNORECASE,
)
YES_RE = re.compile(
    r"\W*((да|давайте|хорошо|ок|окей|конечно|согласен|согласна|можно)\W*)+",
    re.IGNORECASE,
)
CANCEL_RE = re.compile(
    r"\W*((отмена|отменить|не надо|передумал|стоп)\W*)+",
    re.IGNORECASE,
)


def is_cancel(text):
    return CANCEL_RE.fullmatch(text) is not None


def valid_phone(text):
    digits = re.sub(r"\D", "", text)
    return 10 <= len(digits) <= 15


def last_assistant_message(session_id):
    for message in reversed(storage.get_messages(session_id)):
        if message["role"] == "assistant":
            return message["content"]
    return ""


def wants_lead(session_id, text):
    if START_RE.search(text):
        return True
    if YES_RE.fullmatch(text):
        return OFFER_TEXT in last_assistant_message(session_id)
    return False


def should_offer(session, session_id):
    if session["lead_offered"]:
        return False
    user_messages = [m for m in storage.get_messages(session_id, "chat") if m["role"] == "user"]
    return len(user_messages) >= 2


def chat_history(session_id):
    history = []
    for message in storage.get_messages(session_id, "chat"):
        content = message["content"].replace(OFFER_TEXT, "").strip()
        history.append({"role": message["role"], "content": content})
    return history


def start_lead(session_id):
    storage.update_session(session_id, state="lead_name", lead_offered=1)
    return FIRST_QUESTION


def finish_lead(session, company):
    session_id = session["id"]
    summary = rag.make_summary(chat_history(session_id))
    storage.save_lead(session_id, session["lead_name"], session["lead_phone"], company, summary)
    storage.update_session(session_id, state="chat", lead_name=None, lead_phone=None)
    return DONE_START + summary + DONE_END


def handle_step(session, text):
    session_id = session["id"]
    if is_cancel(text):
        storage.update_session(session_id, state="chat", lead_name=None, lead_phone=None)
        return CANCEL_REPLY
    if session["state"] == "lead_name":
        storage.update_session(session_id, state="lead_phone", lead_name=text)
        return PHONE_QUESTION
    if session["state"] == "lead_phone":
        if not valid_phone(text):
            return PHONE_RETRY
        storage.update_session(session_id, state="lead_company", lead_phone=text)
        return COMPANY_QUESTION
    return finish_lead(session, text)
