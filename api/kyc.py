"""Mock KYC: validate the uploaded ID image, OCR it and match against the registry."""
import difflib
import io
import re

import pytesseract
from PIL import Image

from . import config

Image.MAX_IMAGE_PIXELS = 25_000_000  # guard against decompression bombs
MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
CIN_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")  # Tunisian CIN: 8 digits


class KYCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def validate_image(data, content_type):
    if not data:
        raise KYCError("INVALID_FILE", "Empty upload")
    if len(data) > config.MAX_ID_IMAGE_BYTES:
        raise KYCError("FILE_TOO_LARGE", "ID image must be 5 MB or smaller")
    kind = next((m for sig, m in MAGIC.items() if data.startswith(sig)), None)
    if kind is None or content_type not in MAGIC.values() or kind != content_type:
        raise KYCError("INVALID_FILE", "Only genuine JPEG or PNG images are accepted")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise KYCError("INVALID_FILE", "Image could not be decoded")


def _name_score(full_name, ocr_words):
    tokens = [t for t in re.split(r"\s+", full_name.lower()) if len(t) >= 3]
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if difflib.get_close_matches(t, ocr_words, n=1, cutoff=0.8))
    return hits / len(tokens)


def verify_identity(data, content_type, conn):
    img = validate_image(data, content_type)
    if img.width < 1000:  # small ID photos OCR badly
        scale = 1000 / img.width
        img = img.resize((1000, int(img.height * scale)))
    text = pytesseract.image_to_string(img, lang="eng+fra")
    ids = CIN_RE.findall(text)
    if not ids:
        raise KYCError("OCR_NO_ID", "No ID number could be read from the image")
    user = None
    for candidate in ids:
        user = conn.execute("SELECT * FROM users WHERE id_number = ?", (candidate,)).fetchone()
        if user:
            break
    if user is None:
        raise KYCError("ID_NOT_FOUND", "ID number is not in the registry")
    words = re.findall(r"[^\W\d_]{3,}", text.lower())
    if _name_score(user["full_name"], words) < 0.6:
        raise KYCError("NAME_MISMATCH", "Name on the ID does not match the registry")
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "id_masked": "*" * 4 + user["id_number"][-4:],
    }
