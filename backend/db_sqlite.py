# backend/db_sqlite.py
import os, sqlite3, uuid
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from ml_intent import DEPTS  # {"ortopedi":"Ortopedi / FTR", ...}

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = _conn(); cur = con.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS departments(
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL
      )
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dept_code TEXT NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY(dept_code) REFERENCES departments(code)
      )
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS appointments(
        id TEXT PRIMARY KEY,
        dept_code TEXT NOT NULL,
        doctor TEXT NOT NULL,
        slot TEXT NOT NULL,          -- "YYYY-MM-DD HH:MM"
        patient TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(doctor, slot)         -- aynı doktora aynı saat çakışmasın
      )
    """)
    # seed departments
    cur.execute("SELECT COUNT(*) AS c FROM departments")
    if cur.fetchone()["c"] == 0:
        cur.executemany("INSERT INTO departments(code,name) VALUES(?,?)",
                        [(k, v) for k, v in DEPTS.items()])
    # seed doctors (örnek)
    cur.execute("SELECT COUNT(*) AS c FROM doctors")
    if cur.fetchone()["c"] == 0:
        seed = {
            "ortopedi": ["Uzm. Dr. Ayşe Yılmaz", "Op. Dr. Mert Kaya"],
            "kbb": ["Uzm. Dr. Elif Demir"],
            "kardiyoloji": ["Uzm. Dr. Can Şahin"],
            "gastro": ["Uzm. Dr. Gökhan Aksoy"],
            "dahiliye": ["Uzm. Dr. Seda Karaca"],
            "dermatoloji": ["Uzm. Dr. Burcu Kar"],
            "uroloji": ["Uzm. Dr. Emre Tunç"],
            "noroloji": ["Uzm. Dr. Nil Sezer"],
        }
        rows = []
        for code, names in seed.items():
            for n in names:
                rows.append((code, n))
        cur.executemany("INSERT INTO doctors(dept_code, name) VALUES(?,?)", rows)
    con.commit(); con.close()

def _generate_slots(start_hour=9, end_hour=16) -> List[str]:
    """Bugünden 3 gün, her saat başı slot."""
    out = []
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    for day in range(0, 3):
        base = (now + timedelta(days=day)).replace(hour=start_hour)
        for h in range(start_hour, end_hour + 1):
            ts = base.replace(hour=h)
            if ts >= now:
                out.append(ts.strftime("%Y-%m-%d %H:%M"))
    return out

def list_doctors(dept_code: str) -> List[str]:
    con = _conn(); cur = con.cursor()
    cur.execute("SELECT name FROM doctors WHERE dept_code=? ORDER BY name", (dept_code,))
    names = [r["name"] for r in cur.fetchall()]
    con.close()
    return names

def booked_set_for_dept(dept_code: str) -> set:
    con = _conn(); cur = con.cursor()
    cur.execute("""SELECT doctor, slot FROM appointments WHERE dept_code=?""", (dept_code,))
    s = {(r["doctor"], r["slot"]) for r in cur.fetchall()}
    con.close()
    return s

def availability(dept_code: str) -> List[Dict]:
    """[{doctor, slots:[...]}, ...] döner; DB’deki dolular filtrelenir."""
    docs = list_doctors(dept_code)
    all_slots = _generate_slots()
    booked = booked_set_for_dept(dept_code)
    rows = []
    for d in docs:
        free = [s for s in all_slots if (d, s) not in booked]
        rows.append({"doctor": d, "slots": free[:5]})
    return rows

def book_appointment(dept_code: str, doctor: str, slot: str, patient: str = "") -> Tuple[bool, str, Dict]:
    """Başarılıysa (True, appt_id, {}), değilse (False, hata, {})."""
    # doğrulamalar
    docs = set(list_doctors(dept_code))
    if doctor not in docs:
        return (False, "Doktor departmanda bulunamadı.", {})
    if slot not in _generate_slots():
        return (False, "Geçersiz saat.", {})

    appt_id = str(uuid.uuid4())[:8]
    try:
        con = _conn(); cur = con.cursor()
        cur.execute("""
           INSERT INTO appointments(id, dept_code, doctor, slot, patient, created_at)
           VALUES(?,?,?,?,?,?)
        """, (appt_id, dept_code, doctor, slot, patient or "", datetime.now().isoformat(timespec="seconds")))
        con.commit(); con.close()
        return (True, appt_id, {"id": appt_id, "doctor": doctor, "slot": slot})
    except sqlite3.IntegrityError:
        return (False, "Slot artık uygun değil.", {})
