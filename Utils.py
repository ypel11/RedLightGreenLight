import struct
import numpy as np
import cv2
import pickle
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

def generate_rsa_keypair(bits=2048):
    key = RSA.generate(bits)
    private_rsa = key
    public_rsa = key.publickey()
    return private_rsa, public_rsa

def load_rsa_private(pem_data):
    return RSA.import_key(pem_data)

def load_rsa_public(pem_data):
    return RSA.import_key(pem_data)

#
# 2) RSA‐encrypt / decrypt (OAEP)
#
def rsa_encrypt(public_key: RSA.RsaKey, plaintext: bytes) -> bytes:
    cipher_rsa = PKCS1_OAEP.new(public_key)
    return cipher_rsa.encrypt(plaintext)

def rsa_decrypt(private_key: RSA.RsaKey, ciphertext: bytes) -> bytes:
    cipher_rsa = PKCS1_OAEP.new(private_key)
    return cipher_rsa.decrypt(ciphertext)

AES_NONCE_SIZE = 12   # recommended for GCM
AES_TAG_SIZE = 16     # GCM authentication tag = 16 bytes

def aes_encrypt(aes_key: bytes, plaintext: bytes) -> bytes:
    """
    Returns a bytes object: 12‐byte nonce || ciphertext || 16‐byte tag.
    """
    nonce = get_random_bytes(AES_NONCE_SIZE)
    cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return nonce + ciphertext + tag

def aes_decrypt(aes_key: bytes, data: bytes) -> bytes:
    """
    Expects data = nonce (12 bytes) || ciphertext || tag (16 bytes).
    Returns the decrypted plaintext or raises ValueError if tag fails.
    """
    nonce = data[:AES_NONCE_SIZE]
    tag = data[-AES_TAG_SIZE:]
    ciphertext = data[AES_NONCE_SIZE:-AES_TAG_SIZE]
    cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)

#
# 4) “send_encrypted” / “recv_encrypted” wrappers over a socket
#    We prefix each encrypted blob with a 4‐byte big‐endian length.
#
def send_encrypted(sock, aes_key: bytes, plaintext: bytes):
    """
    Encrypts plaintext with aes_key (AES‐GCM) and sends length + blob.
    """
    blob = aes_encrypt(aes_key, plaintext)
    sock.sendall(len(blob).to_bytes(4, "big") + blob)

def recv_encrypted(sock, aes_key: bytes) -> bytes:
    """
    Receives 4-byte length, then that many bytes; decrypts with aes_key and returns plaintext.
    Includes detailed debug output to help diagnose encryption errors.
    """
    try:
        # Receive the 4-byte length prefix
        length_buffer = recv_all(sock, 4)
        if not length_buffer:
            raise ConnectionError("Socket closed when expecting length prefix")

        length = int.from_bytes(length_buffer, "big")
        print(f"[recv_encrypted] Expecting {length} bytes of encrypted data")

        # Receive the full encrypted blob
        data = recv_all(sock, length)
        actual_length = len(data)
        print(f"[recv_encrypted] Received {actual_length} bytes")

        if actual_length != length:
            raise ValueError(f"Expected {length} bytes, but received {actual_length}")

        nonce = data[:AES_NONCE_SIZE]
        tag = data[-AES_TAG_SIZE:]
        ciphertext = data[AES_NONCE_SIZE:-AES_TAG_SIZE]

        print(f"[recv_encrypted] Nonce: {nonce.hex()}")
        print(f"[recv_encrypted] Tag:   {tag.hex()}")
        print(f"[recv_encrypted] Ciphertext length: {len(ciphertext)}")

        # Decrypt and verify
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        print(f"[recv_encrypted] Decryption successful, plaintext length: {len(plaintext)}")

        return plaintext

    except ValueError as ve:
        print(f"[recv_encrypted] Decryption failed: {ve}")
        raise

    except Exception as e:
        print(f"[recv_encrypted] Unexpected error: {e}")
        raise


def send_frame(sock, frame, recv_more, send_more, red_light):
    # overlay alive_flag or whatever on frame first…
    success, jpg = cv2.imencode('.jpg', frame)
    if not success:
        return
    buffer = jpg.tobytes()
    # send 1 byte alive_flag + 4 bytes length + raw JPEG
    sock.send(struct.pack(">???I",  red_light, recv_more, send_more, len(buffer)))
    sock.send(buffer)
def recv_all(sock, n):
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            raise ConnectionError("Socket closed")
        data += packet
    return data


def stack_frames(frames, grid_size=(2,3)):
    h, w = frames[0].shape[:2]
    blank = np.zeros_like(frames[0])
    # pad if needed
    while len(frames) < grid_size[0]*grid_size[1]:
        frames.append(blank)
    rows = []
    for i in range(0, len(frames), grid_size[1]):
        rows.append(np.hstack(frames[i:i+grid_size[1]]))
    return np.vstack(rows)
