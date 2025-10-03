import base64
import json
import requests
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def media_key_from_json(media_key_json: str) -> bytes:
    """
    Convierte el string JSON {"0":152,"1":88,...} a bytes reales.
    """
    obj = json.loads(media_key_json)
    return bytes([obj[str(i)] for i in range(len(obj))])


def derive_media_keys(media_key_bytes: bytes, media_type_info: bytes) -> dict:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=112,
        salt=None,
        info=media_type_info,
        backend=default_backend(),
    )
    expanded = hkdf.derive(media_key_bytes)
    return {
        "iv": expanded[0:16],
        "cipherKey": expanded[16:48],
        "macKey": expanded[48:80],
        "refKey": expanded[80:112],
    }


def aes_cbc_decrypt(cipher_key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext_padded = decryptor.update(ciphertext) + decryptor.finalize()
    pad_len = plaintext_padded[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Padding inválido.")
    return plaintext_padded[:-pad_len]


def download_encrypted(url: str, timeout: int = 30) -> bytes:
    headers = {"User-Agent": "curl/7.64.1"}
    r = requests.get(url, headers=headers, timeout=timeout, stream=True)
    r.raise_for_status()
    return r.content


def decrypt_whatsapp_media(enc_bytes: bytes, media_key_json: str, message_type: str) -> bytes:
    media_key = media_key_from_json(media_key_json)

    type_map = {
        "audio": b"WhatsApp Audio Keys",
        "image": b"WhatsApp Image Keys",
        "video": b"WhatsApp Video Keys",
        "document": b"WhatsApp Document Keys",
    }
    info = type_map.get(message_type, b"WhatsApp Image Keys")

    keys = derive_media_keys(media_key, info)
    iv = keys["iv"]
    cipher_key = keys["cipherKey"]

    if len(enc_bytes) <= 10:
        raise ValueError("Contenido .enc demasiado corto.")
    file_bytes = enc_bytes[:-10]

    plaintext = aes_cbc_decrypt(cipher_key, iv, file_bytes)
    return plaintext
