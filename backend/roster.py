# ⚠️ DEMO / TEST KULLANIMI
# Bu dosya yalnızca geliştirici testleri içindir.
# Gerçek randevu sistemi backend/db_sqlite.py üzerinden çalışır.



from datetime import datetime, timedelta

# dept_code -> doctors
DOCTORS = {
    "ortopedi": [
        {"id": "d1", "name": "Uzm. Dr. Ayşe Yılmaz"},
        {"id": "d2", "name": "Op. Dr. Mert Kaya"},
    ],
    "kbb": [{"id": "d3", "name": "Uzm. Dr. Elif Demir"}],
    "kardiyoloji": [{"id": "d4", "name": "Uzm. Dr. Can Şahin"}],
    "gastro": [{"id": "d5", "name": "Uzm. Dr. Gökhan Aksoy"}],
    "dahiliye": [{"id": "d6", "name": "Uzm. Dr. Seda Karaca"}],
    "dermatoloji": [{"id": "d7", "name": "Uzm. Dr. Burcu Kar"}],
    "uroloji": [{"id": "d8", "name": "Uzm. Dr. Emre Tunç"}],
    "noroloji": [{"id": "d9", "name": "Uzm. Dr. Nil Sezer"}],
}

def generate_slots(start_hour=9, end_hour=16):
    """Bugünden itibaren 3 gün, her saat başı slot üretir."""
    out = []
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    for day in range(0, 3):
        base = (now + timedelta(days=day)).replace(hour=start_hour)
        for h in range(start_hour, end_hour + 1):
            ts = base.replace(hour=h)
            if ts >= now:
                out.append(ts.strftime("%Y-%m-%d %H:%M"))
    return out

# --- basit bellek içi rezervasyon deposu ---
BOOKED = set()  # key: (doctor_name, slot_str)

def availability(dept_code: str):
    """Her doktordan 5 uygun slot döner (BOOKED filtreli)."""
    doctors = DOCTORS.get(dept_code, [])
    all_slots = generate_slots()
    rows = []
    for d in doctors:
        free = [s for s in all_slots if (d["name"], s) not in BOOKED]
        rows.append({"doctor": d["name"], "slots": free[:5]})
    return rows

def reserve(doctor_name: str, slot: str) -> bool:
    """Slot müsaitse rezerve eder; zaten doluysa False döner."""
    key = (doctor_name, slot)
    if key in BOOKED:
        return False
    BOOKED.add(key)
    return True
