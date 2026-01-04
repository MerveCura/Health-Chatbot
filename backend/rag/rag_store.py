# backend/rag/rag_store.py
import os
from typing import List
import glob

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

def _read_all_txt(folder: str) -> List[str]:
    if not folder or not os.path.isdir(folder):
        return []
    paths = sorted(glob.glob(os.path.join(folder, "*.txt")))
    docs = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    docs.append(t)
        except Exception:
            continue
    return docs

def build_or_load_collection(persist_dir: str, name: str, knowledge_dir: str):
    os.makedirs(persist_dir, exist_ok=True)

    client = chromadb.PersistentClient(path=persist_dir)
    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

    col = client.get_or_create_collection(
        name=name,
        embedding_function=embed_fn
    )

    # Koleksiyon boşsa knowledge dosyalarını yükle
    if col.count() == 0:
        docs = _read_all_txt(knowledge_dir)
        if docs:
            ids = [f"{name}-{i}" for i in range(len(docs))]
            metas = [{"source": "knowledge", "index": i} for i in range(len(docs))]
            col.add(documents=docs, ids=ids, metadatas=metas)

    return col

def retrieve(collection, query: str, k: int = 3) -> List[str]:
    if not query:
        return []
    res = collection.query(query_texts=[query], n_results=k)
    docs = res.get("documents") or [[]]
    # docs: List[List[str]]
    out = docs[0] if docs and len(docs) > 0 else []
    return [d for d in out if isinstance(d, str) and d.strip()]
