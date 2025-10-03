import os
import tempfile
import requests
from flask import Flask, request, jsonify
from whatsapp_decrypt import download_encrypted, decrypt_whatsapp_media
from assembly_client import transcribe_with_assemblyai

app = Flask(__name__)

@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON recibido"}), 400

        audio_url = data.get("audio_url")
        media_key_json = data.get("media_key")
        webhook_url = data.get("webhook_url")

        if not audio_url or not media_key_json or not webhook_url:
            return jsonify({"error": "Faltan parámetros"}), 400

        # Descargar archivo .enc
        enc_bytes = download_encrypted(audio_url)

        # Descifrar archivo con media_key en JSON
        decrypted_bytes = decrypt_whatsapp_media(enc_bytes, media_key_json, "audio")

        # Guardar como archivo temporal .ogg
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_file:
            tmp_file.write(decrypted_bytes)
            tmp_path = tmp_file.name

        # Transcribir con AssemblyAI
        transcription = transcribe_with_assemblyai(tmp_path)

        # Limpiar archivo
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        # Enviar resultado a n8n
        requests.post(webhook_url, json={"transcription": transcription})

        return jsonify({"status": "ok", "transcription": transcription}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
