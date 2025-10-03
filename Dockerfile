FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Producción con gunicorn (recomendado)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app", "--workers", "2"]
