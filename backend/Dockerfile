# Python imajı
FROM python:3.11-slim

# Çalışma dizini
WORKDIR /app

# Sadece requirements'ı kopyala ve paketleri kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Geri kalan backend dosyalarını kopyala
COPY . .

# Uygulama 0.0.0.0:8000'de çalışsın
EXPOSE 8000

# Container başlarken çalışacak komut
CMD ["python", "app.py"]
