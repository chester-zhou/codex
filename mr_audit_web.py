from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

from mr_audit.audit_engine import AuditResult, audit_rules
from mr_audit.builtin_rules import BUILTIN_RULES_COUNT, BUILTIN_RULES_SOURCE, load_builtin_rules
from mr_audit.excel_parser import load_rules_from_excel
from mr_audit.pdf_parser import extract_pdf_text


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url


def _network_check(url: str, timeout: float) -> None:
    target = _origin(url)
    resp = requests.get(target, timeout=timeout)
    if resp.status_code >= 500:
        raise RuntimeError(f"网络检查失败: {target} 返回状态码 {resp.status_code}")


def _set_env(name: str, value: str) -> None:
    if value:
        os.environ[name] = value


def _to_rows(results: List[AuditResult]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for r in results:
        evidence_list = [asdict(item) for item in r.evidence]
        evidence_text = " | ".join([f"p{item['page']}:{item['quote']}" for item in evidence_list])
        rows.append(
            {
                "大类": r.major,
                "小类": r.minor,
                "审核要求": r.requirement,
                "判断结果": r.result,
                "证据": evidence_text,
                "判断说明": r.reason,
                "置信度": r.confidence,
                "_evidence_json": evidence_list,
            }
        )
    return rows


def main() -> None:
    st.set_page_config(page_title="MR 图纸自动审核", layout="wide")
    st.title("MR 场地安装前图纸自动审核")
    st.caption("可直接使用内置审核要点，或上传 Excel 覆盖；上传 PDF 后一键输出结构化审核结果。")

    with st.sidebar:
        st.subheader("模型与网络配置")
        server_key_exists = bool(os.getenv("QWEN_API_KEY", "").strip())
        qwen_api_key = st.text_input(
            "QWEN API Key",
            value="",
            type="password",
            help="填写 DashScope API Key（留空时使用服务器环境变量）",
            placeholder="留空使用服务器密钥",
        )
        st.caption(f"服务器密钥状态: {'已配置' if server_key_exists else '未配置'}")
        qwen_base_url = st.text_input(
            "QWEN API Base URL",
            value=os.getenv("QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        qwen_model = st.text_input("审核模型", value=os.getenv("QWEN_MODEL", "qwen-plus"))

        st.subheader("OCR 配置")
        enable_ocr = st.checkbox("启用 OCR", value=True)
        ocr_engine = st.selectbox("OCR 引擎", ["qwen_ocr", "tesseract", "easyocr", "openai_ocr"], index=0)
        ocr_model = st.text_input("OCR 模型", value=os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr-latest"))
        ocr_fallbacks_raw = st.text_input("OCR 回退模型（逗号分隔）", value="")
        force_ocr = st.checkbox("强制每页都 OCR", value=True)
        ocr_min_chars = 99999 if force_ocr else st.number_input("触发 OCR 的最小文本长度", min_value=0, value=20)
        ocr_dpi = st.number_input("OCR DPI", min_value=72, max_value=600, value=300)

        st.subheader("执行配置")
        skip_llm = st.checkbox("仅提取证据，不调用审核模型", value=False)
        max_evidence = st.number_input("每条规则最多证据数", min_value=1, max_value=10, value=3)
        network_check = st.checkbox("运行前网络检查", value=True)
        network_timeout = st.number_input("网络检查超时（秒）", min_value=1.0, max_value=30.0, value=8.0)

        st.subheader("代理（可选）")
        http_proxy = st.text_input("HTTP_PROXY", value=os.getenv("HTTP_PROXY", ""))
        https_proxy = st.text_input("HTTPS_PROXY", value=os.getenv("HTTPS_PROXY", ""))
        no_proxy = st.text_input("NO_PROXY", value=os.getenv("NO_PROXY", ""))

    use_builtin_rules = st.checkbox(
        f"使用内置审核要点（{BUILTIN_RULES_COUNT} 条，来源: {BUILTIN_RULES_SOURCE}）",
        value=True,
    )
    excel_file = st.file_uploader("上传审核要点 Excel（可选）", type=["xlsx", "xlsm", "xls"])
    pdf_file = st.file_uploader("上传 MR 图纸 PDF", type=["pdf"])

    run = st.button(
        "开始审核",
        type="primary",
        disabled=not (pdf_file and (use_builtin_rules or excel_file)),
    )
    if not run:
        return

    try:
        effective_qwen_key = qwen_api_key.strip() or os.getenv("QWEN_API_KEY", "").strip()
        if not effective_qwen_key:
            raise RuntimeError("缺少 QWEN_API_KEY（请在页面输入，或在服务器环境变量中配置）")

        _set_env("QWEN_API_KEY", effective_qwen_key)
        _set_env("QWEN_API_BASE_URL", qwen_base_url)
        _set_env("QWEN_MODEL", qwen_model)
        _set_env("QWEN_OCR_MODEL", ocr_model)
        _set_env("HTTP_PROXY", http_proxy)
        _set_env("http_proxy", http_proxy)
        _set_env("HTTPS_PROXY", https_proxy)
        _set_env("https_proxy", https_proxy)
        _set_env("NO_PROXY", no_proxy)
        _set_env("no_proxy", no_proxy)

        if network_check:
            _network_check(qwen_base_url, timeout=float(network_timeout))
            st.success(f"网络检查通过: {_origin(qwen_base_url)}")

        ocr_model_fallbacks = [x.strip() for x in ocr_fallbacks_raw.split(",") if x.strip()]

        with st.spinner("审核进行中，请稍候..."):
            with tempfile.TemporaryDirectory(prefix="mr_audit_web_") as tmp_dir:
                pdf_path = Path(tmp_dir) / pdf_file.name
                pdf_path.write_bytes(pdf_file.getvalue())
                excel_path = None
                if not use_builtin_rules:
                    if not excel_file:
                        raise RuntimeError("未上传 Excel，且未启用内置审核要点")
                    excel_path = Path(tmp_dir) / excel_file.name
                    excel_path.write_bytes(excel_file.getvalue())

                if use_builtin_rules:
                    rules = load_builtin_rules()
                else:
                    rules = load_rules_from_excel(str(excel_path))
                pages = extract_pdf_text(
                    str(pdf_path),
                    ocr=enable_ocr,
                    ocr_engine=ocr_engine,
                    ocr_dpi=int(ocr_dpi),
                    ocr_min_chars=int(ocr_min_chars),
                    ocr_model=ocr_model or None,
                    ocr_model_fallbacks=ocr_model_fallbacks or None,
                )
                results = audit_rules(
                    rules,
                    pages,
                    model=qwen_model or None,
                    skip_llm=skip_llm,
                    max_evidence=int(max_evidence),
                )
    except Exception as exc:
        st.error(f"审核失败: {type(exc).__name__}: {exc}")
        st.stop()

    rows = _to_rows(results)
    df = pd.DataFrame(rows)

    st.success(f"审核完成：共 {len(df)} 条规则")
    st.dataframe(df[["大类", "小类", "审核要求", "判断结果", "证据", "判断说明", "置信度"]], use_container_width=True)

    counts = df["判断结果"].value_counts(dropna=False).rename_axis("判断结果").reset_index(name="数量")
    st.subheader("结果统计")
    st.dataframe(counts, use_container_width=True)

    report_json = json.dumps(
        [
            {
                "大类": row["大类"],
                "小类": row["小类"],
                "审核要求": row["审核要求"],
                "判断结果": row["判断结果"],
                "证据": row["_evidence_json"],
                "判断说明": row["判断说明"],
                "置信度": row["置信度"],
            }
            for row in rows
        ],
        ensure_ascii=False,
        indent=2,
    )
    report_csv = df[["大类", "小类", "审核要求", "判断结果", "证据", "判断说明", "置信度"]].to_csv(index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "下载 JSON 报告",
            data=report_json,
            file_name="audit_report_web.json",
            mime="application/json",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "下载 CSV 报告",
            data=report_csv,
            file_name="audit_report_web.csv",
            mime="text/csv",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
