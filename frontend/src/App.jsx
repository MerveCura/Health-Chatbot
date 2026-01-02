import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Send, Clock, AlertTriangle, Check, User, MessageSquare } from 'lucide-react'; 

import './App.css'; 

// --- LOCAL STORAGE KEY'LERİ ---
const CONVERSATIONS_KEY = 'chatConversations'; 
const ACTIVE_ID_KEY = 'activeConversationId'; 
const APPOINTMENTS_KEY = 'userAppointments'; // YENİ KEY

// Sohbet verilerinin temel yapısı
const initialConversations = [{
    id: Date.now(),
    title: "İlk Sohbet",
    lastMessage: "Size nasıl yardımcı olabilirim?",
    date: new Date().toLocaleDateString('tr-TR'),
    messages: [{ role: "assistant", content: "Merhaba, HealthAssistant'a hoş geldiniz! Size nasıl yardımcı olabilirim?" }]
}];

export default function App() {
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastRoute, setLastRoute] = useState(null); 
  const boxRef = useRef(null);

  // --- STATE'LER ---
  const [conversations, setConversations] = useState(initialConversations); 
  const [activeConversationId, setActiveConversationId] = useState(initialConversations[0].id);
  const [appointments, setAppointments] = useState([]); // YENİ: Randevuları tutar
  const [viewMode, setViewMode] = useState('chat'); // YENİ: 'chat' veya 'appointments'
  
  const hist = conversations.find(c => c.id === activeConversationId)?.messages || [];

  const API_BASE_URL = window.location.host.includes('localhost') ? "http://localhost:8000" : "http://backend:8000";

  // 1. useEffect: LOCAL STORAGE'DAN YÜKLEME (Uygulama açıldığında çalışır)
  useEffect(() => {
    const stored = localStorage.getItem(CONVERSATIONS_KEY);
    const storedActiveId = localStorage.getItem(ACTIVE_ID_KEY);
    const storedAppointments = localStorage.getItem(APPOINTMENTS_KEY); // YENİ YÜKLEME
    
    if (stored) {
      const parsed = JSON.parse(stored);
      setConversations(parsed);

      if (parsed.length > 0) {
        const initialId = storedActiveId && parsed.find(c => c.id === Number(storedActiveId)) 
          ? Number(storedActiveId) 
          : parsed[parsed.length - 1].id;
        setActiveConversationId(initialId);
      } else {
        setConversations(initialConversations);
        setActiveConversationId(initialConversations[0].id);
      }
    }
    
    // YENİ: Randevuları yükle
    if (storedAppointments) {
      setAppointments(JSON.parse(storedAppointments));
    }

  }, []);

  // 2. useEffect: LOCAL STORAGE'A KAYDETME (conversations değiştiğinde çalışır)
  useEffect(() => {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    localStorage.setItem(ACTIVE_ID_KEY, activeConversationId.toString());

    // Otomatik Kaydırma
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [conversations, activeConversationId]);
  
  // 3. useEffect: RANDEVULARI LOCAL STORAGE'A KAYDETME
  useEffect(() => {
    localStorage.setItem(APPOINTMENTS_KEY, JSON.stringify(appointments));
  }, [appointments]);


  // --- YARDIMCI FONKSİYONLAR ---
  
  const updateConversation = (newMessages, lastMsg) => {
    setConversations(prev => {
      const updated = prev.map(c => 
        c.id === activeConversationId
          ? { 
              ...c, 
              messages: newMessages,
              lastMessage: lastMsg.content,
              date: new Date().toLocaleDateString('tr-TR')
            }
          : c
      );
      return updated;
    });
  };

  // Yeni View Switch fonksiyonu
  const switchViewMode = (mode, id = null) => {
      setViewMode(mode);
      setLastRoute(null); // Randevu kartını temizle
      if (mode === 'chat' && id !== null) {
          setActiveConversationId(id);
      }
  }

  
  const switchConversation = (id) => {
      switchViewMode('chat', id);
  }
  
  const startNewConversation = () => {
      const newId = Date.now();
      const newConv = {
          id: newId,
          title: "Yeni Sohbet...",
          lastMessage: "Henüz mesaj yok.",
          date: new Date().toLocaleDateString('tr-TR'),
          messages: []
      };
      setConversations(prev => [newConv, ...prev]); // Yeni sohbeti listenin başına ekle
      switchConversation(newId);
  }

  // --- SEND FONKSİYONU ---
  const send = async () => {
    if (!msg.trim() || loading) return;
    setErr("");
    setLoading(true);
    const outgoing = msg;
    const currentMessages = hist; 
    
    // Aktif görünüm sohbet değilse, sohbete geçiş yap
    if (viewMode !== 'chat') {
        setViewMode('chat');
    }

    const tempHist = [...currentMessages, { role: "user", content: outgoing }];
    updateConversation(tempHist, { role: "user", content: outgoing });
    setMsg("");
    
    if (currentMessages.length === 0) {
        setConversations(prev => prev.map(c => 
            c.id === activeConversationId
                ? { ...c, title: outgoing.substring(0, 30) + (outgoing.length > 30 ? '...' : '') }
                : c
        ));
    }

    try {
      const res = await axios.post(`${API_BASE_URL}/chat`, { 
        message: outgoing, 
        history: currentMessages 
      });
      const data = res?.data || {};
      let botText = data?.reply ?? "Cevap alınamadı.";

      if (data?.intent === "route" && data?.department && Array.isArray(data?.availability)) {
        setLastRoute({ department: data.department, availability: data.availability });
      } else {
        setLastRoute(null);
      }

      const finalHist = [...tempHist, { role: "assistant", content: botText }];
      updateConversation(finalHist, { role: "assistant", content: botText });
      
    } catch (e) {
      console.error(e);
      setErr("İstek atılamadı (CORS/bağlantı). Backend çalışıyor mu?");
      const finalHist = [...tempHist, { role: "assistant", content: "Bağlantı hatası veya backend çalışmıyor." }];
      updateConversation(finalHist, { role: "assistant", content: "Bağlantı hatası veya backend çalışmıyor." });
    } finally {
      setLoading(false);
    }
  };

  // --- BOOK FONKSİYONU GÜNCELLEMESİ (Randevu Kaydı Eklendi) ---
  const book = async (doctor, slot) => {
    if (!lastRoute?.department) return;
    setLoading(true);
    
    // ... (Randevu isteği kısmı aynen kalacak) ...
    try {
      const res = await axios.post(`${API_BASE_URL}/book`, {
        department: lastRoute.department,
        doctor,
        slot,
        patient: ""
      });
      setLoading(false);

      const currentMessages = hist; 
      const outgoingMsg = `Randevu talebi: Dr. ${doctor}, Saat: ${slot}`;

      if (!res.data?.ok) {
        // Hata durumunda
        const errorMsg = res.data?.error || "Rezervasyon yapılamadı.";
        const finalHist = [...currentMessages, { role: "user", content: outgoingMsg }, { role: "assistant", content: errorMsg }];
        updateConversation(finalHist, { role: "assistant", content: errorMsg });
        return;
      }
      
      // --- RANDEVU KAYDI VE LOCAL STORAGE GÜNCELLEMESİ ---
      const successMsg = res.data.message;
      const finalHist = [...currentMessages, { role: "user", content: outgoingMsg }, { role: "assistant", content: `✅ ${successMsg}` }];
      updateConversation(finalHist, { role: "assistant", content: successMsg }); 

      // YENİ RANDEVUYU KAYDET
      const newAppointment = {
            id: Date.now(),
            doctor: doctor,
            department: lastRoute.department.name,
            slot: slot,
            date: new Date().toLocaleDateString('tr-TR'),
            time: slot,
            status: 'Onaylandı' // veya Confirmed
        };
      setAppointments(prev => [newAppointment, ...prev]); // En üste ekle
      // -----------------------------------------------------------

      setLastRoute((prev) =>
        prev
          ? { ...prev, availability: res.data.availability || prev.availability }
          : prev
      );
    } catch (e) {
      console.error(e);
      setLoading(false);
      const finalHist = [...hist, { role: "assistant", content: "Rezervasyon sırasında kritik hata oluştu." }];
      updateConversation(finalHist, { role: "assistant", content: "Rezervasyon sırasında kritik hata oluştu." });
    }
  };


  // --- JSX RETURN BLOĞU ---
  return (
    <div className="main-layout"> 
        
        {/* --- 1. SOL YAN PANEL (SIDEBAR) --- */}
        <aside className="sidebar">
            <h3 className="sidebar-title">Sistem</h3>
            <div 
                className={`sidebar-menu-item ${viewMode === 'appointments' ? 'active' : ''}`}
                onClick={() => switchViewMode('appointments')} 
            >
                <Clock size={16} /> Randevularım ({appointments.length})
            </div>
            
            <h3 className="sidebar-title" style={{ marginTop: 20 }}>Geçmiş Sohbetler</h3>
            <div 
                className="new-chat-button"
                onClick={startNewConversation} 
            >
                <MessageSquare size={16} /> Yeni Sohbet Başlat
            </div>
            <div className="conversation-list">
                {conversations
                    .slice().sort((a, b) => b.id - a.id) 
                    .map((c) => (
                    <div 
                        key={c.id} 
                        className={`conversation-item ${c.id === activeConversationId && viewMode === 'chat' ? 'active' : ''}`}
                        onClick={() => switchConversation(c.id)} 
                    >
                        <MessageSquare size={14} style={{ flexShrink: 0, marginRight: 8 }} />
                        <div style={{ minWidth: 0, overflow: 'hidden' }}>
                            <span className="conversation-title">{c.title}</span>
                            <p className="conversation-last-message">{c.lastMessage}</p> 
                        </div>
                        <span className="conversation-date">{c.date}</span>
                    </div>
                ))}
            </div>
        </aside>

        {/* --- 2. SAĞ ANA İÇERİK ALANI --- */}
        <div className="chat-content-area">
            {/* ... (Header, Error Message JSX'i aynen kalacak) ... */}
            <header className="chat-header">
                <h2 className="title">
                    <MessageSquare className="icon-main" size={24} style={{ marginRight: 8 }} />
                    <span className="title-highlight">Health</span> Assistant
                </h2>
                <div className="disclaimer">
                    <AlertTriangle className="icon-warn" size={14} style={{ marginRight: 4 }} />
                    Acil durumlarda 112’yi arayın. Bu sistem tıbbi tavsiye vermez.
                </div>
            </header>

            {err && (
                <div className="error-message">
                    <AlertTriangle size={16} style={{ marginRight: 8 }} />
                    {err}
                </div>
            )}
            
            {/* GÖRÜNÜM KONTROLÜ */}
            {viewMode === 'chat' ? (
                <>
                    <div
                        ref={boxRef}
                        className="chat-box"
                    >
                        {hist.map((m, i) => ( 
                            <div key={i} className={`chat-bubble ${m.role}`}>
                                {m.role === "assistant" && <MessageSquare size={16} className="bubble-icon" />}
                                {m.role === "user" && <User size={16} className="bubble-icon user-icon" />}
                                <div className="bubble-content">{m.content}</div>
                            </div>
                        ))}
                        
                        {loading && !lastRoute && (
                            <div className="chat-bubble assistant loading-bubble">
                                <span className="loading-dot"></span>
                                <span className="loading-dot"></span>
                                <span className="loading-dot"></span>
                            </div>
                        )}

                        {lastRoute?.department && (
                            <div className="appointment-card">
                                {/* ... (Randevu kartı içeriği) ... */}
                                <div className="appointment-header">
                                    <Check size={20} className="header-icon" />
                                    Uygun saat seçerek randevu oluştur:
                                    <div className="appointment-subtitle">Poliklinik: {lastRoute.department.name}</div>
                                </div>
                                {lastRoute.availability.map((row, idx) => (
                                    <div key={idx} className="doctor-slot-row">
                                        <div className="doctor-name">{row.doctor}</div>
                                        <div className="slot-buttons-wrapper">
                                            {row.slots.length === 0 && <span className="no-slot">Uygun saat yok</span>}
                                            {row.slots.slice(0, 5).map((s) => (
                                                <button
                                                    key={s}
                                                    onClick={() => book(row.doctor, s)}
                                                    className="slot-button"
                                                    disabled={loading}
                                                >
                                                    <Clock size={14} style={{ marginRight: 4 }} /> {s}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    
                    {/* INPUT ALANI SADECE CHAT MODUNDA GÖRÜNÜR */}
                    <div className="input-area">
                        <input
                            value={msg}
                            onChange={(e) => setMsg(e.target.value)}
                            placeholder="Şikâyetini yaz (örn. dizimde ağrı var)..."
                            className="chat-input"
                            onKeyDown={(e) => e.key === "Enter" && send()}
                            disabled={loading}
                        />
                        <button
                            onClick={send}
                            disabled={loading}
                            className="send-button"
                        >
                            {loading ? "Gönderiliyor..." : <Send size={20} />}
                        </button>
                    </div>
                </>
            ) : (
                // --- RANDEVULARIM GÖRÜNÜMÜ ---
                <div className="appointments-view chat-box">
                    <h2>Planlanmış Randevularınız</h2>
                    {appointments.length === 0 ? (
                        <p className="no-appointment">Henüz onaylanmış aktif randevunuz bulunmamaktadır.</p>
                    ) : (
                        appointments.map(app => ( 
                            <div key={app.id} className="appointment-list-item">
                                <div className="app-icon"><Check size={20} /></div>
                                <div className="app-details">
                                    <div className="app-title">{app.department} - Dr. {app.doctor}</div>
                                    <div className="app-info">
                                        <Clock size={14} style={{ marginRight: 4 }} />
                                        **{app.date}** / {app.time}
                                    </div>
                                </div>
                                <div className={`app-status ${app.status.toLowerCase()}`}>{app.status}</div>
                            </div>
                        ))
                    )}
                </div>
            )}
        </div>
    </div>
  );
}