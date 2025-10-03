import requests
import time
import os

ASSEMBLY_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
HEADERS = {"authorization": ASSEMBLY_API_KEY}


def upload_to_assemblyai(audio_path: str) -> str:
    """Sube el audio a AssemblyAI y devuelve el upload_url"""
    with open(audio_path, "rb") as f:
        response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=HEADERS,
            data=f
        )
    response.raise_for_status()
    return response.json()["upload_url"]


def create_transcription(upload_url: str) -> str:
    """Crea la transcripción en AssemblyAI y devuelve transcript_id"""
    response = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json={"audio_url": upload_url},
        headers=HEADERS
    )
    response.raise_for_status()
    return response.json()["id"]


def wait_for_transcription(transcript_id: str) -> str:
    """Espera hasta que la transcripción esté lista y devuelve el texto"""
    url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"

    while True:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        if result["status"] == "completed":
            return result["text"]

        if result["status"] == "error":
            raise Exception(f"AssemblyAI error: {result['error']}")

        time.sleep(5)  # esperar 5 segundos antes de reintentar
