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
BASE_URL = 'http://localhost:11434/api' #(env("LLM_BASE_URL") or env("BASE_URL") or env("OPENAI_BASE_URL")).rstrip("/")
LLM_KEY = env("LLM_API_KEY") or env("OPENAI_API_KEY")
EMB_KEY = 'embed_key' #env("EMBEDDER_API_KEY") or LLM_KEY
RERANK_KEY = env("RERANKER_API_KEY") or LLM_KEY
LLM_MODEL = env("LLM_MODEL") or env("GEN_MODEL") or env("OPENAI_MODEL", "qwen/qwen3.8-27b")
EMB_MODEL = 'bge-m3:latest' #env("EMB_MODEL", "baai/bge-m3")
RERANKER_MODEL = env("RERANKER_MODEL", "qwen/qwen3-reranker-8b")
TOP_K = 20 #number("TOP_K", 4, 1, 30)
RERANKER_TOP_N = number("RERANKER_TOP_N", 2, 1, 30)
MAX_TOKENS = number("MAX_TOKENS", 2048, 128, 8192)
MAX_WORKERS = number("MAX_WORKERS", 3, 1, 8)
TEMPERATURE = number("TEMPERATURE", 0.0, 0.0, 2.0, float)
CHUNKER = env("CHUNKER", "common")
# PYTHONPATH применяется самим Python, вручную обрабатывать его не нужно.

FALLBACK = "Не могу ответить по доступным фрагментам базы знаний."
WORD = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{4,}")

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
                chunks = chunk(text, 300, 50)
                for idx, c in enumerate(chunks):
                    documents.append({
                        'source' : name,
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
        embeddings = post(client, '/embed', EMB_KEY, body)['embeddings']
        for doc, embedding in zip(documents, embeddings): 
            result.append({**doc, 'embedding' : embedding})
    return result 


# ======= Vector Database =================================

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

def build_vdb():
    _, collection = vdb_init()
    docs = load_documents(find_file('knowledge-base.zip'))
    docs_w_embeds = get_embeddings(docs)
    save_embeddings(collection, docs_w_embeds)
    return collection 


def get_relevant_documents(collection, query):
    with httpx.Client(timeout=50) as client:
        embedding = post(client, '/embed', EMB_KEY, {'model' : EMB_MODEL, 'input' : query})['embeddings'][0]
        output = collection.query(query_embeddings=embedding, n_results=TOP_K, include=['documents', 'metadatas', 'distances'])
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

def getreadydb():
    return chromadb.PersistentClient(path='./chroma_db').get_or_create_collection(name='mts-energytool-vector-database',metadata={"hnsw:space": "cosine"})

def test_collection_with_query(collection, queries):
    for q in queries:
        responses = get_relevant_documents(collection, q)
        print(f'* Query: {q}')
        for idx, response in enumerate(responses,1):
            print(f"{idx}. Source: {response['source']}")
            print(f"Chunk_id: {response['chunk_id']}")
            print(f"Distance: {response['distance']}")
            print(f"Content: {response['content']}")
            print('='*200)
        print('\n\n')


queries = [
    'У нас крыша на два ската — восток и запад. Панели можно поставить на оба?',
    'На крыше почти нет места. А солнечные панели на фасад ставите?',
    'Можно сначала поставить солнечную станцию на 60 кВт, а потом расширить?',
    'Нам предлагают компенсировать реактивную энергию. Сначала надо что-то измерить?'
]


# ============== Making Prompt for the Generation Model ====================

def build_info_prompt(relevant_docs, n_best=3):
    result = ''
    for idx, doc in enumerate(relevant_docs[-n_best:][::-1], 1):
        with open(doc['source'], 'r', encoding='utf-8') as file:
            source_content = file.read().strip('\n ')
            subprompt = f"""{idx}.
            Название источника: {doc['source']}
            ID Чанка: {doc['chunk_id']}
            Содержание Чанка: {doc['content']}
            Расстояние до эмбеддинга запроса: {doc['distance']}
            Содержание источника: {source_content}
            """
            result += subprompt

    return result


def generate(info_prompt):

    pass 
