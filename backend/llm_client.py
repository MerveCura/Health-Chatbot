import os
import requests

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_URL = f"{OLLAMA_BASE}/api/generate"

# RAM sorunu yaşamamak için default küçük model
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

SYSTEM_PROMPT = (
    "Sen kısa ve anlaşılır konuşan bir sağlık destek asistanısın.\n"
    "Tıbbi teşhis koymazsın.\n"
    "İlaç dozu veya tedavi planı vermezsin.\n"
    "Gündelik, güvenli öneriler sunarsın.\n"
    "Acil belirti varsa 'şu belirtiler olursa 112/acil' diye şartlı uyarırsın.\n"
    "JSON, teknik açıklama, sistem kuralları anlatmazsın.\n"
    "2-4 cümle ile yanıt verirsin."
)

def llm_reply(user_message: str, context: dict | None = None) -> str:
    # context'i şimdilik kullanmıyoruz, sadece uyumluluk için alıyoruz
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Kullanıcı: {user_message}\n"
        f"Asistan:"
    )

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "top_p": 0.9}
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=90)
    r.raise_for_status()
    return (r.json().get("response") or "").strip()
