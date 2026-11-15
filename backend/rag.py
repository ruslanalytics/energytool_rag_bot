import os
import re
import sys
import time
import zipfile
from pathlib import Path

import httpx
import chromadb
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import bm25s

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
BASE_URL = (env("LLM_BASE_URL") or env("BASE_URL") or env("OPENAI_BASE_URL")).rstrip("/")
LLM_KEY = env("LLM_API_KEY") or env("OPENAI_API_KEY")
EMB_KEY = env("EMBEDDER_API_KEY") or LLM_KEY
RERANK_KEY = env("RERANKER_API_KEY") or LLM_KEY
LLM_MODEL = env("LLM_MODEL") or env("GEN_MODEL") or env("OPENAI_MODEL", "qwen/qwen3.8-27b")
EMB_MODEL = env("EMB_MODEL", "baai/bge-m3")
RERANKER_MODEL = env("RERANKER_MODEL", "qwen/qwen3-reranker-8b")
TOP_K = number("TOP_K", 4, 1, 30)
RERANKER_TOP_N = number("RERANKER_TOP_N", 2, 1, 30)
MAX_TOKENS = number("MAX_TOKENS", 2048, 128, 8192)
MAX_WORKERS = number("MAX_WORKERS", 3, 1, 8)
TEMPERATURE = number("TEMPERATURE", 0.0, 0.0, 2.0, float)
CHUNKER = env("CHUNKER", "common")

# ================ EXPERIMENT SWITCHES: change ONE of them per submission ==================
# with the values below the answers are the same as in the original version (only the protection from errors is added)
PROMPT_VERSION = 'original'  # 'original' or 'new' (new rules: no knowledge outside the chunks, specialist, no names)
SEARCH_QUERY = 'full'        # 'full' - the whole question (like the original);
                             # 'users' - last two messages of the user;
                             # 'last_turns' - last answer of the assistant + last message of the user
USE_STEMMING = False         # True - cut every word to 6 letters for bm25 (Russian endings)
USE_RERANKER = False         # True - take N_CANDIDATES chunks and let the reranker choose the best N_CONTEXT
N_CANDIDATES = 10            # how many chunks go to the reranker
N_CONTEXT = TOP_K            # how many chunks go to the LLM (the original used TOP_K)
WORKERS = 1                  # 1 - one by one (like the original); 3-4 is faster, but the API may answer 429

# ================ OUR OWN SETTINGS ==================
TIME_LIMIT = 15 * 60 # the platform stops the run after 20 minutes, keep a reserve
START_TIME = time.time()
RETRY_STATUSES = (429, 500, 502, 503, 504)
FALLBACK_ANSWER = "Не удалось подготовить ответ по базе знаний. Уточните, пожалуйста, вопрос или свяжитесь со специалистом МТС Energytool."

def post(client, endpoint, key, body, attempts=3):
    if not BASE_URL or not key:
        raise ValueError("Проверьте переменные адреса API и ключа")
    for attempt in range(attempts):
        try:
            response = client.post(
                BASE_URL + endpoint,
                headers={"Authorization": "Bearer " + key},
                json=body,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            response = None
        if response is not None and response.status_code not in RETRY_STATUSES:
            response.raise_for_status()  # other errors (400, 401...) will not get better with a retry
            return response.json()
        if attempt == attempts - 1:
            raise RuntimeError(f"API {endpoint} не ответил после {attempts} попыток")
        time.sleep(2 ** attempt)

def find_file(*names):
    for root in (DATA_DIR, Path(__file__).resolve().parent / DATA_DIR, Path.cwd()):
        for name in names:
            path = root / name
            if path.is_file():
                return path
    raise FileNotFoundError(f"Не найдены файлы: {names}")

def chunk(text, chunk_size=1000, overlap=150):
    headers_to_split = [
        ('#', 'Header 1'),
        ('##', 'Header 2'),
        ('###', 'Header 3')
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split)
    markdown_splitted = markdown_splitter.split_text(text)
    recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    recursive_splitted = recursive_splitter.split_documents(markdown_splitted)
    result = [] 
    for chunk in recursive_splitted:
        page_content = chunk.page_content
        metadata = chunk.metadata
        for h in reversed(metadata):
            level = int(h.split()[-1])
            page_content = (
                '#' * level + ' ' + metadata[h] + '\n' + page_content
            )
        result.append(page_content)
    return result

def load_documents(path):
    documents = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("__MACOSX/") or Path(name).name.startswith("."):
                continue
            if Path(name).suffix.lower() not in (".md", ".txt"):
                continue
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            if text.strip():
                chunks = chunk(text)
                for idx, c in enumerate(chunks):
                    documents.append({
                        'source' : name,
                        'chunk_id' : f'{name}_{idx}',
                        'content' : c
                    })
    if not documents:
        raise ValueError("База знаний не содержит файлов .md или .txt")
    return documents

def get_embeddings(documents, batch_size=32):
    result = []
    embeddings = []
    texts_to_embed = [f"Источник: {doc['source']}, Содержание: {doc['content']}" for doc in documents]
    with httpx.Client(timeout=50) as client:
        # many texts in one request can hit the API limit, so we send them in small batches
        for start in range(0, len(texts_to_embed), batch_size):
            body = {'model' : EMB_MODEL, 'input' : texts_to_embed[start:start + batch_size]}
            data = post(client, '/embeddings', EMB_KEY, body)['data']
            data = sorted(data, key=lambda item: item.get('index', 0))
            embeddings.extend(item['embedding'] for item in data)
    if len(embeddings) != len(documents):
        raise ValueError("Получено меньше эмбеддингов, чем документов")
    for doc, embedding in zip(documents, embeddings): 
        result.append({**doc, 'embedding' : embedding})
    return result 


# ========================= VECTOR DATABASE =================================
def vdb_init():
    # the database lives in memory: we rebuild it on every run anyway, and old files on disk could only add stale chunks
    client = chromadb.EphemeralClient()
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

def get_relevant_documents_dense(collection, query, top_n=20):
    with httpx.Client(timeout=50) as client:
        embedding = post(client, '/embeddings', EMB_KEY, {'model' : EMB_MODEL, 'input' : [query]})['data'][0]['embedding']
        output = collection.query(query_embeddings=[embedding], n_results=min(top_n, collection.count()), include=['documents', 'metadatas', 'distances'])
        result = []
        for i in range(len(output['ids'][0])):
            result.append(
                {
                    'content' : output['documents'][0][i],
                    'source' : output['metadatas'][0][i]['source'],
                    'chunk_id' : output['metadatas'][0][i]['chunk_id'],
                    #'distance' : output['distances'][0][i]
                }
            )
        return result

    
# ==============   BM25  ====================
def stem_text(text):
    if not USE_STEMMING:
        return text
    # simple replacement of stemming for Russian: lower case, "ё" -> "е", every word is cut to 6 letters
    # so "станция", "станции" and "станцией" become the same word
    words = re.findall(r'\w+', text.lower().replace('ё', 'е'))
    return ' '.join(word[:6] for word in words)

def build_bm25(documents):
    contents = [stem_text(doc['content']) for doc in documents]
    tokens = bm25s.tokenize(contents, show_progress=False)
    retriever = bm25s.BM25()
    retriever.index(tokens, show_progress=False)
    return retriever


def get_relevant_documents_kwd(retriever, query, documents, top_n=20):
    tokens = bm25s.tokenize(stem_text(query), show_progress=False)
    doc_idx, scores = retriever.retrieve(tokens, k=min(top_n, len(documents)), show_progress=False)
    result = []
    for i, score in zip(doc_idx[0], scores[0]):
        if score > 0:  # zero score means that no word of the query was found in the chunk
            result.append(documents[i])
    return result


# ==============   HYBRID SEARCH  ====================
def get_search_query(question):
    if SEARCH_QUERY == 'full':
        return question
    # a dialog comes as one text "Пользователь: ... Ассистент: ..."
    parts = re.split(r'^(Пользователь|Ассистент):[ \t]*', question.strip(), flags=re.MULTILINE)
    messages = [(role, text.strip()) for role, text in zip(parts[1::2], parts[2::2])]
    user_messages = [text for role, text in messages if role == 'Пользователь']
    assistant_messages = [text for role, text in messages if role == 'Ассистент']
    if SEARCH_QUERY == 'users':
        return ' '.join(user_messages[-2:]) or question
    return ' '.join(assistant_messages[-1:] + user_messages[-1:]) or question  # 'last_turns'

def hybrid_search(query, vector_collection, word_retriever, documents, k=60): 
    vector_result = []
    if vector_collection is not None:
        try:
            vector_result = get_relevant_documents_dense(vector_collection, query)
        except Exception as error:  # API error: search only by words
            print(f'- dense search failed, using bm25 only: {error}', file=sys.stderr)
    kwd_result = get_relevant_documents_kwd(word_retriever, query, documents)
    d = {}
    for idx, doc in enumerate(vector_result, 1):
        d[doc['chunk_id']] = {'dense' : idx, 'kwd' : None, 'rrf' : 0.0, 'source' : doc['source'], 'content' : doc['content']}
    for idx, doc in enumerate(kwd_result, 1):
        if doc['chunk_id'] not in d:
            d[doc['chunk_id']] = {'dense' : None, 'kwd' : idx, 'rrf' : 0.0, 'source' : doc['source'], 'content' : doc['content']}
        else:
            d[doc['chunk_id']]['kwd'] = idx
    for id in d.keys():
        if d[id]['dense'] != None:
            d[id]['rrf'] += 1 / (k + d[id]['dense'])
        if d[id]['kwd'] != None:
            d[id]['rrf'] += 1 / (k + d[id]['kwd'])
    result = []
    for id in d.keys():
        result.append({'chunk_id' : id, **d[id]})
    result = sorted(result, key = lambda x: x['rrf'], reverse=True)
    return result[:N_CANDIDATES if USE_RERANKER else N_CONTEXT]


# ==============   RERANKER  ====================
def rerank_documents(query, docs, top_n=None):
    top_n = top_n or N_CONTEXT
    if not USE_RERANKER or len(docs) <= top_n:
        return docs
    try:
        with httpx.Client(timeout=50) as client:
            body = {'model' : RERANKER_MODEL, 'query' : query, 'documents' : [doc['content'] for doc in docs], 'top_n' : top_n}
            output = post(client, '/rerank', RERANK_KEY, body)
        items = output.get('results') or output.get('data') or []
        items = sorted(items, key=lambda x: x.get('relevance_score', x.get('score', 0)), reverse=True)
        reranked = [docs[item['index']] for item in items if 0 <= item['index'] < len(docs)]
        return (reranked or docs)[:top_n]
    except Exception as error:  # the reranker is optional: keep the order of the hybrid search
        print(f'- reranker failed, using hybrid order: {error}', file=sys.stderr)
        return docs[:top_n]


# ============== MAKING PROMPT AND GENERATING ANSWER  ====================
def build_info_prompt(relevant_docs, n_best=TOP_K):
    result = ''
    for idx, doc in enumerate(relevant_docs, 1):
        subprompt = f"""{idx}.
        Название источника: {doc['source']}
        Содержание Чанка: {doc['content']}
        """
        result += subprompt
    return result

def remove_thinking(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)  # drop the reasoning block if the model returns it
    return text.split('<think>')[0].strip()

PROMPTS = {
    # (system prompt, header before the question)
    'original': (
        "Ты консультант МТС EnergyTool. Отвечай максимально кратко и по делу. Отвечай всегда по русски. Не выдумывай факты, которых нет в предоставленных фрагментах. При низкой уверенности говори, что не можешь ответить на вопрос и задай уточняющий вопрос клиенту",
        "\n\nВопрос (ответь двумя-тремя предложениями. Если вопрос содержит разговор пользователя и ассистента, обязательно учитывай полный диалог. Задавай клиенту уточняющий вопрос, относящийся к делу):\n",
    ),
    'new': (
        """Ты консультант МТС Energytool на сайте компании. Отвечай всегда по-русски, простыми словами и кратко: обычно 2-4 предложения, не больше 120 слов.
Правила:
1. Факты о продуктах, ценах, сроках, порогах и условиях бери только из предоставленных фрагментов. Свои знания об энергетике не используй и ничего не выдумывай.
2. Если во фрагментах нет ответа, прямо скажи об этом и предложи связаться со специалистом.
3. Если запрос неясен или не хватает данных о клиенте (тип организации, мощность, регион, приборы учёта, задача), обязательно задай один короткий уточняющий вопрос. Если ответ полный, в конце можно задать один короткий вопрос по делу, который поможет подобрать решение.
4. Если вопрос не про продукты Energytool или требует юридического заключения, точной стоимости, расчёта по конкретному объекту, технической документации или настройки приборов, скажи, что это вне твоей компетенции, и предложи связаться со специалистом.
5. Не называй клиентов, производителей и подрядчиков. Не обещай цены, сроки и результат, если этого нет во фрагментах.
6. Если в вопросе есть диалог (реплики «Пользователь:» и «Ассистент:»), отвечай на последнюю реплику пользователя с учётом всего диалога и не переспрашивай то, что клиент уже сообщил.""",
        "\n\nВопрос клиента:\n",
    ),
}

SUMMARY_PROMPT = """Составь краткое резюме диалога для менеджера пресейла МТС Energytool. Используй только то, что сказали клиент и ассистент, ничего не додумывай. Если сведений нет, пиши «не указано». Формат:
Задача клиента: ...
О компании и объекте: ... (тип, регион, мощность, приборы учёта)
Что обсуждали: ...
Подходящие продукты: ...
Что уточнить на звонке: ..."""

def generate(info_prompt, question):
    system_prompt, question_header = PROMPTS[PROMPT_VERSION]
    body = { 
        'model' : LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Фрагменты базы знаний:\n" + info_prompt + question_header + question},
        ],
    }
    with httpx.Client(timeout=100) as client:
        output = post(client, '/chat/completions', LLM_KEY, body)['choices'][0]['message'].get('content') or ''
    return remove_thinking(output)


# ==============   PIPELINE: ONE QUESTION -> ONE ANSWER  ====================
def run_pipeline(question, collection, retriever, documents):
    # the same steps for the platform (solution.py) and for the backend (get_answer)
    timings = {}
    started = time.time()
    search_query = get_search_query(question)
    candidates = hybrid_search(search_query, collection, retriever, documents)
    timings['search_seconds'] = round(time.time() - started, 2)

    started = time.time()
    similar_docs = rerank_documents(search_query, candidates)
    timings['rerank_seconds'] = round(time.time() - started, 2)

    started = time.time()
    answer = generate(build_info_prompt(similar_docs), question)
    timings['llm_seconds'] = round(time.time() - started, 2)
    return {'answer' : answer, 'docs' : similar_docs, 'timings' : timings}


# ============== FUNCTIONS FOR THE BACKEND ====================
HISTORY_LIMIT = 10  # how many last messages of the dialog go to the pipeline

def build_index(kb_path=None):
    # call it ONCE when the backend starts: it reads the knowledge base and builds both search indexes
    kb_path = kb_path or find_file("knowledge-base.zip", "knowledge_base.zip", "kb.zip")
    documents = load_documents(kb_path)
    try:
        collection = build_vdb(documents)
    except Exception as error:  # without embeddings we still can search by words
        print(f'- embeddings are unavailable, using bm25 only: {error}', file=sys.stderr)
        collection = None
    retriever = build_bm25(documents)
    return {'documents' : documents, 'collection' : collection, 'retriever' : retriever}

def dialog_to_text(messages):
    # the platform gives a dialog as one text "Пользователь: ... Ассистент: ...", the prompt is tuned for it,
    # so the backend turns its list of messages into the same text
    if len(messages) == 1:
        return messages[0]['content']
    names = {'user' : 'Пользователь', 'assistant' : 'Ассистент'}
    return '\n'.join(f"{names[m['role']]}: {m['content']}" for m in messages)

def chunk_title(content):
    # a chunk starts with its headers ("# ...", "## ...", "### ..."), they give a short title
    headers = []
    for line in content.split('\n'):
        if not line.startswith('#'):
            break
        headers.append(line.lstrip('#').strip())
    return ' > '.join(headers)

def get_answer(index, messages):
    # messages: [{'role': 'user' or 'assistant', 'content': '...'}, ...], the last one is the new message of the user.
    # It never raises: on any error the answer is FALLBACK_ANSWER and the text of the error is in 'error'.
    started = time.time()
    question = dialog_to_text(messages[-HISTORY_LIMIT:])
    try:
        result = run_pipeline(question, index['collection'], index['retriever'], index['documents'])
        error = None
    except Exception as exception:
        print(f'- error while answering: {exception}', file=sys.stderr)
        result = {'answer' : '', 'docs' : [], 'timings' : {}}
        error = str(exception)
    sources = [{'source' : doc['source'], 'chunk_id' : doc['chunk_id'],
                'title' : chunk_title(doc['content']), 'preview' : doc['content'][:300]}
               for doc in result['docs']]
    timings = {**result['timings'], 'total_seconds' : round(time.time() - started, 2)}
    return {'answer' : result['answer'] or FALLBACK_ANSWER, 'sources' : sources, 'timings' : timings, 'error' : error}

def make_summary(messages):
    # short summary of the consultation for the manager (the limit of 150 words does not apply to it)
    if not messages:
        return 'Клиент не обсуждал задачу с консультантом.'
    names = {'user' : 'Клиент', 'assistant' : 'Ассистент'}
    transcript = '\n'.join(f"{names[m['role']]}: {m['content']}" for m in messages)
    body = {
        'model' : LLM_MODEL,
        'temperature' : TEMPERATURE,
        'max_tokens' : MAX_TOKENS,
        'messages' : [
            {'role' : 'system', 'content' : SUMMARY_PROMPT},
            {'role' : 'user', 'content' : transcript},
        ],
    }
    try:
        with httpx.Client(timeout=100) as client:
            output = post(client, '/chat/completions', LLM_KEY, body)['choices'][0]['message'].get('content') or ''
        summary = remove_thinking(output)
    except Exception as error:
        print(f'- error while making the summary: {error}', file=sys.stderr)
        summary = ''
    return summary or 'Резюме не удалось составить автоматически. Диалог:\n' + transcript
