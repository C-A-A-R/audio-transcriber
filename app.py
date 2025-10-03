import os
import time
import tempfile
import requests
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

# Carga .env si existe (local) y luego variables de entorno del sistema
load_dotenv()

ASSEMBLY_API_KEY = os.getenv("ASSEMBLY_API_KEY")
if not ASSEMBLY_API_KEY:
    raise RuntimeError("Falta ASSEMBLY_API_KEY. Ponla en .env o en variables de entorno.")

API_SECRET = os.getenv("API_SECRET")  # 🔒 Nuevo: token de seguridad obligatorio
if not API_SECRET:
    raise RuntimeError("Falta API_SECRET. Define uno en .env o variables de entorno.")

API_BASE = "https://api.assemblyai.com/v2"
HEADERS = {"authorization": ASSEMBLY_API_KEY}

POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "3"))         # segundos entre sondeos
MAX_POLL_SECONDS = int(os.getenv("MAX_POLL_SECONDS", "300"))   # tiempo máximo de espera (segundos)

app = Flask(__name__)

# Middleware: validar API_SECRET en cada request (excepto /health)
@app.before_request
def check_api_key():
    if request.endpoint == "health":
        return  # /health siempre accesible
    token = request.headers.get("X-API-KEY")
    if token != API_SECRET:
        abort(401)  # Unauthorized

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/transcribe", methods=["POST"])
def transcribe():
    """
    POST JSON esperado:
    {
      "audio_url": "https://mmg.whatsapp.net/....enc",
      "webhook_url": "https://mi-n8n/webhook"    # opcional, sobrescribe WEBHOOK_URL en .env
    }

    Además, el request debe incluir:
    Header: X-API-KEY=<API_SECRET>
    """
    payload = request.get_json(silent=True) or {}
    audio_url = payload.get("audio_url")
    webhook_url = payload.get("webhook_url") or os.getenv("WEBHOOK_URL")

    if not audio_url:
        return jsonify({"error": "audio_url missing"}), 400

    transcript_id = None

    # 1) Intentar crear transcripción indicando la URL directamente
    try:
        r = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": audio_url}, timeout=20)
        r.raise_for_status()
        transcript_id = r.json()["id"]
    except Exception:
        # 2) Fallback: descargar y subir el archivo a AssemblyAI
        tmp_path = None
        try:
            with requests.get(audio_url, stream=True, timeout=30) as dl:
                dl.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    for chunk in dl.iter_content(chunk_size=8192):
                        if chunk:
                            tmp.write(chunk)
                    tmp_path = tmp.name

            with open(tmp_path, "rb") as f:
                up = requests.post(f"{API_BASE}/upload", headers=HEADERS, data=f, timeout=120)
            up.raise_for_status()
            upload_url = up.json()["upload_url"]

            r2 = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": upload_url}, timeout=20)
            r2.raise_for_status()
            transcript_id = r2.json()["id"]

        except Exception as e2:
            return jsonify({"error": "failed to create transcript", "details": str(e2)}), 500
        finally:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    # Polling
    polling_endpoint = f"{API_BASE}/transcript/{transcript_id}"
    start = time.time()
    while True:
        t = requests.get(polling_endpoint, headers=HEADERS, timeout=20).json()
        status = t.get("status")
        if status == "completed":
            result = {"id": transcript_id, "text": t.get("text"), "raw": t}
            # si webhook_url está definido, lo notificamos
            if webhook_url:
                try:
                    requests.post(webhook_url, json=result, timeout=10)
                except Exception as e:
                    result["_webhook_error"] = str(e)
            return jsonify(result), 200
        elif status == "error":
            return jsonify({"error": "transcription_error", "details": t.get("error")}), 500
        elif time.time() - start > MAX_POLL_SECONDS:
            return jsonify({"error": "timeout_waiting_transcript"}), 504
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
