import os
import tempfile
import requests
import base64
from flask import Flask, request, jsonify
from whatsapp_decrypt import download_encrypted, decrypt_whatsapp_media
from assembly_client import transcribe_with_assemblyai
from mapper import map_model_output_to_markdown, extract_title_from_markdown
from md_to_docx import markdown_to_docx

# Variable global para la API key
API_SECRET = os.getenv("API_SECRET")

app = Flask(__name__)


def validate_api_key():
    """Valida que la API key en los headers sea correcta"""
    api_key = request.headers.get("X-API-KEY")
    if not api_key:
        return False, "X-API-KEY header requerido"
    
    if not API_SECRET:
        return False, "API_SECRET no configurado en variables de entorno"
    
    if api_key != API_SECRET:
        return False, "API key inválida"
    
    return True, "OK"


@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        # Validar API key
        is_valid, message = validate_api_key()
        if not is_valid:
            return jsonify({"error": message}), 401
        
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


@app.route("/process_model_output", methods=["POST"])
def process_model_output():
    try:
        # Validar API key
        is_valid, message = validate_api_key()
        if not is_valid:
            return jsonify({"error": message}), 401
        
        data = request.get_json(force=True)
        if not data or "model_output" not in data:
            return jsonify({"error": "missing model_output"}), 400

        # 1. Recibir valores desde n8n
        model_output = data["model_output"]
        instancia = data.get("instancia")
        number = data.get("number")
        server_url = data.get("server_url")
        apikey = data.get("apikey")

        if not (instancia and number and server_url and apikey):
            return jsonify({"error": "missing Evolution API parameters"}), 400

        # 2. Mapear tokens -> Markdown limpio
        markdown_text, _ = map_model_output_to_markdown(model_output)

        # 3. Extraer título como nombre de documento
        file_title = extract_title_from_markdown(markdown_text)
        file_name = f"{file_title}.docx"

        # 4. Crear docx temporal
        docx_path = markdown_to_docx(markdown_text)

        # 5. Convertir archivo a Base64
        with open(docx_path, "rb") as f:
            file_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 6. Armar payload para Evolution API
        url = f"{server_url}/message/sendMedia/{instancia}"
        payload = {
            "number": number,
            "mediatype": "doc",
            "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "caption": f"{file_title}",
            "media": file_b64,
            "fileName": file_name,
            "delay": 100,
            "linkPreview": False
        }
        headers = {
            "apikey": apikey,
            "Content-Type": "application/json"
        }

        # 7. Enviar documento a Evolution API
        response = requests.post(url, json=payload, headers=headers)
        resp_json = response.json()

        return jsonify({
            "status": "sent",
            "filename": file_name,
            "evolution_response": resp_json
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
