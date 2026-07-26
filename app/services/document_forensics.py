import io
import logging
from typing import Dict, List

import docx
import fitz
from docx.shared import RGBColor

from app.services.nlp_engine import INDUSTRY_SKILL_MAP

logger = logging.getLogger(__name__)

# ==========================================================
# CONFIG
# ==========================================================
WHITE_COLOR = 0xFFFFFF

IGNORE_TEXTS = {
    "© topcv.vn",
    "topcv.vn",
    "@topcv.vn",
}

MIN_TINY_FONT = 2.0
SMALL_FONT = 4.0

def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _is_watermark(text: str) -> bool:
    t = _normalize_text(text)

    if not t:
        return True

    if t in IGNORE_TEXTS:
        return True

    if "topcv.vn" in t:
        return True

    return False


def _looks_like_keyword_stuffing(text: str, industry: str = "all") -> bool:
    words = text.lower().replace(",", " ").split()
    if len(words) < 5:
        return False

    # Lấy danh sách key chuẩn từ DB Cache thay vì hardcode
    target_skill_map = INDUSTRY_SKILL_MAP.get(industry, INDUSTRY_SKILL_MAP.get("all", {}))
    
    # Gom tất cả variants thành 1 set phẳng để tra cứu siêu tốc O(1)
    keywords_to_check = set(variant for variants in target_skill_map.values() for variant in variants)

    # Đếm số lượng từ khóa va chạm
    matched = sum(1 for w in words if w in keywords_to_check)

    # Nếu trên 50% số từ trong cụm (hoặc >= 5 từ) là danh từ kỹ năng -> Nhồi nhét từ khóa
    return matched >= 5 or (len(words) > 0 and matched / len(words) > 0.5)


def _risk_to_penalty(risk_score: int) -> int:
    if risk_score >= 80:
        return 30
    if risk_score >= 60:
        return 20
    if risk_score >= 40:
        return 10
    return 0


def detect_hidden_text(file_bytes: bytes, filename: str, industry: str = "all") -> Dict:
    risk_score = 0
    reasons: List[str] = []
    evidence: List[dict] = []

    try:

        # ======================================================
        # PDF
        # ======================================================
        if filename.lower().endswith(".pdf"):

            doc = fitz.open(stream=file_bytes, filetype="pdf")

            for page_index, page in enumerate(doc):

                page_width = page.rect.width
                page_height = page.rect.height

                text_dict = page.get_text("dict")

                for block in text_dict.get("blocks", []):

                    if "lines" not in block:
                        continue

                    for line in block["lines"]:

                        for span in line["spans"]:

                            text = span.get("text", "").strip()

                            if not text:
                                continue

                            if _is_watermark(text):
                                continue

                            size = float(span.get("size", 10))
                            color = span.get("color", 0)

                            bbox = span.get("bbox", None)

                            span_score = 0
                            span_reasons = []

                            if size < MIN_TINY_FONT:
                                span_score += 45
                                span_reasons.append("Tiny font (<2pt)")

                            elif size < SMALL_FONT:
                                span_score += 15
                                span_reasons.append("Very small font (<4pt)")

                            if color == WHITE_COLOR:
                                span_score += 5
                                span_reasons.append("White text")

                            if bbox:

                                x0, y0, x1, y1 = bbox

                                if (
                                    x0 < -5
                                    or y0 < -5
                                    or x1 > page_width + 5
                                    or y1 > page_height + 5
                                ):
                                    span_score += 40
                                    span_reasons.append("Outside page")

                            if _looks_like_keyword_stuffing(text, industry):
                                span_score += 20
                                span_reasons.append("Keyword stuffing")

                            if span_score >= 20:

                                risk_score += span_score

                                reasons.extend(span_reasons)

                                evidence.append(
                                    {
                                        "page": page_index + 1,
                                        "text": text[:150],
                                        "font_size": size,
                                        "color": color,
                                        "bbox": bbox,
                                        "score": span_score,
                                        "reasons": span_reasons,
                                    }
                                )

            risk_score = min(risk_score, 100)

            return {
                "detected": risk_score >= 60,
                "risk_score": risk_score,
                "penalty": _risk_to_penalty(risk_score),
                "reasons": sorted(set(reasons)),
                "evidence": evidence,
            }

        # ======================================================
        # DOCX
        # ======================================================
        elif filename.lower().endswith(".docx"):

            doc = docx.Document(io.BytesIO(file_bytes))

            for para in doc.paragraphs:

                for run in para.runs:

                    text = run.text.strip()

                    if not text:
                        continue

                    if _is_watermark(text):
                        continue

                    span_score = 0
                    span_reasons = []

                    if run.font.hidden:
                        span_score += 60
                        span_reasons.append("Hidden flag")

                    if (
                        run.font.color
                        and run.font.color.rgb == RGBColor(255, 255, 255)
                    ):
                        span_score += 5
                        span_reasons.append("White text")

                    if run.font.size:

                        pt = run.font.size.pt

                        if pt < MIN_TINY_FONT:
                            span_score += 45
                            span_reasons.append("Tiny font")

                        elif pt < SMALL_FONT:
                            span_score += 15
                            span_reasons.append("Very small font")

                    if _looks_like_keyword_stuffing(text, industry):
                        span_score += 20
                        span_reasons.append("Keyword stuffing")

                    if span_score >= 20:

                        risk_score += span_score

                        reasons.extend(span_reasons)

                        evidence.append(
                            {
                                "text": text[:150],
                                "score": span_score,
                                "reasons": span_reasons,
                            }
                        )

            risk_score = min(risk_score, 100)

            return {
                "detected": risk_score >= 60,
                "risk_score": risk_score,
                "penalty": _risk_to_penalty(risk_score),
                "reasons": sorted(set(reasons)),
                "evidence": evidence,
            }

    except Exception as e:

        logger.exception("Forensics failed: %s", e)

        return {
            "detected": False,
            "risk_score": 0,
            "penalty": 0,
            "reasons": [],
            "evidence": [],
        }

    return {
        "detected": False,
        "risk_score": 0,
        "penalty": 0,
        "reasons": [],
        "evidence": [],
    }