# backend/ml_intent.py
# Intent + branş tespiti (kombinasyon mantığı, Türkçe karakter normalizasyonu)

from typing import Optional, Tuple, Dict, Any


def normalize(s: str) -> str:
    t = (s or "").casefold()
    tr = {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
          "â": "a", "î": "i", "û": "u", "é": "e"}
    for k, v in tr.items():
        t = t.replace(k, v)
    # noktalama/çift boşlukları sadeleştirme
    for ch in ",.;:!?()[]{}'\"":
        t = t.replace(ch, " ")
    t = " ".join(t.split())
    return t


def contains_any(t: str, words) -> bool:
    return any(w in t for w in words)


def contains_all(t: str, words) -> bool:
    return all(w in t for w in words)


DEPTS = {
    "ortopedi":    "Ortopedi / Fizik Tedavi",
    "kbb":         "Kulak Burun Boğaz",
    "kardiyoloji": "Kardiyoloji",
    "gastro":      "Gastroenteroloji",
    "dahiliye":    "Dahiliye (İç Hastalıkları)",
    "dermatoloji": "Dermatoloji",
    "uroloji":     "Üroloji",
    "noroloji":    "Nöroloji",
}


# --- intent desenleri ---
def is_urgent(t: str) -> bool:
    # göğüs + (ağrı|baskı|sıkışma)
    if (("gogus" in t or "gogsum" in t or "gogsumde" in t) and contains_any(t, ["agri", "baski", "sikisma"])):
        return True

    # nefes darlığı / nefes almakta zorlanma varyantları
    if ("nefes" in t and contains_any(t, [
        "darl",          # nefes darligi, daraliyor
        "zor",           # nefes zor
        "zorlan",        # nefes almakta zorlaniyorum
        "alam",          # nefes alamiyorum
        "yetmiyor",      # nefes yetmiyor
        "tikan"          # tikanir gibi
    ])):
        return True

    if contains_any(t, ["bayil", "suur kayb", "felc"]):
        return True
    if contains_any(t, ["ani gorme kaybi", "ani gorme bozuklugu"]):
        return True
    return False


def looks_like_lab(t: str) -> bool:
    """
    Basit laboratuvar cümlelerini tespit eder:
    örnek: 'tahlil', 'sonuç', 'kolesterol', 'şeker', 'kan değeri' vb.
    """
    keywords = [
        "tahlil", "sonuc", "sonuç", "test", "deger", "değer",
        "kan", "kolesterol", "seker", "şeker", "glukoz",
        "trigliserid", "vitamin", "hemogram"
    ]
    return any(k in t for k in keywords)


# --- branş kombinasyonları ---
def predict_department(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = normalize(text)

    # Kardiyoloji
    if (("gogus" in t or "gogsum" in t or "gogsumde" in t) and contains_any(t, ["agri", "baski", "sikisma"])) \
       or contains_any(t, ["kalp carpinti"]) \
       or ("nefes" in t and contains_any(t, ["darl", "zor", "zorlan", "alam", "yetmiyor", "tikan"])):
        return ("kardiyoloji", DEPTS["kardiyoloji"])

    # KBB
    if ("bogaz" in t and contains_any(t, ["agri", "yan"])) \
       or ("kulak" in t and contains_any(t, ["agri", "akinti", "tikan"])) \
       or ("burun" in t and "tikan" in t) \
       or contains_any(t, ["sinuzit", "geniz akinti", "ses kisik"]):
        return ("kbb", DEPTS["kbb"])

    # Gastro
    if ("mide" in t and contains_any(t, ["agri", "bulant", "eksime", "ekşime", "yanma"])) \
       or ("karin" in t and contains_any(t, ["agri", "siskin", "siskinlik"])) \
       or contains_any(t, ["ishal", "kabiz", "reflu", "gaz sanci", "gaz sancisi"]):
        return ("gastro", DEPTS["gastro"])

    # Dermatoloji
    if contains_any(t, ["dokuntu", "kizin", "kasin", "egzama", "akne", "sivilce", "kurdesen", "mant"]):
        return ("dermatoloji", DEPTS["dermatoloji"])

    # Üroloji
    if ("idrar" in t and contains_any(t, ["yan", "yanma", "yaniyor", "yakarak", "zor", "kanli"])) \
       or ("bobrek" in t and contains_any(t, ["agri", "tas", "tasi"])):
        return ("uroloji", DEPTS["uroloji"])

    # Nöroloji
    if contains_any(t, ["migren"]) \
       or (("bas" in t) and contains_any(t, ["agri", "don"])) \
       or contains_any(t, ["uyusma", "nobet", "kasilma", "titreme"]):
        return ("noroloji", DEPTS["noroloji"])

    # Ortopedi / FTR
    if contains_any(t, ["diz", "omuz", "dirsek", "bilek", "ayak bilegi"]) \
       or (contains_any(t, ["bel", "boyun"]) and "agri" in t) \
       or contains_any(t, ["kirilma", "cikik", "burkul", "kas yirt", "kas zorlan"]):
        return ("ortopedi", DEPTS["ortopedi"])

    # Dahiliye – genel semptomlar
    if contains_any(t, ["ates", "halsiz", "yorgunluk", "usume titreme", "soguk algin", "grip"]):
        return ("dahiliye", DEPTS["dahiliye"])

    return (None, None)


ROUTE_TRIG = ["poliklinik oner", "hangi brans", "hangi doktora", "brans oner", "yonlendir", "poliklinik hangisi"]


def predict_intent(text: str) -> str:
    t = normalize(text)

    # 1) Acil
    if is_urgent(t):
        return "urgent"

    # 2) Lab/tahlil
    if looks_like_lab(t):
        return "lab"

    # 3) Branş (route) — code varsa
    code, _ = predict_department(text)
    if code:
        return "route"

    # 4) Diğer
    return "general"


def classify(text: str) -> Dict[str, Any]:
    """
    Debug/test amaçlı tek fonksiyon:
    - intent (urgent/lab/route/general)
    - urgent flag
    - lab flag
    - department_code / department_name (acil olsa bile döndürür)
    """
    raw = text or ""
    t = normalize(raw)

    urgent_flag = is_urgent(t)
    lab_flag = looks_like_lab(t)

    intent = predict_intent(raw)

    # ✅ Güncelleme: acil durumda da branş tahmini yap
    dept_code, dept_name = predict_department(raw)

    return {
        "raw": raw,
        "normalized": t,
        "intent": intent,
        "urgent": urgent_flag,
        "lab": lab_flag,
        "department_code": dept_code,
        "department_name": dept_name,
    }
