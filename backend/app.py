# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, datetime
import re

from backend.ml_intent import predict_intent, predict_department
from backend.db_sqlite import init_db, availability, book_appointment

# LLM (Ollama)
from backend.llm_client import llm_reply

# RAG (sadece lab + gündelik öneri)
# backend/rag/rag_store.py dosyan olmalı
from backend.rag.rag_store import build_or_load_collection, retrieve

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})
APP_VERSION = "0.5.1"

# ---- Logger ----
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "chat.log")

def log_event(kind: str, payload: dict):
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, **payload}
    print(f"[{rec['ts']}][{kind}] {payload}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# DB init
init_db()

# ---------------------------
# RAG INIT (daily + lab)
# ---------------------------
BASE_DIR = os.path.dirname(__file__)
RAG_PERSIST_DIR = os.path.join(BASE_DIR, "ragdata")

DAILY_KNOW_DIR = os.path.join(BASE_DIR, "rag", "knowledge_daily")
LAB_KNOW_DIR   = os.path.join(BASE_DIR, "rag", "knowledge_lab")

daily_col = None
lab_col = None

try:
    daily_col = build_or_load_collection(RAG_PERSIST_DIR, "daily", DAILY_KNOW_DIR)
    lab_col   = build_or_load_collection(RAG_PERSIST_DIR, "lab",   LAB_KNOW_DIR)
except Exception as e:
    # RAG çökerse sistem çalışmaya devam etsin
    log_event("rag_init_error", {"error": str(e)})

# ---------------------------
# LAB tespiti (intent=lab zaten var ama ek güvenlik için)
# ---------------------------
LAB_PATTERNS = [
    r"\bhba1c\b", r"\bldl\b", r"\bhdl\b", r"\btrigliser", r"\bkolesterol\b",
    r"\bglukoz\b", r"\bkan\s*şekeri\b", r"\btsh\b", r"\bferritin\b",
    r"\bb12\b", r"\bd\s*vit", r"\bhemoglobin\b", r"\bhgb\b", r"\bhb\b",
    r"\btahlil\b", r"\bkan\s*sonuc", r"\blab\b"
]

def looks_like_lab(text: str) -> bool:
    t = (text or "").lower()
    for p in LAB_PATTERNS:
        if re.search(p, t):
            return True
    # sayı + birim gibi işaretler
    if re.search(r"\b\d+([.,]\d+)?\s*(mg/dl|mmol/l|iu/l|miu/l|ng/ml|pg/ml|%)\b", t):
        return True
    return False

def rag_reply(user_message: str, mode: str) -> str:
    """
    mode: "daily" veya "lab"
    Kurallı akışı bozmaz: sadece 2-4 cümlelik öneri metnini üretir.
    """
    col = lab_col if mode == "lab" else daily_col
    if col is None:
        raise RuntimeError("RAG collection not ready")

    chunks = retrieve(col, user_message, k=3)

    if mode == "lab":
        rules = (
            "SADECE Türkçe yaz. 2–4 cümle yaz. Soru sorma. "
            "İlaç ismi, doz veya tedavi önerme. "
            "Laboratuvar sonuçları kişiye göre değişebilir; genel çerçevede yorumla. "
            "Nazikçe doktorla değerlendirmeyi öner."
        )
        task = "rag_lab"
    else:
        rules = (
            "SADECE Türkçe yaz. 2–4 cümle yaz. Soru sorma. "
            "İlaç ismi, doz veya tedavi önerme. "
            "Gündelik hayatta güvenli, basit öneriler ver. "
            "Nazikçe doktora görünmeyi önerebilirsin."
        )
        task = "rag_daily"

    context_text = "\n".join([f"- {c}" for c in chunks]) if chunks else "- (Bağlam yok)"

    prompt = (
        f"{rules}\n\n"
        f"BAĞLAM:\n{context_text}\n\n"
        f"KULLANICI MESAJI:\n{user_message}\n\n"
        f"YANIT:"
    )

    # llm_client.py mevcut imzana uygun çağrı
    return llm_reply(
        user_message=prompt,
        context={"task": task}
    )

@app.get("/")
def index():
    return jsonify({"ok": True, "service": "health-chatbot-backend", "version": APP_VERSION})

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION})

@app.post("/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    user = (data.get("message") or "").strip()
    if not user:
        return jsonify({"reply": "Boş mesaj aldım.", "intent": "empty", "source": "rule-based"})

    intent = predict_intent(user)

    # --- 1) URGENT: daima rule-based (güvenlik) ---
    if intent == "urgent":
        resp = {
            "reply": (
                "Acil risk ifadesi tespit edildi. Lütfen acil durumdaysanız 112’yi arayın "
                "ve en yakın sağlık kuruluşuna başvurun. (Bu sistem tıbbi teşhis koymaz.)"
            ),
            "intent": intent,
            "source": "rule-based"
        }

    # --- 2) ROUTE: branş/slotları rule-based çıkar, açıklamayı LLM yazsın (Aynen bırakıldı) ---
    elif intent == "route":
        dept_code, dept_name = predict_department(user)

        if not dept_code:
            # Kullanıcıdan detay iste (LLM)
            try:
                reply_text = llm_reply(
                    user_message=user,
                    context={"task": "department_routing_missing"}
                )
                source = "llm"
            except Exception as e:
                reply_text = "Şikâyetini biraz daha detaylandırırsan uygun branşı önerebilirim."
                source = "rule-based"
                log_event("llm_error", {"where": "route_no_dept", "error": str(e)})

            resp = {"reply": reply_text, "intent": intent, "source": source}

        else:
            slots = availability(dept_code)

            # LLM açıklama üretsin (şablonlu ve kontrollü)
            try:
                reply_text = llm_reply(
                    user_message=user,
                    context={
                        "task": "department_routing",
                        "department": {"code": dept_code, "name": dept_name}
                    }
                )
                source = "llm"
            except Exception as e:
                reply_text = f"Ön değerlendirme: {dept_name} uygun görünebilir."
                source = "rule-based"
                log_event("llm_error", {"where": "route_with_dept", "error": str(e)})

            resp = {
                "reply": reply_text or f"Ön değerlendirme: {dept_name} uygun görünebilir.",
                "intent": intent,
                "source": source,
                "department": {"code": dept_code, "name": dept_name},
                "availability": slots
            }

    # --- 3) LAB: RAG ile daha anlamlı kısa yönlendirme (Kurallı bozulmaz) ---
    elif intent == "lab":
        try:
            # ek güvenlik: intent lab ama içerik değilse yine çalışır; sorun olmaz
            reply_text = rag_reply(user, mode="lab")
            source = "rag"
        except Exception as e:
            # RAG olmazsa mevcut LLM fallback
            try:
                reply_text = llm_reply(user_message=user, context={"task": "lab_help"})
                source = "llm"
            except Exception as e2:
                reply_text = (
                    "Laboratuvar değerleri yaş/cinsiyet/öykü bağlamında yorumlanır. "
                    "Lütfen parametre adını, değerini, birimini ve referans aralığını yaz."
                )
                source = "rule-based"
                log_event("llm_error", {"where": "lab_fallback", "error": str(e2)})

            log_event("rag_error", {"where": "lab", "error": str(e)})

        resp = {"reply": reply_text, "intent": intent, "source": source}

    # --- 4) GENERAL: gündelik öneriyi RAG ile güçlendir ---
    else:
        # Eğer mesaj açıkça lab gibi görünüyorsa intent general olsa bile lab RAG'e alabiliriz.
        # (İstersen bunu kapatırız; şimdilik akıllı davranış.)
        use_lab = looks_like_lab(user)

        try:
            if use_lab:
                reply_text = rag_reply(user, mode="lab")
                source = "rag"
                out_intent = "lab"
            else:
                reply_text = rag_reply(user, mode="daily")
                source = "rag"
                out_intent = "general"
        except Exception as e:
            # RAG olmazsa mevcut LLM fallback
            try:
                reply_text = llm_reply(user_message=user, context={"task": "general_health_info"})
                source = "llm"
                out_intent = "general"
            except Exception as e2:
                reply_text = "Şu anda yanıt üretilemiyor."
                source = "rule-based"
                out_intent = "general"
                log_event("llm_error", {"where": "general", "error": str(e2)})

            log_event("rag_error", {"where": "general", "error": str(e)})

        resp = {"reply": reply_text, "intent": out_intent, "source": source}

    log_event("chat", {"req": user, **resp})
    return jsonify(resp)

@app.post("/book")
def book():
    data = request.get_json(force=True, silent=True) or {}
    dept = (data.get("department") or {}).get("code")
    doctor = data.get("doctor")
    slot = data.get("slot")
    patient = (data.get("patient") or "").strip()

    if not (dept and doctor and slot):
        return jsonify({"ok": False, "error": "Eksik bilgi (department/doctor/slot)."}), 400

    ok, info, appt = book_appointment(dept, doctor, slot, patient)
    if not ok:
        return jsonify({"ok": False, "error": info}), 409

    reply = f"Randevu oluşturuldu: {appt['doctor']} – {appt['slot']} (Kod: {appt['id']})"
    updated = availability(dept)
    log_event("book", {"dept": dept, **appt, "patient": patient or None})

    return jsonify({
        "ok": True,
        "message": reply,
        "appointment": appt,
        "availability": updated
    })

@app.get("/debug/classify")
def debug_classify():
    text = request.args.get("text", "")
    intent = predict_intent(text)
    code, name = predict_department(text)
    return jsonify({"text": text, "intent": intent, "dept_code": code, "dept_name": name})

# Preflight
@app.route("/chat", methods=["OPTIONS"])
def chat_options():
    return ("", 204)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
