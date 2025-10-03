import assemblyai as aai
import os

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

def transcribe_with_assemblyai(file_path: str) -> str:
    """
    Sube un archivo a AssemblyAI y espera la transcripción final.
    """
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(file_path)
    return transcript.text if transcript and transcript.text else ""
