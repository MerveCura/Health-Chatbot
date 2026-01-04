import os
import requests

# ---- Config ----
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

def _guess_ollama_url() -> str:
    """
    Priority:
    1) OLLAMA_URL env
    2) If running inside docker -> host.docker.internal
    3) Local fallback -> 127.0.0.1
    """
    env_url = os.getenv("OLLAMA_URL")
    if env_url:
        return env_url.rstrip("/")

    # Docker tespiti (yaygın)
    in_docker = os.path.exists("/.dockerenv") or os.getenv("RUNNING_IN_DOCKER") == "1"
    if in_docker:
        return "http://host.docker.internal:11434"

    return "http://127.0.0.1:11434"

OLLAMA_URL = _guess_ollama_url()

def llm_reply(user_message: str, context: dict | None = None) -> str:
    """
    Ollama /api/generate ile kısa yanıt üretir.
    Hata fırlatır -> app.py yakalayıp rule-based'e düşer.
    """
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": user_message,
        "stream": False,
        # İstersen biraz "daha tutarlı" olsun diye:
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
        }
    }

    # context'i prompta gömmek istiyorsan burada birleştir (senin app.py zaten prompt hazırlıyor)
    # O yüzden burada ekstra bir şey yapmıyoruz.
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()
    except Exception:
        # burayı app.py logluyor zaten; hatayı yukarı fırlat
        raise
