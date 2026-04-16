# global-dossier-query

> 一个 [WorkBuddy](https://www.codebuddy.cn/docs/workbuddy/Overview) Skill，自动查询 [USPTO Global Dossier](https://globaldossier.uspto.gov) 上的中国专利申请，生成涵盖所有同族成员的全球专利审查档案报告（Markdown 格式）。

[English Documentation](./README.md)

---

## 功能概述

输入一个 12 位中国专利申请号（CN），本 Skill 自动完成以下全流程：

1. 使用 Playwright（无头浏览器）打开 USPTO Global Dossier 网站
2. 设置 Office = **CN**、Type = **Application**，输入 CN 申请号
3. 提取所有同族专利成员列表及 **View Dossier** 链接
4. 逐一访问每个成员的档案页，获取：
   - **All Documents**：完整文件列表（含日期和文件名）
   - **Patent Family**：各成员审查状态
5. 通过关键词自动识别审查状态（已授权 / 已驳回 / 审查中 / 审查意见待复审…）
6. 生成结构化的 **Markdown 报告**，覆盖所有同族成员

---

## 使用前提

Python 3.8+ 及以下依赖：

```bash
pip install playwright beautifulsoup4
python -m playwright install chromium
```

---

## 使用方式

### 方式 A：直接运行脚本（推荐）

```bash
python scripts/query_global_dossier.py <12位CN申请号> [--output <输出目录>]
```

**示例：**

```bash
# 查询 CN202211613450，报告保存到 ./patent-reports/CN202211613450/
python scripts/query_global_dossier.py 202211613450

# 指定自定义输出目录
python scripts/query_global_dossier.py 202211613450 --output ./my-reports

# 显示浏览器窗口（调试用）
python scripts/query_global_dossier.py 202211613450 --show-browser
```

**输出文件（保存至 `<输出目录>/CN<申请号>/`）：**

| 文件 | 说明 |
|------|------|
| `全球专利审查档案报告_CN<申请号>.md` | 主报告文件（Markdown） |
| `family_links.json` | 提取到的同族成员 URL 列表 |
| `alldocs_<OFFICE>_<NUM>.txt` | 各成员 All Docs 原始文本（调试用） |
| `pf_<OFFICE>_<NUM>.txt` | 各成员 Patent Family 原始文本（调试用） |
| `family_page_full.html` | 家族列表页完整 HTML（调试用） |

### 方式 B：Python 代码调用

```python
import asyncio
from pathlib import Path
from scripts.query_global_dossier import run

asyncio.run(run("202211613450", Path("./output")))
```

---

## 报告结构

生成的 Markdown 报告包含：

### 1. 家族概览表

| 专利局 | 申请号 | 审查状态 |
|--------|--------|----------|
| CN | 202211613450 | 审查中 — 审查意见 |
| KR | 20170012160 | 已授权 |
| US | 17/123456 | 已授权 |
| EP | 22123456 | 审查报告已发出 |

### 2. 各成员详细信息

每个同族成员包含：
- 指向 Global Dossier 档案页的直接链接
- 审查状态摘要
- **最新文件列表**（文件名、日期、文件类型）
- Patent Family 摘要节选

---

## 审查状态识别逻辑

通过页面关键词自动识别，各局对应关键词如下：

| 专利局 | 状态 | 识别关键词 |
|--------|------|-----------|
| CN（CNIPA）| 已授权 | 授权、patent granted |
| CN | 已驳回 | 驳回、rejected |
| CN | 已撤回 | 撤回、withdrawn |
| CN | 审查意见待复审 | 第一次审查意见、office action |
| KR（KIPO）| 已授权 | registration、registered |
| KR | 最终驳回 | final rejection |
| EP（EPO）| 已授权 | granted |
| EP | 审查报告已发出 | examination report |
| PCT（WIPO）| 第二章完成 | iprp、chapter ii |

> **说明：** 审查状态为关键词自动识别，请以各局官方系统为最终依据。

---

## 技术说明

- **CN 申请号为 12 位数字。** Global Dossier 搜索框有 8 位 `pattern` 限制，脚本会通过 JavaScript 在输入前自动移除该限制。
- Global Dossier 是 Angular SPA，每个档案详情页需约 7 秒 JavaScript 渲染时间。
- 同族成员数量较多（>10 个）时，整体运行时间约 3–8 分钟。
- 若发生超时，建议重试或使用 `--show-browser` 模式观察页面状态。
- CNIPA 数据可能因 USPTO 同步间隔而存在轻微延迟。

---

## 目录结构

```
global-dossier-query/
├── SKILL.md                      # WorkBuddy Skill 定义
├── README.md                     # 英文文档
├── README.zh.md                  # 本文件（中文文档）
├── LICENSE                       # MIT License
├── .gitignore
├── scripts/
│   └── query_global_dossier.py   # 主自动化脚本
├── references/
│   └── api_reference.md          # 页面选择器、等待策略、状态关键词参考
└── assets/                       # （保留，用于截图/示意图）
```

---

## WorkBuddy 集成

本 Skill 安装后，通过以下自然语言短语触发：

- `查询全球档案`
- `Global Dossier`
- `同族专利审查`
- `全球审查档案`
- `查 Global Dossier`
- `CN专利全球审查报告`
- 任何包含 12 位 CN 申请号 + 全球/国际审查状态的请求

---

## License

[MIT](./LICENSE)
