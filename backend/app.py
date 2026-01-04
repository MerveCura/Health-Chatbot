# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, datetime, re

from ml_intent import predict_intent, predict_department
from db_sqlite import init_db, availability, book_appointment

# LLM (EN üretim + TR çeviri)
from llm_client import llm_reply_en, translate_to_tr

# RAG
from rag.rag_store import build_or_load_collection, retrieve

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})
APP_VERSION = "0.6.0"

# ---- Logger ----
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "chat.log")

def log_event(kind: str, payload: dict):
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, **payload}
    print(f"[{rec['ts']}][{kind}] {payload}", flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# DB init
init_db()

# ---------------------------
# RAG INIT
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
    log_event("rag_init_error", {"error": str(e)})

# ---------------------------
# LAB tespiti (ek güvenlik)
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
    if re.search(r"\b\d+([.,]\d+)?\s*(mg/dl|mmol/l|iu/l|miu/l|ng/ml|pg/ml|%)\b", t):
        return True
    return False

# ---------------------------
# LLM yardımcıları (EN -> TR)
# ---------------------------
RETURN_EN_DEBUG = os.getenv("RETURN_EN_DEBUG", "0") == "1"

def llm_en_to_tr(en_text: str) -> str:
    try:
        return translate_to_tr(en_text)
    except Exception as e:
        log_event("translate_error", {"error": str(e)})
        return en_text

def generate_reply_tr(user_message: str, *, context: dict | None = None) -> tuple[str, str]:
    """
    EN üretir, TR çevirir.
    return: (tr_text, en_text)
    """
    en = llm_reply_en(user_message=user_message, context=context or {})
    tr = llm_en_to_tr(en)
    return tr, en

# ---------------------------
# RAG + LLM (EN üretim, sonra TR)
# ---------------------------
def rag_llm_tr(user_message: str, *, mode: str, extra_context: dict | None = None) -> tuple[str, str, list[str]]:
    """
    mode: "daily" | "lab"
    1) RAG retrieve
    2) LLM EN üretim (context içine RAG chunk'ları koy)
    3) TR çeviri
    """
    col = lab_col if mode == "lab" else daily_col
    if col is None:
        raise RuntimeError("RAG collection not ready")

    chunks = retrieve(col, user_message, k=3)  # list[str]
    ctx = dict(extra_context or {})
    ctx["rag_mode"] = mode
    ctx["rag_chunks"] = chunks

    prompt = (
        "Use the provided context (if any) to produce a safe, helpful reply.\n\n"
        f"USER:\n{user_message}\n\n"
        f"CONTEXT BULLETS:\n" + "\n".join([f"- {c}" for c in chunks]) + "\n\n"
        "ANSWER:"
    )

    tr, en = generate_reply_tr(prompt, context=ctx)
    return tr, en, chunks

# ---------------------------
# Routes
# ---------------------------
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

    # 1) URGENT: TR sabit (UI güvenliği)
    if intent == "urgent":
        resp = {
            "reply": (
                "Acil risk ifadesi tespit edildi. Lütfen acil durumdaysanız 112’yi arayın "
                "ve en yakın sağlık kuruluşuna başvurun. (Bu sistem tıbbi teşhis koymaz.)"
            ),
            "intent": intent,
            "source": "rule-based",
        }

    # 2) ROUTE: branşı rule-based bul, ama açıklamayı LLM+RAG ile güçlendir (A)
    elif intent == "route":
        dept_code, dept_name = predict_department(user)

        if not dept_code:
            try:
                tr, en = generate_reply_tr(
                    user_message=user,
                    context={"task": "department_routing_missing"}
                )
                resp = {"reply": tr, "intent": intent, "source": "llm"}
                if RETURN_EN_DEBUG:
                    resp["reply_en"] = en
            except Exception as e:
                log_event("llm_error", {"where": "route_no_dept", "error": str(e)})
                resp = {"reply": "Şikâyetini biraz daha detaylandırırsan uygun branşı önerebilirim.", "intent": intent, "source": "rule-based"}

        else:
            slots = availability(dept_code)

            try:
                tr, en, chunks = rag_llm_tr(
                    user,
                    mode="daily",
                    extra_context={
                        "task": "department_routing_with_rag",
                        "department": {"code": dept_code, "name": dept_name}
                    }
                )
                resp = {
                    "reply": tr,
                    "intent": intent,
                    "source": "rag+llm",
                    "department": {"code": dept_code, "name": dept_name},
                    "availability": slots,
                }
                if RETURN_EN_DEBUG:
                    resp["reply_en"] = en
                    resp["rag_chunks"] = chunks
            except Exception as e:
                log_event("rag_error", {"where": "route_with_dept", "error": str(e)})
                try:
                    tr, en = generate_reply_tr(
                        user_message=user,
                        context={"task": "department_routing", "department": {"code": dept_code, "name": dept_name}}
                    )
                    resp = {
                        "reply": tr,
                        "intent": intent,
                        "source": "llm",
                        "department": {"code": dept_code, "name": dept_name},
                        "availability": slots
                    }
                    if RETURN_EN_DEBUG:
                        resp["reply_en"] = en
                except Exception as e2:
                    log_event("llm_error", {"where": "route_with_dept_fallback", "error": str(e2)})
                    resp = {
                        "reply": f"Ön değerlendirme: {dept_name} uygun görünebilir.",
                        "intent": intent,
                        "source": "rule-based",
                        "department": {"code": dept_code, "name": dept_name},
                        "availability": slots
                    }

    # 3) LAB: RAG lab -> EN üretim -> TR
    elif intent == "lab":
        try:
            tr, en, chunks = rag_llm_tr(user, mode="lab", extra_context={"task": "lab_rag"})
            resp = {"reply": tr, "intent": intent, "source": "rag+llm"}
            if RETURN_EN_DEBUG:
                resp["reply_en"] = en
                resp["rag_chunks"] = chunks
        except Exception as e:
            log_event("rag_error", {"where": "lab", "error": str(e)})
            try:
                tr, en = generate_reply_tr(user_message=user, context={"task": "lab_help"})
                resp = {"reply": tr, "intent": intent, "source": "llm"}
                if RETURN_EN_DEBUG:
                    resp["reply_en"] = en
            except Exception as e2:
                log_event("llm_error", {"where": "lab_fallback", "error": str(e2)})
                resp = {
                    "reply": (
                        "Laboratuvar değerleri yaş/cinsiyet/öykü bağlamında yorumlanır. "
                        "Parametre adını, değerini, birimini ve referans aralığını ekleyip doktorla değerlendirmen iyi olur."
                    ),
                    "intent": intent,
                    "source": "rule-based"
                }

    # 4) GENERAL: daily RAG (lab gibi görünürse lab'a çek)
    else:
        use_lab = looks_like_lab(user)
        try:
            if use_lab:
                tr, en, chunks = rag_llm_tr(user, mode="lab", extra_context={"task": "general_looks_like_lab"})
                out_intent = "lab"
            else:
                tr, en, chunks = rag_llm_tr(user, mode="daily", extra_context={"task": "general_daily_rag"})
                out_intent = "general"

            resp = {"reply": tr, "intent": out_intent, "source": "rag+llm"}
            if RETURN_EN_DEBUG:
                resp["reply_en"] = en
                resp["rag_chunks"] = chunks

        except Exception as e:
            log_event("rag_error", {"where": "general", "error": str(e)})
            try:
                tr, en = generate_reply_tr(user_message=user, context={"task": "general_health_info"})
                resp = {"reply": tr, "intent": "general", "source": "llm"}
                if RETURN_EN_DEBUG:
                    resp["reply_en"] = en
            except Exception as e2:
                log_event("llm_error", {"where": "general_fallback", "error": str(e2)})
                resp = {"reply": "Şu anda yanıt üretilemiyor.", "intent": "general", "source": "rule-based"}

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
    # Debug reloader logları kaçırıyordu; docker için kapatıyoruz
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)
