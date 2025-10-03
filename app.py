import os
import time
import tempfile
import base64
import requests
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv
from decrypt_whatsapp_audio import decrypt_audio

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
        "media_key": "<base64 o hex> | {"0":152,...} | [152,...],
        "webhook_url": "https://mi-n8n/webhook"    # opcional, sobrescribe WEBHOOK_URL en .env
    }

    Además, el request debe incluir:
    Header: X-API-KEY=<API_SECRET>
    """
    payload = request.get_json(silent=True) or {}
    audio_url = payload.get("audio_url")
    media_key_raw = payload.get("media_key")
    webhook_url = payload.get("webhook_url") or os.getenv("WEBHOOK_URL")

    if not audio_url:
        return jsonify({"error": "audio_url missing"}), 400

    transcript_id = None

    # Si es un .enc de WhatsApp y tenemos media_key, desencriptamos y subimos los bytes
    if (audio_url and audio_url.endswith('.enc')):
        if media_key_raw is None:
            return jsonify({"error": "media_key missing for .enc audio"}), 400
        # Soportar media_key en varios formatos: base64, hex, dict {"0":..}, lista [..]
        try:
            media_key_bytes = None
            if isinstance(media_key_raw, str):
                if all(c in '0123456789abcdefABCDEF' for c in media_key_raw) and len(media_key_raw) % 2 == 0:
                    media_key_bytes = bytes.fromhex(media_key_raw)
                else:
                    media_key_bytes = base64.b64decode(media_key_raw)
            elif isinstance(media_key_raw, dict):
                # Ordenar por índice numérico de las claves
                items = sorted(((int(k), v) for k, v in media_key_raw.items()), key=lambda x: x[0])
                values = [v for _, v in items]
                if not all(isinstance(v, int) and 0 <= v <= 255 for v in values):
                    raise ValueError("media_key dict values must be 0..255 integers")
                media_key_bytes = bytes(values)
            elif isinstance(media_key_raw, list):
                if not all(isinstance(v, int) and 0 <= v <= 255 for v in media_key_raw):
                    raise ValueError("media_key list values must be 0..255 integers")
                media_key_bytes = bytes(media_key_raw)
            else:
                raise ValueError("unsupported media_key type")

            if len(media_key_bytes) != 32:
                raise ValueError("media_key must be 32 bytes length")
        except Exception as e:
            return jsonify({"error": "invalid_media_key_format", "details": str(e)}), 400

        try:
            decrypted_bytes = decrypt_audio(media_key_bytes, audio_url)
        except Exception as e:
            return jsonify({"error": "decrypt_failed", "details": str(e)}), 400

        # Subir bytes a AssemblyAI /upload
        try:
            up = requests.post(f"{API_BASE}/upload", headers=HEADERS, data=decrypted_bytes, timeout=180)
            up.raise_for_status()
            upload_url = up.json()["upload_url"]

            r2 = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": upload_url}, timeout=20)
            r2.raise_for_status()
            transcript_id = r2.json()["id"]
        except Exception as e2:
            return jsonify({"error": "failed_to_upload_decrypted", "details": str(e2)}), 500
    else:
        # Flujo original: intentar con URL directa y si falla, subir archivo descargado
        try:
            r = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": audio_url}, timeout=20)
            r.raise_for_status()
            transcript_id = r.json()["id"]
        except Exception:
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
                    up = requests.post(f"{API_BASE}/upload", headers=HEADERS, data=f, timeout=180)
                up.raise_for_status()
                upload_url = up.json()["upload_url"]

                r2 = requests.post(f"{API_BASE}/transcript", headers=HEADERS, json={"audio_url": upload_url}, timeout=20)
                r2.raise_for_status()
                transcript_id = r2.json()["id"]

            except Exception as e2:
                return jsonify({"error": "failed_to_create_transcript", "details": str(e2)}), 500
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
