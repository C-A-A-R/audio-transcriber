# mapper.py
import json
import re
from typing import Tuple, Any

def extract_title_from_markdown(markdown_text: str) -> str:
    """
    Busca el primer encabezado (# ...) en el Markdown y lo usa como nombre.
    Si no hay, devuelve 'notes'.
    """
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            # limpiar caracteres no válidos para nombre de archivo
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip()
            return safe_title if safe_title else "notes"
    return "notes"

def _join_token_list(tokens):
    """
    Tokens suele ser lista de fragmentos. Los unimos sin separador
    y luego limpiamos espacios y saltos de línea sobrantes.
    """
    text = "".join(tokens)
    # Normalizar saltos de línea y espacios
    # - juntamos palabras separadas por tokenización incorrecta: dejamos tal cual,
    #   pero arreglamos espacios dobles y espacios antes de signos de puntuación.
    text = re.sub(r'\s+\n', '\n', text)
    text = re.sub(r'\n\s+', '\n', text)
    # quitar espacios antes de puntuación
    text = re.sub(r'\s+([.,;:?!])', r'\1', text)
    # colapsar múltiples espacios
    text = re.sub(r'[ \t]{2,}', ' ', text)
    # limpiar espacios extra al inicio / fin
    return text.strip()

def _list_like(obj) -> bool:
    return isinstance(obj, (list, tuple))

def _looks_tokenized_list(lst) -> bool:
    """
    Heurística: si es lista y los elementos son cortos (avg length < 10)
    o gran parte son fragmentos muy cortos -> fue tokenizado.
    """
    if not _list_like(lst) or len(lst) == 0:
        return False
    lengths = [len(str(x)) for x in lst]
    avg = sum(lengths)/len(lengths)
    short_count = sum(1 for l in lengths if l <= 5)
    return (avg < 12) or (short_count / len(lengths) > 0.5)

def _extract_output_field(obj):
    """
    Algunos modelos devuelven {"output": [...]} u {"output": "string"}.
    """
    if isinstance(obj, dict):
        # could be {"output": [...] } or {"choices": [{"text": ...}]}
        if "output" in obj:
            return obj["output"]
        # common choice pattern
        if "choices" in obj and isinstance(obj["choices"], list) and len(obj["choices"])>0:
            # try common fields
            first = obj["choices"][0]
            if isinstance(first, dict):
                for k in ("text", "content", "message", "delta"):
                    if k in first:
                        return first[k]
    return obj

def map_model_output_to_markdown(model_output: Any) -> Tuple[str, bool]:
    """
    Entrada: puede ser:
        - string (ya ok)
        - list of fragments/tokens -> se unirán
        - dict with 'output' -> se manejará el campo output

    Devuelve: (markdown_text, mapped_flag)
    """
    # si viene con wrapper, extraer
    value = _extract_output_field(model_output)

    # si es lista -> posiblemente tokens/fragments
    if _list_like(value):
        # if elements are bytes, convert to str
        fragments = [str(x) for x in value]
        if _looks_tokenized_list(fragments):
            md = _join_token_list(fragments)
            return md, True
        else:
            # maybe it's already list of paragraphs; join with newline
            md = "\n".join(fragments)
            return md, True

    # si es string
    if isinstance(value, str):
        # Heurística: si contiene patterns de tokens separados (ej. " #", " PROGRAM", "ACIÓN")
        # no podemos detectar tokenization perfecta aquí; asumimos que si hay muchos saltos
        # de fragmento raros (espacios antes de letras capitales) procederemos a limpiar.
        text = value
        # Thumbnails of tokenization can appear as many short segments; try to normalize
        # Remove repeated " \n" / spaces near newlines
        text = re.sub(r'\s+\n', '\n', text)
        text = re.sub(r'\n\s+', '\n', text)
        text = re.sub(r'\s+([.,;:?!])', r'\1', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip(), False

    # fallback: stringify
    return str(value).strip(), False
