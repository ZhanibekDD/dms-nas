"""
MVP предобработки скана паспорта РФ перед vision: выбор ориентации 0/90/180/270°
и флаг расхождения фамилии с данными сотрудника (без записи ФИО в Employee).
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "pass_docs_vision_v2"
ORIENTATION_HEURISTIC_VARIANT = "deterministic_4way_row_edge_v1"


def _fio_key(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip()).casefold()


def _orientation_score_rgb(pil_rgb: Image.Image) -> float:
    """
    Эвристика «горизонтальности» текста: сумма |Δ по X| / (сумма |Δ по Y| + ε).
    Для разворота паспорта в читаемой ориентации обычно выше, чем у повёрнутого на 90°.
    """
    g = pil_rgb.convert("L")
    w, h = g.size
    if w < 2 or h < 2:
        return 0.0
    max_side = 320
    if max(w, h) > max_side:
        ratio = max_side / float(max(w, h))
        g = g.resize((max(2, int(w * ratio)), max(2, int(h * ratio))), Image.Resampling.LANCZOS)
        w, h = g.size
    px = g.load()
    gh = 0
    gv = 0
    for y in range(h):
        for x in range(w - 1):
            gh += abs(px[x + 1, y] - px[x, y])
    for x in range(w):
        for y in range(h - 1):
            gv += abs(px[x, y + 1] - px[x, y])
    return float(gh / (gv + 1.0))


def choose_passport_rotation(pil_rgb: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """
    Перебирает 0/90/180/270°, выбирает кадр с максимальным orientation_score.
    Возвращает (повёрнутое RGB-изображение, метаданные для extracted_json.preprocessing).
    """
    pil_rgb = pil_rgb.convert("RGB")
    scores: dict[str, float] = {}
    best_angle = 0
    best_score = -1.0
    best_im = pil_rgb

    for deg in (0, 90, 180, 270):
        if deg == 0:
            rotated = pil_rgb
        else:
            rotated = pil_rgb.rotate(-deg, expand=True, resample=Image.Resampling.BICUBIC)
        sc = _orientation_score_rgb(rotated)
        scores[str(deg)] = round(sc, 4)
        if sc > best_score:
            best_score = sc
            best_angle = deg
            best_im = rotated

    meta: dict[str, Any] = {
        "rotation_applied": best_angle,
        "variant": ORIENTATION_HEURISTIC_VARIANT,
        "scores_by_angle_deg": scores,
        "chosen_score": round(best_score, 4),
    }
    return best_im, meta


def compute_name_mismatch_warning(employee: Any, normalized: dict[str, Any]) -> dict[str, Any]:
    """
    Сравнивает фамилию из normalized с подсказками из карточки (last_name, source_label, хвост import_key).
    Не изменяет Employee; только словарь для записи в extracted_json.
    """
    plast = (normalized.get("last_name") or "").strip()
    if not plast:
        return {
            "name_mismatch_warning": False,
            "name_mismatch_reason": "empty_passport_last_name",
        }

    refs: list[str] = []
    ln = (getattr(employee, "last_name", None) or "").strip()
    if ln:
        refs.append(ln)
    sl = (getattr(employee, "source_label", None) or "").strip()
    if sl:
        refs.append(sl.split()[0])
    ik = (getattr(employee, "import_key", None) or "").strip()
    if "&" in ik:
        tail = ik.split("&", 1)[-1].strip()
        if tail:
            refs.append(tail)

    keys = {_fio_key(r) for r in refs if r}
    pk = _fio_key(plast)
    if not keys:
        return {
            "name_mismatch_warning": False,
            "name_mismatch_reason": "no_employee_refs",
            "passport_last_name": plast,
        }

    if pk in keys:
        return {
            "name_mismatch_warning": False,
            "name_mismatch_reason": "match_last_name_or_folder",
            "passport_last_name": plast,
        }

    # Частичное вхождение (редкие опечатки/суффиксы) — только если короткие строки
    for k in keys:
        if len(pk) >= 3 and len(k) >= 3 and (pk in k or k in pk):
            return {
                "name_mismatch_warning": False,
                "name_mismatch_reason": "fuzzy_substring_match",
                "passport_last_name": plast,
            }

    return {
        "name_mismatch_warning": True,
        "name_mismatch_reason": "passport_last_name_not_in_employee_refs",
        "passport_last_name": plast,
        "employee_refs_checked": list(refs)[:8],
    }
