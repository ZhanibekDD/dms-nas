"""Экстракторы по extractor_kind (ru_passport, medical_certificate)."""

from .identity import extract_ru_passport
from .medical import extract_medical_certificate

EXTRACTOR_REGISTRY = {
    "ru_passport": extract_ru_passport,
    "medical_certificate": extract_medical_certificate,
}

__all__ = ["EXTRACTOR_REGISTRY", "extract_ru_passport", "extract_medical_certificate"]
