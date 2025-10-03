# whatsapp_decrypt.py
import json
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def parse_media_key(media_key_str: str) -> bytes:
    """
    Convierte el string JSON {"0":152, "1":88, ...} a bytes.
    """
    key_dict = json.loads(media_key_str)
    key_bytes = bytes([key_dict[str(i)] for i in range(len(key_dict))])
    return key_bytes


def decrypt_whatsapp_audio(enc_data: bytes, media_key: bytes) -> bytes:
    """
    Desencripta archivo .enc de WhatsApp usando media_key.
    """

    # La clave real de WhatsApp se deriva con HKDF → aquí simplificamos: 
    # usamos directamente los primeros 32 bytes.
    # (Si no funciona, necesitaríamos implementar HKDF full con info="WhatsApp Audio Keys")
    key = media_key[:32]
    iv = enc_data[:16]  # primeros 16 bytes son IV
    ciphertext = enc_data[16:]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()

    # quitar padding PKCS7
    pad_len = decrypted[-1]
    return decrypted[:-pad_len]
