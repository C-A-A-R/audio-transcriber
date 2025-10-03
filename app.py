import requests, time, os, tempfile
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv
from whatsapp_decrypt import decrypt_whatsapp_audio


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

@app.route("/transcribe", methods=["POST"])
def transcribe():
    payload = request.get_json(silent=True) or {}
    audio_url = payload.get("audio_url")
    media_key = payload.get("media_key")   # <- lo enviamos desde Evolution API webhook
    webhook_url = payload.get("webhook_url") or os.getenv("WEBHOOK_URL")

    if not audio_url:
        return jsonify({"error": "audio_url missing"}), 400

    # Si hay mediaKey, significa que es un .enc -> descifrar
    if media_key:
        try:
            audio_path = decrypt_whatsapp_audio(audio_url, media_key)
            with open(audio_path, "rb") as f:
                up = requests.post(f"{API_BASE}/upload", headers=HEADERS, data=f, timeout=120)
            up.raise_for_status()
            upload_url = up.json()["upload_url"]
            audio_url = upload_url  # sustituimos por el audio válido
            os.remove(audio_path)
        except Exception as e:
            return jsonify({"error": "failed to decrypt media", "details": str(e)}), 500

    # Ahora procesar con AssemblyAI como antes
    try:
        r = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": audio_url}, timeout=20)
        r.raise_for_status()
        transcript_id = r.json()["id"]
    except Exception as e:
        return jsonify({"error": "failed to create transcript", "details": str(e)}), 500

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
