"""Экстракторы по extractor_kind."""

from .identity import extract_ru_passport
from .medical import extract_medical_certificate
from .training import (
    extract_bdd_protocol,
    extract_electrical_safety,
    extract_safety_protocol_ab,
    extract_safety_protocol_v,
    extract_siz_training_protocol,
    extract_umo,
)

EXTRACTOR_REGISTRY = {
    "ru_passport": extract_ru_passport,
    "medical_certificate": extract_medical_certificate,
    "safety_protocol_v": extract_safety_protocol_v,
    "safety_protocol_ab": extract_safety_protocol_ab,
    "electrical_safety": extract_electrical_safety,
    "bdd_protocol": extract_bdd_protocol,
    "siz_training_protocol": extract_siz_training_protocol,
    "umo": extract_umo,
}

__all__ = [
    "EXTRACTOR_REGISTRY",
    "extract_ru_passport",
    "extract_medical_certificate",
    "extract_safety_protocol_v",
    "extract_safety_protocol_ab",
    "extract_electrical_safety",
    "extract_bdd_protocol",
    "extract_siz_training_protocol",
    "extract_umo",
]
