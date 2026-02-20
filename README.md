# MR 场地安装前图纸自动审核系统

## 功能
- 解析 Excel 审核要点，生成结构化规则
- 内置 92 条审核要点（来自 `MR check.xlsx`），可不上传 Excel 直接审核
- 解析 PDF 文本并保留页码
- 调用阿里千问 (Qwen) 大模型进行规则判断
- 输出结构化审核报告 (JSON/CSV)

## 环境要求
- Python 3.10+
- 依赖：`openpyxl` (已用于 Excel 解析)
- PDF 解析依赖：`pdfplumber`
- OCR 依赖（可选）：`tesseract` + `pytesseract`、`easyocr`、Qwen OCR API 或 OpenAI OCR API

安装 PDF 依赖示例：
```bash
pip install pdfplumber
```

安装 OCR 依赖示例：
```bash
brew install tesseract
pip install pytesseract
```

使用 EasyOCR：
```bash
pip install easyocr
```

## 配置
设置环境变量：
- `QWEN_API_KEY`：必填
- `QWEN_API_BASE_URL`：可选，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `QWEN_MODEL`：可选，默认 `qwen-plus`

## 运行
使用内置审核要点（无需 Excel）：
```bash
python3 -m mr_audit.cli \
  --pdf "/Users/chesterzhou/Documents/MRINS/MRmaterial/1.5T/南京中西医结合医院-Achieva 1.5T-移机布局图.pdf" \
  --output /Users/chesterzhou/Documents/MRINS/audit_report.json \
  --csv /Users/chesterzhou/Documents/MRINS/audit_report.csv \
  --use-builtin-rules
```

使用 Excel 覆盖内置规则：
```bash
python3 -m mr_audit.cli \
  --excel "/Users/chesterzhou/Documents/MRINS/MR check.xlsx" \
  --pdf "/Users/chesterzhou/Documents/MRINS/MR图纸资料/南京中西医结合医院-Achieva 1.5T/南京中西医结合医院-Achieva 1.5T-移机布局图.pdf" \
  --output /Users/chesterzhou/Documents/MRINS/audit_report.json \
  --csv /Users/chesterzhou/Documents/MRINS/audit_report.csv
```

如仅提取证据不调用大模型：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --skip-llm
```

启用 OCR：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr
```

使用 EasyOCR：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine easyocr
```

如果默认模型目录不可写，可指定模型目录：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine easyocr --ocr-model-dir /Users/chesterzhou/Documents/MRINS/.easyocr
```

使用 Qwen OCR API（无需本地模型，走 API）：  
需设置 `QWEN_API_KEY`（或 `DASHSCOPE_API_KEY`），可选 `QWEN_OCR_MODEL`。  
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine qwen_ocr
```

可显式指定模型，并配置回退模型：
```bash
python3 -m mr_audit.cli \
  --excel ... --pdf ... --ocr --ocr-engine qwen_ocr \
  --ocr-model qwen-vl-ocr-latest \
  --ocr-model-fallbacks "qwen2.5-vl-72b-instruct,qwen2.5-vl-7b-instruct"
```

如需走本地代理，可加：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine qwen_ocr \
  --https-proxy http://127.0.0.1:7890 --http-proxy http://127.0.0.1:7890
```

可先做连通性检查，失败时会打印代理环境信息：
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine qwen_ocr \
  --network-check --network-timeout 8
```

使用 OpenAI OCR API（无需本地模型，走 API）：  
需设置 `OPENAI_API_KEY`，可选 `OPENAI_BASE_URL`、`OPENAI_OCR_MODEL`。  
```bash
python3 -m mr_audit.cli --excel ... --pdf ... --ocr --ocr-engine openai_ocr
```

## 输出字段
- 大类
- 小类
- 审核要求
- 判断结果（PASS / FAIL / UNKNOWN）
- 证据（页码 + 原文）
- 判断说明
- 置信度（0-1）

## Web 页面运行
可直接启动本地网页，上传文件后点击审核：

```bash
streamlit run /Users/chesterzhou/Documents/MRINS/mr_audit_web.py
```

页面内支持：
- 使用内置审核要点，或上传 Excel 覆盖
- 上传 PDF
- 配置 Qwen Key / Base URL / 审核模型
- 选择 OCR 引擎与 OCR 模型（含回退模型）
- 配置 HTTP/HTTPS 代理
- 一键审核并在页面展示结果
- 下载 JSON / CSV 报告
