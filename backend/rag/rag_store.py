import os
from typing import List, Tuple
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

_EMBED_MODEL = None

def _get_embedder():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _EMBED_MODEL

def _read_docs(folder: str) -> List[Tuple[str, str]]:
    docs = []
    if not os.path.isdir(folder):
        return docs
    for name in os.listdir(folder):
        if name.lower().endswith(".md"):
            path = os.path.join(folder, name)
            with open(path, "r", encoding="utf-8") as f:
                docs.append((name, f.read().strip()))
    return docs

def build_or_load_collection(persist_dir: str, collection_name: str, knowledge_dir: str):
    os.makedirs(persist_dir, exist_ok=True)
    client = chromadb.PersistentClient(
        path=persist_dir,
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_or_create_collection(name=collection_name)

    if col.count() == 0:
        docs = _read_docs(knowledge_dir)
        if not docs:
            return col
        embedder = _get_embedder()
        ids, texts, metas = [], [], []
        for i, (fname, text) in enumerate(docs):
            ids.append(f"{collection_name}-{i}-{fname}")
            texts.append(text)
            metas.append({"source": fname})
        vectors = embedder.encode(texts).tolist()
        col.add(ids=ids, documents=texts, metadatas=metas, embeddings=vectors)

    return col

def retrieve(col, query: str, k: int = 3) -> List[str]:
    embedder = _get_embedder()
    qv = embedder.encode([query]).tolist()[0]
    res = col.query(query_embeddings=[qv], n_results=k)
    docs = res.get("documents", [[]])[0]
    return [d for d in docs if d]
