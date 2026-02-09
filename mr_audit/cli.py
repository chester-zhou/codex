from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .audit_engine import AuditResult, audit_rules
from .excel_parser import load_rules_from_excel
from .pdf_parser import extract_pdf_text


def _write_json(path: Path, results: list[AuditResult]) -> None:
    payload = [
        {
            "大类": r.major,
            "小类": r.minor,
            "审核要求": r.requirement,
            "判断结果": r.result,
            "证据": [asdict(item) for item in r.evidence],
            "判断说明": r.reason,
            "置信度": r.confidence,
        }
        for r in results
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, results: list[AuditResult]) -> None:
    import csv

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["大类", "小类", "审核要求", "判断结果", "证据", "判断说明", "置信度"])
        for r in results:
            evidence_str = " | ".join(
                [f"p{item.page}:{item.quote}" for item in r.evidence]
            )
            writer.writerow(
                [r.major, r.minor, r.requirement, r.result, evidence_str, r.reason, r.confidence]
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MR 场地安装前图纸自动审核")
    parser.add_argument("--excel", required=True, help="审核要点 Excel 路径")
    parser.add_argument("--pdf", required=True, help="MR 场地图纸 PDF 路径")
    parser.add_argument("--output", default="audit_report.json", help="输出 JSON 路径")
    parser.add_argument("--sheet", default=None, help="Excel 表名 (可选)")
    parser.add_argument("--model", default=None, help="Qwen 模型名称 (可选)")
    parser.add_argument("--skip-llm", action="store_true", help="仅提取证据，不调用大模型")
    parser.add_argument("--max-evidence", type=int, default=3, help="每条规则最多证据条数")
    parser.add_argument("--csv", default=None, help="可选输出 CSV 路径")
    parser.add_argument("--ocr", action="store_true", help="启用 OCR (需 tesseract + pytesseract)")
    parser.add_argument("--ocr-engine", default="tesseract", help="OCR 引擎: tesseract / easyocr / qwen_ocr")
    parser.add_argument("--ocr-lang", default="chi_sim+eng", help="OCR 语言 (tesseract 语种)")
    parser.add_argument("--ocr-dpi", type=int, default=300, help="OCR 渲染 DPI")
    parser.add_argument("--ocr-min-chars", type=int, default=20, help="触发 OCR 的最小文本长度")
    parser.add_argument("--ocr-model-dir", default=None, help="EasyOCR 模型目录 (可写路径)")
    parser.add_argument("--ocr-min-pixels", type=int, default=32 * 32 * 3, help="Qwen OCR 最小像素")
    parser.add_argument("--ocr-max-pixels", type=int, default=32 * 32 * 8192, help="Qwen OCR 最大像素")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    rules = load_rules_from_excel(args.excel, sheet_name=args.sheet)
    pages = extract_pdf_text(
        args.pdf,
        ocr=args.ocr,
        ocr_engine=args.ocr_engine,
        ocr_lang=args.ocr_lang,
        ocr_dpi=args.ocr_dpi,
        ocr_min_chars=args.ocr_min_chars,
        ocr_model_dir=args.ocr_model_dir,
        ocr_min_pixels=args.ocr_min_pixels,
        ocr_max_pixels=args.ocr_max_pixels,
    )
    results = audit_rules(
        rules,
        pages,
        model=args.model,
        skip_llm=args.skip_llm,
        max_evidence=args.max_evidence,
    )

    output_path = Path(args.output)
    _write_json(output_path, results)

    if args.csv:
        _write_csv(Path(args.csv), results)

    print(f"已输出审核报告: {output_path}")


if __name__ == "__main__":
    main()
