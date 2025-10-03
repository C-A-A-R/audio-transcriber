# app.py
import os
import time
import requests
from flask import Flask, request, jsonify
from whatsapp_decrypt import decrypt_whatsapp_audio, parse_media_key
from conect_assemblyai import upload_to_assemblyai, create_transcription, wait_for_transcription 

app = Flask(__name__)


@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json(force=True)

        audio_url = payload.get("audio_url")
        media_key = payload.get("media_key")   
        webhook_url = payload.get("webhook_url") or os.getenv("WEBHOOK_URL")

        # Convertir la media key a bytes
        media_key = parse_media_key(media_key_str)

        # Descargar archivo .enc
        resp = requests.get(audio_url)
        resp.raise_for_status()
        enc_data = resp.content

        # Desencriptar audio
        audio_data = decrypt_whatsapp_audio(enc_data, media_key)

        # Guardar archivo desencriptado
        out_file = "/tmp/output.ogg"
        with open(out_file, "wb") as f:
            f.write(audio_data)

        # Subir a AssemblyAI
        upload_url = upload_to_assemblyai(out_file)

        # Crear transcripción
        transcript_id = create_transcription(upload_url)

        # Esperar resultado
        transcript_text = wait_for_transcription(transcript_id)

        # Enviar a n8n
        requests.post(webhook_url, json={"transcript": transcript_text})

        return jsonify({"status": "ok", "transcript": transcript_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
