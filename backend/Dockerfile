FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data models logs

EXPOSE 8000

# app.py /app altında olduğu için backend.app değil:
CMD ["python", "app.py"]
