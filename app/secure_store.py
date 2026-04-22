from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes


CRYPTPROTECT_UI_FORBIDDEN = 0x01
LOCAL_ENTROPY = b"CutCanvas-AI-Settings-v1"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32


def _blob_from_bytes(raw: bytes) -> tuple[DATA_BLOB, ctypes.Array | None]:
    if not raw:
        return DATA_BLOB(0, None), None
    buffer = ctypes.create_string_buffer(raw, len(raw))
    return DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        kernel32.LocalFree(blob.pbData)


def encrypt_text(value: str) -> str:
    raw = value.encode("utf-8")
    in_blob, in_buffer = _blob_from_bytes(raw)
    entropy_blob, entropy_buffer = _blob_from_bytes(LOCAL_ENTROPY)
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "CutCanvas AI Key",
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("无法加密 API Key。")
    _ = (in_buffer, entropy_buffer)
    encrypted = _bytes_from_blob(out_blob)
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_text(value: str) -> str:
    raw = base64.b64decode(value.encode("ascii"))
    in_blob, in_buffer = _blob_from_bytes(raw)
    entropy_blob, entropy_buffer = _blob_from_bytes(LOCAL_ENTROPY)
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("无法解密 API Key。")
    _ = (in_buffer, entropy_buffer)
    decrypted = _bytes_from_blob(out_blob)
    return decrypted.decode("utf-8")
