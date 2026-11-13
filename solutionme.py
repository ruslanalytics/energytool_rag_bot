import csv
import math
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import chromadb
import pandas as pd

def env(name, default=""):
    value = os.getenv(name, "").strip()
    return default if not value or value == name else value
def number(name, default, lower, upper, kind=int):
    try:
        return max(lower, min(upper, kind(env(name))))
    except ValueError:
        return default

# ================ TEMPORARY CHANGED SOME ENV VARIABLES, WILL SWITCH BACK LATER ==================
DATA_DIR = Path(env("DATA_DIR", "data"))
BASE_URL = 'http://localhost:11434/v1'#(env("LLM_BASE_URL") or env("BASE_URL") or env("OPENAI_BASE_URL")).rstrip("/")
LLM_KEY = 'llm_key' #env("LLM_API_KEY") or env("OPENAI_API_KEY")
EMB_KEY = 'emb_key' #env("EMBEDDER_API_KEY") or LLM_KEY
RERANK_KEY = env("RERANKER_API_KEY") or LLM_KEY
LLM_MODEL = ' qwen2.5:7b-instruct' # env("LLM_MODEL") or env("GEN_MODEL") or env("OPENAI_MODEL", "qwen/qwen3.8-27b")
EMB_MODEL = 'bge-m3' #env("EMB_MODEL", "baai/bge-m3")
RERANKER_MODEL = env("RERANKER_MODEL", "qwen/qwen3-reranker-8b")
TOP_K = number("TOP_K", 4, 1, 30)
RERANKER_TOP_N = number("RERANKER_TOP_N", 2, 1, 30)
MAX_TOKENS = number("MAX_TOKENS", 2048, 128, 8192)
MAX_WORKERS = number("MAX_WORKERS", 3, 1, 8)
TEMPERATURE = number("TEMPERATURE", 0.0, 0.0, 2.0, float)
CHUNKER = env("CHUNKER", "common")

def post(client, endpoint, key, body):
    if not BASE_URL or not key:
        raise ValueError("Проверьте переменные адреса API и ключа")
    for attempt in range(2):
        try:
            response = client.post(
                BASE_URL + endpoint,
                headers={"Authorization": "Bearer " + key},
                json=body,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 1:
                raise
            time.sleep(0.5)

def find_file(*names):
    for root in (DATA_DIR, Path(__file__).resolve().parent / DATA_DIR, Path.cwd()):
        for name in names:
            path = root / name
            if path.is_file():
                return path
    raise FileNotFoundError(f"Не найдены файлы: {names}")

def chunk(text, chunk_size, collision):
    text = text.split()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - collision
    return chunks

def load_documents(path):
    documents = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("__MACOSX/") or Path(name).suffix.lower() not in (".md", ".txt"):
                continue
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            if text.strip():
                chunks = chunk(text, 400, 100)
                for idx, c in enumerate(chunks):
                    documents.append({
                        'source' : name,
                        'source_content' : text, 
                        'chunk_id' : idx,
                        'content' : ' '.join(c)
                    })
    if not documents:
        raise ValueError("База знаний не содержит файлов .md или .txt")
    return documents


def get_embeddings(documents):
    result = []
    with httpx.Client(timeout=50) as client:
        texts_to_embed = [f"Источник: {doc['source']}, Содержание: {doc['content']}" for doc in documents]
        body = {'model' : EMB_MODEL, 'input' : texts_to_embed}
        embeddings = [doc['embedding'] for doc in post(client, '/embeddings', EMB_KEY, body)['data']]
        for doc, embedding in zip(documents, embeddings): 
            result.append({**doc, 'embedding' : embedding})
    return result 


# ========================= VECTOR DATABASE =================================

def vdb_init():
    client = chromadb.PersistentClient(path='./chroma_db')
    collection = client.get_or_create_collection(
        name='mts-energytool-vector-database',
        metadata={"hnsw:space": "cosine"} 
    )
    return client, collection

def save_embeddings(collection, documents_w_embeds):
    ids = []
    embeddings = []
    contents = []
    metadatas = []
    for doc in documents_w_embeds:
        ids.append(f"{doc['source']}:{doc['chunk_id']}")
        embeddings.append(doc['embedding'])
        contents.append(doc['content'])
        metadatas.append({
            "source" : doc['source'],
            "chunk_id" : doc['chunk_id']
        })
    collection.upsert(ids=ids, embeddings=embeddings, documents=contents, metadatas=metadatas)

def build_vdb(documents):
    _, collection = vdb_init()
    docs_w_embeds = get_embeddings(documents)
    save_embeddings(collection, docs_w_embeds)
    return collection 

def get_relevant_documents(collection, query):
    with httpx.Client(timeout=50) as client:
        embedding = post(client, '/embeddings', EMB_KEY, {'model' : EMB_MODEL, 'input' : query})['data'][0]['embedding']
        output = collection.query(query_embeddings=[embedding], n_results=TOP_K, include=['documents', 'metadatas', 'distances'])
        result = []
        for i in range(len(output['ids'][0])):
            result.append(
                {
                    'content' : output['documents'][0][i],
                    'source' : output['metadatas'][0][i]['source'],
                    'chunk_id' : output['metadatas'][0][i]['chunk_id'],
                    'distance' : output['distances'][0][i]
                }
            )
        return result

# ============== MAKING PROMPT AND GENERATING ANSWER  ====================
def build_info_prompt(relevant_docs, n_best=TOP_K):
    result = ''
    for idx, doc in enumerate(relevant_docs[:n_best], 1):
        subprompt = f"""{idx}.
        Название источника: {doc['source']}
        Содержание Чанка: {doc['content']}
        """
        result += subprompt
    return result


def generate(info_prompt, question):
    system_prompt = "Ты консультант МТС EnergyTool. Отвечай максимально кратко и по делу. Всегда отвечай на русском, если не попросять отвечать на другом языке. Не выдумывай факты, которых нет в предоставленных фрагментах. При низкой уверенности говори, что не можешь ответить на вопрос и задай уточняющий вопрос клиенту"
    body = { 
        'model' : LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Фрагменты базы знаний:\n" + info_prompt + "\n\nВопрос (ответь двумя-тремя предложениями. Если вопрос содержит разговор пользователя и ассистента, обязательно учитывай полный диалог. Задавай клиенту уточняющий вопрос, относящийся к делу):\n" + question},
        ],
    }
    with httpx.Client(timeout=100) as client:
        output = post(client, '/chat/completions', LLM_KEY, body)['choices'][0]['message']['content']
        return output

# ======================= THE MAIN FUNCTION ============================
def main():
    questions_path = find_file("questions.csv", "train.csv")
    kb_path = find_file("knowledge-base.zip", "knowledge_base.zip", "kb.zip")
    print('- found the questions and knowledge base')
    questions_df = pd.read_csv(questions_path, index_col='id')
    documents = load_documents(kb_path)
    print('- loaded the files')
    print(f'- {len(questions_df)} questions')
    collection = build_vdb(documents)
    print('- formed the vector database')
    questions = questions_df['question'].to_list()
    ids = questions_df.index.to_list()
    answers = []
    for idx, question in enumerate(questions, 1):
        similar_docs = get_relevant_documents(collection, question)
        info_prompt = build_info_prompt(similar_docs)
        answer = generate(info_prompt, question)
        answers.append(answer)
        print(f'{idx}. Answered the question: {question} \n - {answer}')
    answers_df = pd.DataFrame({'id' : ids, 'answer' : answers})
    answers_df.to_csv('submission.csv', index=False)

if __name__ == '__main__':
    main()
