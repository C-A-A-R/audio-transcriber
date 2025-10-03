import requests
import hmac
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import HKDF


def _download_enc_file(enc_url: str, timeout: int = 30) -> bytes:
    resp = requests.get(enc_url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _parse_media_key_to_bytes(media_key_raw) -> bytes:
    """Convierte media_key en bytes (32 bytes). Acepta: bytes, str (base64/hex), dict {"0":n,..}, list [n,..]."""
    if isinstance(media_key_raw, (bytes, bytearray)):
        media_key_bytes = bytes(media_key_raw)
    elif isinstance(media_key_raw, str):
        # hex si todos son hex y longitud par; si no, intentamos base64
        if all(c in '0123456789abcdefABCDEF' for c in media_key_raw) and len(media_key_raw) % 2 == 0:
            media_key_bytes = bytes.fromhex(media_key_raw)
        else:
            media_key_bytes = base64.b64decode(media_key_raw)
    elif isinstance(media_key_raw, dict):
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
    return media_key_bytes


def decrypt_audio(media_key, enc_url: str, timeout: int = 30) -> bytes:
    """
    Descifra un audio .enc de WhatsApp con la media key (bytes/base64/hex/dict/list).

    Retorna los bytes del audio descifrado (formato OGG/Opus normalmente).
    """
    media_key_bytes = _parse_media_key_to_bytes(media_key)
    enc_data = _download_enc_file(enc_url, timeout=timeout)

    # Derivar claves usando HKDF (112 bytes: 16 IV, 32 cipher_key, 32 mac_key, resto no usado)
    info = b"WhatsApp Audio Keys"
    salt = b"\x00" * 32
    expanded_key = HKDF(media_key_bytes, 112, salt, hashlib.sha256, 3, info)

    iv = expanded_key[0:16]
    cipher_key = expanded_key[16:48]
    mac_key = expanded_key[48:80]

    # Separar datos y MAC (últimos 10 bytes)
    if len(enc_data) <= 10:
        raise ValueError("Archivo .enc demasiado pequeño")
    file_data = enc_data[:-10]
    mac = enc_data[-10:]

    # Verificar integridad (HMAC-SHA256) y truncar a 10 bytes
    computed_mac = hmac.new(mac_key, iv + file_data, hashlib.sha256).digest()[:10]
    if mac != computed_mac:
        raise ValueError("MAC inválido: archivo alterado o mediaKey incorrecta")

    # Descifrar con AES-CBC
    cipher = AES.new(cipher_key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(file_data)

    # Eliminar padding PKCS7
    pad_len = decrypted[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Padding PKCS7 inválido")
    return decrypted[:-pad_len]