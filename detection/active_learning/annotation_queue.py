"""Annotation queue with HMAC-SHA256 integrity protection.

Each annotation carries an ``annotation_hmac`` field computed as
HMAC-SHA256 of ``wallet|label|annotator_id|annotated_at`` keyed by
``config.ANNOTATION_HMAC_SECRET``.  ``export_labelled`` verifies every
HMAC before including the annotation in the exported dataset; any
annotation with an invalid HMAC is logged as a WARNING and excluded.
"""

import hashlib
import hmac
import json
import os
from typing import Any

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


def _compute_hmac(wallet: str, label: int, annotator_id: str, annotated_at: str) -> str:
    secret = config.ANNOTATION_HMAC_SECRET.encode()
    message = f"{wallet}|{label}|{annotator_id}|{annotated_at}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def add_annotation(
    queue_path: str,
    wallet: str,
    label: int,
    annotator_id: str,
    annotated_at: str,
) -> dict:
    """Append a new annotation to *queue_path* (JSON list) with an HMAC."""
    annotation: dict[str, Any] = {
        "wallet": wallet,
        "label": label,
        "annotator_id": annotator_id,
        "annotated_at": annotated_at,
        "annotation_hmac": _compute_hmac(wallet, label, annotator_id, annotated_at),
    }

    queue: list = []
    if os.path.exists(queue_path):
        with open(queue_path) as f:
            queue = json.load(f)

    queue.append(annotation)
    with open(queue_path, "w") as f:
        json.dump(queue, f, indent=2)

    return annotation


def export_labelled(queue_path: str) -> list[dict]:
    """Return verified annotations from *queue_path*.

    Annotations whose HMAC fails verification are logged as WARNING and
    excluded from the returned list.
    """
    if not os.path.exists(queue_path):
        return []

    with open(queue_path) as f:
        queue: list[dict] = json.load(f)

    verified = []
    for ann in queue:
        expected = _compute_hmac(
            ann.get("wallet", ""),
            ann.get("label", -1),
            ann.get("annotator_id", ""),
            ann.get("annotated_at", ""),
        )
        if not hmac.compare_digest(expected, ann.get("annotation_hmac", "")):
            logger.warning(
                "Invalid HMAC for annotation wallet=%s annotator=%s — excluded",
                ann.get("wallet"),
                ann.get("annotator_id"),
            )
        else:
            verified.append(ann)

    return verified
