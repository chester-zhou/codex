from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import os

import shutil


@dataclass
class PdfPage:
    page_num: int
    text: str


def extract_pdf_text(
    path: str,
    *,
    ocr: bool = False,
    ocr_engine: str = "tesseract",
    ocr_lang: str = "chi_sim+eng",
    ocr_dpi: int = 300,
    ocr_min_chars: int = 20,
    ocr_model_dir: Optional[str] = None,
    ocr_min_pixels: int = 32 * 32 * 3,
    ocr_max_pixels: int = 32 * 32 * 8192,
) -> List[PdfPage]:
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "未安装 pdfplumber，无法解析 PDF。请执行: pip install pdfplumber"
        ) from exc

    ocr_engine = ocr_engine.lower()
    if ocr and ocr_engine not in {"tesseract", "easyocr", "qwen_ocr"}:
        raise ValueError("ocr_engine 仅支持 tesseract、easyocr 或 qwen_ocr")

    pytesseract = None
    easyocr_reader = None
    if ocr and ocr_engine == "tesseract":
        if not shutil.which("tesseract"):
            raise RuntimeError("未找到 tesseract，请先安装后再启用 OCR")
        try:
            import pytesseract  # type: ignore
        except Exception as exc:
            raise RuntimeError("未安装 pytesseract，请执行: pip install pytesseract") from exc
    elif ocr and ocr_engine == "easyocr":
        try:
            import easyocr  # type: ignore
        except Exception as exc:
            raise RuntimeError("未安装 easyocr，请执行: pip install easyocr") from exc

        def _parse_langs(raw: str) -> List[str]:
            parts = [p.strip() for p in raw.replace("+", ",").split(",") if p.strip()]
            mapped = []
            for p in parts:
                if p in {"chi_sim", "zh", "zh_cn"}:
                    mapped.append("ch_sim")
                elif p == "eng":
                    mapped.append("en")
                else:
                    mapped.append(p)
            return mapped or ["ch_sim", "en"]

        model_dir = ocr_model_dir or os.getenv("EASYOCR_MODEL_DIR")
        if not model_dir:
            model_dir = os.path.join(os.getcwd(), ".easyocr")
        easyocr_reader = easyocr.Reader(
            _parse_langs(ocr_lang),
            gpu=False,
            model_storage_directory=model_dir,
            user_network_directory=model_dir,
        )
    elif ocr and ocr_engine == "qwen_ocr":
        from .qwen_ocr_client import qwen_ocr_image  # local import to avoid heavy deps

    pages: List[PdfPage] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if ocr and len(text.strip()) < ocr_min_chars:
                image = page.to_image(resolution=ocr_dpi).original
                if ocr_engine == "tesseract":
                    ocr_text = pytesseract.image_to_string(image, lang=ocr_lang)
                elif ocr_engine == "easyocr":
                    results = easyocr_reader.readtext(image)
                    ocr_text = "\n".join([item[1] for item in results if len(item) >= 2])
                else:
                    ocr_text = qwen_ocr_image(
                        image,
                        min_pixels=ocr_min_pixels,
                        max_pixels=ocr_max_pixels,
                    )
                if ocr_text:
                    text = ocr_text
            pages.append(PdfPage(page_num=i, text=text))

    if not pages:
        raise ValueError("PDF 未包含可解析页面")

    return pages
