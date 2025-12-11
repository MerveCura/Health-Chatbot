import { useState, useEffect, useRef } from "react";
import axios from "axios";

export default function App() {
  const [msg, setMsg] = useState("");
  const [hist, setHist] = useState([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastRoute, setLastRoute] = useState(null); // {department, availability}
  const boxRef = useRef(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [hist]);

  const send = async () => {
    if (!msg.trim() || loading) return;
    setErr("");
    setLoading(true);
    const outgoing = msg;

    try {
      const res = await axios.post("http://localhost:8000/chat", { message: outgoing });
      const data = res?.data || {};
      let botText = data?.reply ?? "Cevap alınamadı.";

      // Route ise departman ve uygunlukları kaydet, ekranda listele
      if (data?.intent === "route" && data?.department && Array.isArray(data?.availability)) {
        setLastRoute({ department: data.department, availability: data.availability });

        const lines = [];
        lines.push(`\n→ Poliklinik: ${data.department.name}`);
        data.availability.forEach((row) => {
          const first3 = (row.slots || []).slice(0, 3).join(", ");
          lines.push(`- ${row.doctor}: ${first3}`);
        });
        botText += "\n" + lines.join("\n");
      } else {
        setLastRoute(null);
      }

      setHist((h) => [...h, { role: "user", content: outgoing }, { role: "assistant", content: botText }]);
      setMsg("");
    } catch (e) {
      console.error(e);
      setErr("İstek atılamadı (CORS/bağlantı). Backend çalışıyor mu?");
      setHist((h) => [...h, { role: "assistant", content: "Bağlantı hatası veya backend çalışmıyor." }]);
    } finally {
      setLoading(false);
    }
  };

  const book = async (doctor, slot) => {
    if (!lastRoute?.department) return;
    try {
      const res = await axios.post("http://localhost:8000/book", {
        department: lastRoute.department,
        doctor,
        slot,
        patient: "" // istersen buraya isim alıp gönderebilirsin
      });

      if (!res.data?.ok) {
        setHist((h) => [...h, { role: "assistant", content: res.data?.error || "Rezervasyon yapılamadı." }]);
        return;
      }

      // onay mesajını göster
      const msg = res.data.message;
      setHist((h) => [...h, { role: "assistant", content: `✅ ${msg}` }]);

      // ekrandaki slot butonlarını güncelle
      setLastRoute((prev) =>
        prev
          ? { ...prev, availability: res.data.availability || prev.availability }
          : prev
      );
    } catch (e) {
      console.error(e);
      setHist((h) => [...h, { role: "assistant", content: "Rezervasyon sırasında hata oluştu." }]);
    }
  };

  return (
    <div style={{ maxWidth: 860, margin: "40px auto", fontFamily: "system-ui" }}>
      <h2 style={{ color: "#e8f0ff" }}>🩺 Health Chatbot (MVP)</h2>
      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8, color: "#e8e8e8" }}>
        Acil durumlarda 112’yi arayın. Bu sistem tıbbi tavsiye vermez.
      </div>

      {err && (
        <div
          style={{
            background: "#fff3cd",
            border: "1px solid #ffeeba",
            padding: 8,
            borderRadius: 6,
            marginBottom: 8,
            color: "#000",
          }}
        >
          {err}
        </div>
      )}

      <div
        ref={boxRef}
        style={{
          border: "1px solid #ddd",
          padding: 16,
          borderRadius: 8,
          minHeight: 280,
          maxHeight: 420,
          overflowY: "auto",
          background: "#f8f9fa",
          color: "#000",
          whiteSpace: "pre-wrap",
        }}
      >
        {hist.map((m, i) => (
          <div
            key={i}
            style={{
              margin: "8px 0",
              padding: "8px 10px",
              borderRadius: 12,
              background: m.role === "user" ? "#DCF8C6" : "#EAEAEA",
              color: "#000",
              maxWidth: "90%",
            }}
          >
            <b>{m.role === "user" ? "Sen" : "Bot"}:</b> {m.content}
          </div>
        ))}

        {/* Route cevabı geldiyse slot butonları */}
        {lastRoute?.department && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              Uygun saat seçerek randevu oluştur:
              <div style={{ opacity: 0.7, fontWeight: 400 }}>
                Poliklinik: {lastRoute.department.name}
              </div>
            </div>
            {lastRoute.availability.map((row, idx) => (
              <div key={idx} style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{row.doctor}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {row.slots.length === 0 && <span style={{ opacity: 0.6 }}>Uygun saat yok</span>}
                  {row.slots.slice(0, 5).map((s) => (
                    <button
                      key={s}
                      onClick={() => book(row.doctor, s)}
                      style={{
                        border: "1px solid #888",
                        borderRadius: 6,
                        padding: "6px 10px",
                        background: "#2b2b2b",
                        color: "#fff",
                        cursor: "pointer",
                        transition: "0.2s",
                        fontSize: "13px",
                        fontWeight: 500,
                      }}
                      onMouseEnter={(e) => (e.target.style.background = "#4CAF50")}
                      onMouseLeave={(e) => (e.target.style.background = "#2b2b2b")}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Şikâyetini yaz (örn. dizimde ağrı var)..."
          style={{
            flex: 1,
            padding: 10,
            borderRadius: 6,
            border: "1px solid #ccc",
            background: "#1f1f1f",
            color: "#fff",
          }}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={loading}
        />
        <button
          onClick={send}
          disabled={loading}
          style={{
            background: loading ? "#6aa76d" : "#4CAF50",
            color: "white",
            border: "none",
            borderRadius: 6,
            padding: "10px 16px",
            cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "Gönderiliyor..." : "Gönder"}
        </button>
      </div>
    </div>
  );
}
