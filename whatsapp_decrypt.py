# whatsapp_decrypt.py
import base64
import requests
import hashlib
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import tempfile

def parse_media_key(media_key_dict):
    """Convierte el objeto JSON de mediaKey a bytes"""
    return bytes([media_key_dict[str(i)] if str(i) in media_key_dict else media_key_dict[i] for i in range(32)])

def derive_keys(media_key: bytes):
    """Deriva IV y CipherKey usando HKDF (WhatsApp spec)"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=112,
        salt=bytes([0]*32),
        info=b"WhatsApp Audio Keys",
        backend=default_backend()
    )
    derived = hkdf.derive(media_key)
    iv = derived[:16]
    cipher_key = derived[16:48]
    return iv, cipher_key

def decrypt_whatsapp_audio(enc_url, media_key_dict):
    # Descargar el archivo .enc
    resp = requests.get(enc_url, stream=True)
    resp.raise_for_status()
    encrypted = resp.content

    # Preparar claves
    media_key = parse_media_key(media_key_dict)
    iv, cipher_key = derive_keys(media_key)

    # AES-CBC decrypt
    cipher = AES.new(cipher_key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted)

    # Quitar padding PKCS#7
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len]

    # Guardar en un archivo temporal .ogg
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    tmp.write(decrypted)
    tmp.close()

    return tmp.name
