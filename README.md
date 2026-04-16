# global-dossier-query

> A [WorkBuddy](https://www.codebuddy.cn/docs/workbuddy/Overview) Skill that automates querying the [USPTO Global Dossier](https://globaldossier.uspto.gov) for a Chinese patent application and generates a full global prosecution report in Markdown.

[中文文档](./README.zh.md)

---

## What It Does

Given a 12-digit Chinese application number (CN), this skill:

1. Opens the USPTO Global Dossier website using Playwright (headless browser)
2. Sets Office = **CN**, Type = **Application**, and inputs the CN application number
3. Extracts all patent family members and their **View Dossier** links
4. Visits each family member's dossier page to retrieve:
   - **All Documents** — complete list with dates and file names
   - **Patent Family** — prosecution status of each family member
5. Identifies prosecution status from page content (granted / rejected / pending / OA received…)
6. Generates a structured **Markdown report** covering all family members

---

## Prerequisites

Python 3.8+ and the following packages:

```bash
pip install playwright beautifulsoup4
python -m playwright install chromium
```

---

## Usage

### Option A — Run as a script (recommended)

```bash
python scripts/query_global_dossier.py <12-digit CN app number> [--output <output dir>]
```

**Examples:**

```bash
# Query CN202211613450, save report to ./patent-reports/CN202211613450/
python scripts/query_global_dossier.py 202211613450

# Specify a custom output directory
python scripts/query_global_dossier.py 202211613450 --output ./my-reports

# Show browser window (useful for debugging)
python scripts/query_global_dossier.py 202211613450 --show-browser
```

**Output files (in `<output_dir>/CN<app_number>/`):**

| File | Description |
|------|-------------|
| `全球专利审查档案报告_CN<app>.md` | Main Markdown report |
| `family_links.json` | Extracted family member URLs |
| `alldocs_<OFFICE>_<NUM>.txt` | Raw All Docs text per member (debug) |
| `pf_<OFFICE>_<NUM>.txt` | Raw Patent Family text per member (debug) |
| `family_page_full.html` | Full family list page HTML (debug) |

### Option B — Import in Python

```python
import asyncio
from pathlib import Path
from scripts.query_global_dossier import run

asyncio.run(run("202211613450", Path("./output")))
```

---

## Report Structure

The generated Markdown report contains:

### 1. Family Overview Table

| Office | Application No. | Prosecution Status |
|--------|-----------------|--------------------|
| CN | 202211613450 | Pending — Office Action |
| KR | 20170012160 | Registered |
| US | 17/123456 | Granted |
| EP | 22123456 | Examination Report Issued |

### 2. Per-Member Detail

For each family member:
- Direct link to the Global Dossier dossier page
- Prosecution status summary
- **Most Recent Documents** table (file name, date, type)
- Patent Family summary excerpt

---

## Prosecution Status Recognition

Status is auto-detected from page keywords:

| Office | Status | Keywords |
|--------|--------|----------|
| CN (CNIPA) | Granted | 授权, patent granted |
| CN | Rejected | 驳回, rejected |
| CN | Withdrawn | 撤回, withdrawn |
| CN | Pending OA | 第一次审查意见, office action |
| KR (KIPO) | Registered | registration, registered |
| KR | Final Rejection | final rejection |
| EP (EPO) | Granted | granted |
| EP | Examination | examination report |
| PCT (WIPO) | Chapter II done | iprp, chapter ii |

> **Note:** Auto-detection is based on keyword matching. For official status, always refer to each patent office's system.

---

## Technical Notes

- **CN app numbers are 12 digits.** The Global Dossier search field has an 8-digit `pattern` attribute that is removed via JavaScript before input.
- Global Dossier is an Angular SPA — each dossier detail page requires ~7 seconds of JavaScript rendering time.
- Family pages with **10+ members** may take 3–8 minutes to fully process.
- If a timeout occurs, retry or use `--show-browser` to observe the browser state.
- Data from CNIPA may be slightly delayed due to USPTO synchronization intervals.

---

## File Structure

```
global-dossier-query/
├── SKILL.md                      # WorkBuddy Skill definition
├── README.md                     # This file (English)
├── README.zh.md                  # Chinese documentation
├── LICENSE                       # MIT License
├── .gitignore
├── scripts/
│   └── query_global_dossier.py   # Main automation script
├── references/
│   └── api_reference.md          # Page selectors, wait strategies, status keywords
└── assets/                       # (reserved for screenshots / diagrams)
```

---

## WorkBuddy Integration

This is a WorkBuddy Skill. When installed, it is triggered by natural language phrases such as:

- `查询全球档案`
- `Global Dossier`
- `同族专利审查`
- `全球审查档案`
- `查 Global Dossier`
- `CN专利全球审查报告`
- Any 12-digit CN application number + global/international prosecution context

---

## License

[MIT](./LICENSE)
