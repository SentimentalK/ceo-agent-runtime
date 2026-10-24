# pptx-to-md: PPTX 全文本化与 Markdown 转换工具

基于 Python 的全本地、开源、免 API 的 PPTX 文本化工具。支持原生文本提取、表格转 Markdown、图表文本提取、演讲者备注（Speaker Notes）、嵌套 Group 递归解析、以及基于 ONNX 的轻量级本地 OCR（中英文支持与图像文字去噪/去重）。

---

## 特性

* **原生文本与表格提取**：精准提取段落、列表及 Markdown 格式表格。
* **本地轻量级 OCR**：基于 RapidOCR (PaddleOCR ONNX 运行时)，开箱即用，无需配置复杂的 GPU/Paddle 依赖，在 Mac/Linux/Windows 上秒级本地推理。
* **阅读顺序重排**：按照自然从上到下、从左到右的位置重排元素。
* **智能去重与去噪**：去除同一 Slide 内原生文本与图片 OCR 导致的重复内容，过滤低置信度噪点及全篇高频 Header/Footer。
* **演讲者备注**：自动提取 Slide Speaker Notes 附在对应 Slide 尾部。

---

## 快速安装

```bash
./setup   # 创建 .venv（需要 Python 3.10-3.12）
```

---

## 使用方法

### 1. 转换单个文件

```bash
./run path/to/lecture.pptx
# 输出将默认保存在 ./output/lecture.md
```

指定输出路径：
```bash
./run path/to/lecture.pptx -o ./custom_output/result.md
```

### 2. 批量处理整个目录

```bash
./run ./input -o ./output
```

### 3. 可选参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--no-ocr` | False | 关闭图片 OCR 识别 |
| `--confidence` | `0.55` | OCR 识别置信度阈值 (0.0 ~ 1.0) |
| `--no-dedup` | False | 关闭 Slide 内部相似文本去重 |
| `--keep-footers`| False | 保留全篇反复出现的页眉页脚与页码 |

---

## 输出示例

```markdown
---
source: lecture-01.pptx
slides: 3
---

# Slide 1

Introduction to Databases

Oracle & Distributed Systems

---

# Slide 2

| Database Service | Default Port |
| --- | --- |
| Oracle Listener | 1521 |
| PostgreSQL | 5432 |

### Notes

Remember to remind students to test their listener config before lab.

---

# Slide 3

Architecture Flow

API Gateway -> Auth -> DB
```
