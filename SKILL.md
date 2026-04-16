---
name: global-dossier-query
description: >
  This skill should be used when the user wants to query the USPTO Global Dossier
  (https://globaldossier.uspto.gov) for a Chinese patent application (12-digit CN application number)
  and generate a global prosecution report covering all patent family members.
  Trigger phrases include: "查询全球档案", "Global Dossier", "同族专利审查", "全球审查档案",
  "查 Global Dossier", "CN专利全球审查报告", or any request involving a 12-digit CN application
  number combined with global/international prosecution status.
---

# Global Dossier 全球专利审查档案查询技能

## 功能概述

本技能自动完成以下全流程：

1. 使用 Playwright 打开 USPTO Global Dossier 网站
2. 设置 Office=CN、Type=Application，输入用户提供的 12 位中国专利申请号
3. 提取所有同族专利成员列表及各成员的 View Dossier 链接
4. 逐一访问每个成员的档案页，获取 All Documents 和 Patent Family 信息
5. 识别各成员审查状态，提取 Most Recent Documents（最近文件）
6. 生成 Markdown 格式的全球审查档案报告

## 使用前提

运行前确认 Python 环境中已安装以下依赖：

```bash
pip install playwright beautifulsoup4
python -m playwright install chromium
```

## 执行方式

### 方式 A：直接运行脚本（推荐）

```bash
python scripts/query_global_dossier.py <12位CN申请号> [--output <输出目录>]
```

示例：
```bash
# 查询 CN202211613450，报告保存到当前目录的 patent-reports/CN202211613450/
python scripts/query_global_dossier.py 202211613450

# 指定输出目录
python scripts/query_global_dossier.py 202211613450 --output ./my-reports

# 显示浏览器窗口（调试用）
python scripts/query_global_dossier.py 202211613450 --show-browser
```

脚本输出：
- `全球专利审查档案报告_CN<申请号>.md` — 主报告文件（Markdown）
- `alldocs_<OFFICE>_<APP_NUM>.txt` — 各成员 All Docs 原始文本（调试）
- `pf_<OFFICE>_<APP_NUM>.txt` — 各成员 Patent Family 原始文本（调试）
- `family_links.json` — 提取到的同族成员 URL 列表
- `family_page_full.html` — 家族列表页完整 HTML（调试）

### 方式 B：编写代码调用

```python
import asyncio
from pathlib import Path
# 将 scripts/query_global_dossier.py 中的 run() 函数导入使用
from query_global_dossier import run

asyncio.run(run("202211613450", Path("./output")))
```

## 操作流程说明

### 1. 页面交互要点

- CN 申请号为 12 位，必须先用 JavaScript 移除页面 input 的 `pattern` 属性限制
- 搜索按钮在三个字段（Office/Type/Number）填完后才会 enabled
- Global Dossier 是 Angular SPA，详情页需等待 ~7 秒 JavaScript 渲染
- 参考 `references/api_reference.md` 获取页面选择器和等待策略详情

### 2. 同族链接提取

从家族页面 HTML 中解析 `<a href="details/...">` 链接，格式为：
`details/{OFFICE}/{APP_NUM}/{APP_TYPE}/{GD_ID}`

### 3. 报告结构

生成的 Markdown 报告包含：
- **家族概览表**：各成员专利局、申请号、审查状态
- **各成员详细信息**：档案链接、审查状态、Most Recent Documents 表格、Patent Family 摘要

### 4. 审查状态识别

基于页面文本关键词自动识别（CN/KR/EP/US/PCT 各有不同关键词），详见 `references/api_reference.md`。

## 注意事项

- Global Dossier 数据来源于各局与 USPTO 的同步，部分局（如 CNIPA）的最新文件可能有延迟
- 同族成员数量较多时（>10个）整体运行时间约 3–8 分钟
- 若网络超时，建议重试或使用 `--show-browser` 模式观察页面状态
- 审查状态为关键词自动识别，请以各局官方系统为最终依据
