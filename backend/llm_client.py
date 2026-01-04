# backend/llm_client.py
import os
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

EN_SYSTEM = """
You are a calm, friendly health support assistant.

STRICT RULES:
- Write ONLY in English.
- 2–4 sentences.
- Do NOT ask questions.
- Do NOT suggest medications, dosages, or treatments.
- Give safe, everyday self-care suggestions.
- You may gently suggest seeing a doctor at the end.
"""

TR_TRANSLATE_SYSTEM = """
Sen Türkçe konuşan, sakin ve samimi bir sağlık destek asistanısın.

KURALLAR (KESİN):
- SADECE Türkçe yaz.
- 2–4 cümle yaz.
- Soru sorma.
- İlaç ismi, doz veya tedavi önerme.
- Gündelik hayatta güvenli, basit öneriler ver.
- En sonda nazikçe doktora görünmeyi önerebilirsin.
- İngilizce kelime kullanma.
"""

def _ollama_generate(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    text = (data.get("response") or "").strip()
    if not text:
        return "Şu anda yanıt üretilemiyor."
    return text

def llm_reply_en(user_message: str, context: dict | None = None) -> str:
    ctx = ""
    if context:
        ctx = f"\n\n[CONTEXT]\n{context}\n"
    prompt = f"{EN_SYSTEM}\n{ctx}\nUser message:\n{user_message}\n\nAnswer:"
    return _ollama_generate(prompt)

def translate_to_tr(english_text: str) -> str:
    prompt = (
        f"{TR_TRANSLATE_SYSTEM}\n\n"
        f"Aşağıdaki metni kurallara uyarak Türkçeye çevir:\n"
        f"{english_text}\n\nTürkçe yanıt:"
    )
    return _ollama_generate(prompt)
