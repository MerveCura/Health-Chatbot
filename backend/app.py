# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, datetime

from ml_intent import predict_intent, predict_department
from db_sqlite import init_db, availability, book_appointment

# LLM (Ollama)
from llm_client import llm_reply

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

    # --- 2) ROUTE: branş/slotları rule-based çıkar, açıklamayı LLM yazsın ---
    elif intent == "route":
        dept_code, dept_name = predict_department(user)

        if not dept_code:
            # Kullanıcıdan detay iste (LLM)
            try:
                reply_text = llm_reply(
                    user_message=user,
                    context={
                        "task": "department_routing_missing"
                    }
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

    # --- 3) LAB: LLM kısa yönlendirme yazsın ---
    elif intent == "lab":
        try:
            reply_text = llm_reply(
                user_message=user,
                context={"task": "lab_help"}
            )
            source = "llm"
        except Exception as e:
            reply_text = (
                "Laboratuvar değerleri yaş/cinsiyet/öykü bağlamında yorumlanır. "
                "Lütfen parametre adını, değerini, birimini ve referans aralığını yaz."
            )
            source = "rule-based"
            log_event("llm_error", {"where": "lab", "error": str(e)})

        resp = {"reply": reply_text, "intent": intent, "source": source}

    # --- 4) GENERAL: direkt LLM ---
    else:
        try:
            reply_text = llm_reply(
                user_message=user,
                context={"task": "general_health_info"}
            )
            source = "llm"
        except Exception as e:
            reply_text = "Şu anda yanıt üretilemiyor."
            source = "rule-based"
            log_event("llm_error", {"where": "general", "error": str(e)})

        resp = {"reply": reply_text, "intent": "general", "source": source}

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
