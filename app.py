import os
import tempfile
import requests
from flask import Flask, request, jsonify

from whatsapp_decrypt import download_encrypted, decrypt_whatsapp_media
from assembly_client import transcribe_with_assemblyai

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "cambia-esta-clave")

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON recibido"}), 400

        raw_num = payload.get("data", {}).get("messages", {}).get('key', {}).get('remoteJid', "")
        numero = f"+{raw_num.split('@')[0]}" if "@" in raw_num else raw_num
        message = payload.get("data", {}).get("messages", {})
        msg = message.get("message", {}) if isinstance(message, dict) else {}

        # 📌 Caso texto simple
        if "conversation" in msg or "extendedTextMessage" in msg:
            text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text")
            return jsonify({
                "numero": numero,
                "type": "text",
                "transcription": text
            })

        # 📌 Caso audio
        audio_msg = message.get('message', {}).get("audioMessage")
        if not audio_msg:
            return jsonify({"status": "no_audio_or_text", "numero": numero}), 200

        audio_url = audio_msg.get("url")
        media_key = audio_msg.get("mediaKey")
        seconds = audio_msg.get("seconds")
        if not audio_url or not media_key:
            return jsonify({"error": "Faltan url o mediaKey en audioMessage"}), 400

        # 1) Descargar archivo .enc
        enc_bytes = download_encrypted(audio_url)

        # 2) Descifrar
        decrypted_bytes = decrypt_whatsapp_media(enc_bytes, media_key, message_type="audio")

        # 3) Guardar temporalmente el .ogg
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_file:
            tmp_file.write(decrypted_bytes)
            tmp_path = tmp_file.name

        # 4) Transcribir con AssemblyAI
        transcription = transcribe_with_assemblyai(tmp_path)

        # 5) Eliminar archivo temporal
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return jsonify({
            "numero": numero,
            "type": "audio",
            "seconds": seconds,
            "transcription": transcription
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
