import json
import base64
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def parse_media_key(media_key_str: str) -> bytes:
    """
    Convierte el media_key que llega como JSON string {"0":152,"1":88,...} a bytes.
    """
    if isinstance(media_key_str, str):
        media_key_dict = json.loads(media_key_str)
    else:
        media_key_dict = media_key_str

    return bytes(media_key_dict[str(i)] for i in range(len(media_key_dict)))


def derive_keys(media_key: bytes):
    """
    Deriva las claves AES/HMAC/IV usando HKDF con el contexto de WhatsApp Audio.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=112,  # 32 (AES) + 32 (HMAC) + 16 (IV) + extra
        salt=None,
        info=b"WhatsApp Audio Keys",
        backend=default_backend(),
    )
    key_material = hkdf.derive(media_key)

    aes_key = key_material[:32]
    mac_key = key_material[32:64]
    iv = key_material[64:80]
    return aes_key, mac_key, iv


def decrypt_whatsapp_audio(enc_data: bytes, media_key: bytes) -> bytes:
    """
    Desencripta el audio .enc de WhatsApp.
    """
    aes_key, mac_key, iv = derive_keys(media_key)

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(enc_data) + decryptor.finalize()

    # Deshacer padding PKCS7
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    return plaintext
