from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import requests

from .audit_engine import AuditResult, audit_rules
from .builtin_rules import BUILTIN_RULES_COUNT, BUILTIN_RULES_SOURCE, load_builtin_rules
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


def _resolve_check_url(args: argparse.Namespace) -> str:
    if args.ocr and args.ocr_engine == "openai_ocr":
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    # qwen_ocr and text llm both use this base
    return os.getenv("QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url


def _network_check(check_url: str, timeout: float) -> None:
    target = _origin(check_url)
    try:
        resp = requests.get(target, timeout=timeout)
    except Exception as exc:
        http_proxy = os.getenv("HTTP_PROXY", "")
        https_proxy = os.getenv("HTTPS_PROXY", "")
        no_proxy = os.getenv("NO_PROXY", "")
        raise RuntimeError(
            f"网络检查失败: {target}; error={type(exc).__name__}: {exc}; "
            f"HTTP_PROXY={http_proxy!r}; HTTPS_PROXY={https_proxy!r}; NO_PROXY={no_proxy!r}"
        ) from exc
    if resp.status_code >= 500:
        raise RuntimeError(f"网络检查失败: {target} 返回状态码 {resp.status_code}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MR 场地安装前图纸自动审核")
    parser.add_argument("--excel", required=False, help="审核要点 Excel 路径")
    parser.add_argument("--pdf", required=True, help="MR 场地图纸 PDF 路径")
    parser.add_argument("--output", default="audit_report.json", help="输出 JSON 路径")
    parser.add_argument("--sheet", default=None, help="Excel 表名 (可选)")
    parser.add_argument("--use-builtin-rules", action="store_true", help="使用内置审核要点（无需 Excel）")
    parser.add_argument("--model", default=None, help="Qwen 模型名称 (可选)")
    parser.add_argument("--skip-llm", action="store_true", help="仅提取证据，不调用大模型")
    parser.add_argument("--max-evidence", type=int, default=3, help="每条规则最多证据条数")
    parser.add_argument("--csv", default=None, help="可选输出 CSV 路径")
    parser.add_argument("--ocr", action="store_true", help="启用 OCR (需 tesseract + pytesseract)")
    parser.add_argument(
        "--ocr-engine",
        default="tesseract",
        help="OCR 引擎: tesseract / easyocr / qwen_ocr / openai_ocr",
    )
    parser.add_argument("--ocr-lang", default="chi_sim+eng", help="OCR 语言 (tesseract 语种)")
    parser.add_argument("--ocr-dpi", type=int, default=300, help="OCR 渲染 DPI")
    parser.add_argument("--ocr-min-chars", type=int, default=20, help="触发 OCR 的最小文本长度")
    parser.add_argument("--ocr-model-dir", default=None, help="EasyOCR 模型目录 (可写路径)")
    parser.add_argument("--ocr-model", default=None, help="OCR 模型名 (主要用于 qwen_ocr/openai_ocr)")
    parser.add_argument("--ocr-model-fallbacks", default=None, help="OCR 回退模型，逗号分隔，仅 qwen_ocr")
    parser.add_argument("--ocr-min-pixels", type=int, default=32 * 32 * 3, help="Qwen OCR 最小像素")
    parser.add_argument("--ocr-max-pixels", type=int, default=32 * 32 * 8192, help="Qwen OCR 最大像素")
    parser.add_argument("--http-proxy", default=None, help="HTTP 代理，如 http://127.0.0.1:7890")
    parser.add_argument("--https-proxy", default=None, help="HTTPS 代理，如 http://127.0.0.1:7890")
    parser.add_argument("--no-proxy", default=None, help="NO_PROXY 值，如 localhost,127.0.0.1")
    parser.add_argument("--network-check", action="store_true", help="运行前检查模型 API 网络连通性")
    parser.add_argument("--network-timeout", type=float, default=8.0, help="网络检查超时时间（秒）")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.http_proxy:
        os.environ["HTTP_PROXY"] = args.http_proxy
        os.environ["http_proxy"] = args.http_proxy
    if args.https_proxy:
        os.environ["HTTPS_PROXY"] = args.https_proxy
        os.environ["https_proxy"] = args.https_proxy
    if args.no_proxy:
        os.environ["NO_PROXY"] = args.no_proxy
        os.environ["no_proxy"] = args.no_proxy

    if args.network_check:
        check_url = _resolve_check_url(args)
        _network_check(check_url, timeout=args.network_timeout)
        print(f"网络检查通过: {_origin(check_url)}")

    if args.use_builtin_rules or not args.excel:
        rules = load_builtin_rules()
        print(f"已加载内置审核要点: {BUILTIN_RULES_COUNT} 条（来源: {BUILTIN_RULES_SOURCE}）")
    else:
        rules = load_rules_from_excel(args.excel, sheet_name=args.sheet)
    ocr_model_fallbacks = None
    if args.ocr_model_fallbacks:
        ocr_model_fallbacks = [
            x.strip() for x in args.ocr_model_fallbacks.split(",") if x.strip()
        ]
    pages = extract_pdf_text(
        args.pdf,
        ocr=args.ocr,
        ocr_engine=args.ocr_engine,
        ocr_lang=args.ocr_lang,
        ocr_dpi=args.ocr_dpi,
        ocr_min_chars=args.ocr_min_chars,
        ocr_model_dir=args.ocr_model_dir,
        ocr_model=args.ocr_model,
        ocr_model_fallbacks=ocr_model_fallbacks,
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
