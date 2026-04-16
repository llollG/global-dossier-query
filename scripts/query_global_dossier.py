#!/usr/bin/env python3
"""
USPTO Global Dossier 全球专利审查档案查询工具
=====================================
用法:
    python query_global_dossier.py <CN申请号> [--output <输出目录>] [--headless]

示例:
    python query_global_dossier.py 202211613450
    python query_global_dossier.py 202211613450 --output ./reports

功能:
    1. 打开 USPTO Global Dossier 网站
    2. 选择 Office=CN, Type=Application，输入申请号
    3. 获取所有同族专利成员列表
    4. 逐一访问每个成员的档案页面，获取 All Documents 和 Patent Family 信息
    5. 生成 Markdown 格式的全球审查档案报告
"""

import asyncio
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERROR] playwright 未安装，请先运行: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] beautifulsoup4 未安装，请先运行: pip install beautifulsoup4")
    sys.exit(1)

BASE_URL = "https://globaldossier.uspto.gov"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


# ──────────────────────────────────────────────
# Step 1: 搜索专利，获取同族列表页面
# ──────────────────────────────────────────────
async def search_patent(page, app_number: str) -> dict:
    """访问 Global Dossier 主页，设置 CN/Application，输入申请号并提交，返回结果页 URL 和页面 HTML。"""
    print(f"[1/5] 打开 Global Dossier 首页 ...")
    await page.goto(f"{BASE_URL}/home", wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(4000)

    print(f"[2/5] 选择 Office=CN ...")
    await page.select_option("#country", label="CN")
    await page.wait_for_timeout(1000)

    print(f"[3/5] 选择 Type=Application ...")
    await page.select_option("#type", label="Application")
    await page.wait_for_timeout(1000)

    print(f"[4/5] 输入申请号 {app_number} ...")
    # 移除 HTML 校验限制（CN 专利号为 12 位，超过原始 8 位 pattern 限制）
    await page.evaluate("""
        var q = document.getElementById('query');
        if(q){ q.removeAttribute('pattern'); q.removeAttribute('maxlength'); }
    """)
    await page.fill("#query", app_number)
    await page.wait_for_timeout(800)

    print(f"[5/5] 提交查询 ...")
    btn_disabled = await page.evaluate(
        "document.querySelector('button[name=\"search\"]') ? "
        "document.querySelector('button[name=\"search\"]').disabled : true"
    )
    if not btn_disabled:
        await page.click('button[name="search"]')
    else:
        # 降级：直接触发表单 submit 事件
        await page.evaluate("""
            var f = document.querySelector('form[name="pfsearch"]');
            if(f) f.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));
        """)

    # 等待结果页加载（URL 变为 /result/... 或 /details/...）
    for _ in range(30):
        await page.wait_for_timeout(1000)
        if "result/" in page.url or "details/" in page.url:
            break

    result_url = page.url
    print(f"    结果页 URL: {result_url}")

    # 等待同族列表渲染
    await page.wait_for_timeout(8000)

    # ── 勾选 NON-IP5 Office 复选框（显示 AU、CA 等非五局同族成员）
    print("    勾选 NON-IP5 Office 复选框 ...")
    non_ip5_found = False
    # 尝试多种选择器匹配 NON-IP5 复选框
    for selector in [
        'input[type="checkbox"][id*="non" i]',
        'input[type="checkbox"][id*="ip5" i]',
        'label:has-text("NON-IP5") input[type="checkbox"]',
        'label:has-text("Non-IP5") input[type="checkbox"]',
        'input[type="checkbox"]',
    ]:
        try:
            loc = page.locator(selector).first
            cnt = await loc.count()
            if cnt == 0:
                continue
            # 检查是否已勾选
            is_checked = await loc.is_checked()
            if not is_checked:
                await loc.check(timeout=3000)
                non_ip5_found = True
                print("    NON-IP5 Office 复选框已勾选")
            else:
                non_ip5_found = True
                print("    NON-IP5 Office 复选框已是勾选状态")
            break
        except Exception:
            continue

    if not non_ip5_found:
        print("    [WARN] 未找到 NON-IP5 Office 复选框，尝试通过 JavaScript 查找 ...")
        # 降级：通过 JS 查找含 NON-IP5 文本的 checkbox
        js_checked = await page.evaluate("""() => {
            const labels = document.querySelectorAll('label, span, div');
            for (const el of labels) {
                if (el.textContent && /non.?ip5/i.test(el.textContent)) {
                    const cb = el.querySelector('input[type="checkbox"]') 
                           || el.previousElementSibling 
                           || el.nextElementSibling;
                    if (cb && cb.type === 'checkbox') {
                        if (!cb.checked) { cb.click(); cb.dispatchEvent(new Event('change', {bubbles:true})); }
                        return true;
                    }
                }
            }
            // 最后兜底：查找所有 checkbox，点击未选中的（排除搜索表单中的）
            const allCb = document.querySelectorAll('input[type="checkbox"]');
            for (const cb of allCb) {
                const ctx = cb.closest('form') || cb.parentElement;
                if (ctx && !/pfsearch/i.test(ctx.id || '')) {
                    if (!cb.checked) { cb.click(); cb.dispatchEvent(new Event('change', {bubbles:true})); }
                    return true;
                }
            }
            return false;
        }""")
        if js_checked:
            print("    NON-IP5 Office 复选框已通过 JS 勾选")
        else:
            print("    [WARN] 未能勾选 NON-IP5 Office，部分非五局同族成员可能缺失")

    # 等待 NON-IP5 数据加载
    await page.wait_for_timeout(5000)

    # ── 分页加载：点击 "Load Next X records" 按钮直到全部加载
    print("    检查分页加载 ...")
    max_load_rounds = 20  # 防止无限循环
    for round_idx in range(max_load_rounds):
        load_btn_found = False
        # 尝试匹配 "Load Next N records" 按钮
        for selector in [
            'button:has-text("Load Next")',
            'a:has-text("Load Next")',
            'button:has-text("load next")',
            'a:has-text("load next")',
        ]:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    btn_text = await loc.text_content()
                    print(f"    点击分页按钮: {btn_text.strip()}")
                    await loc.click(timeout=5000)
                    await page.wait_for_timeout(4000)
                    load_btn_found = True
                    break
            except Exception:
                continue
        
        if not load_btn_found:
            # 尝试 JS 兜底查找
            js_result = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button, a, [role="button"]');
                for (const btn of btns) {
                    const txt = btn.textContent || '';
                    if (/load\s+next/i.test(txt)) {
                        btn.click();
                        return txt.trim();
                    }
                }
                return null;
            }""")
            if js_result:
                print(f"    通过 JS 点击分页按钮: {js_result}")
                await page.wait_for_timeout(4000)
            else:
                print("    分页加载完成（无更多记录）")
                break

    page_text = await page.evaluate("document.body.innerText")
    page_html = await page.evaluate("document.documentElement.outerHTML")

    return {
        "url": result_url,
        "text": page_text,
        "html": page_html,
    }


# ──────────────────────────────────────────────
# Step 2: 从 HTML 提取所有 View Dossier 链接
# ──────────────────────────────────────────────
# 专利局排序优先级（用于报告输出排序）
OFFICE_ORDER = {
    "US": 0,
    "EP": 1,
    "JP": 2,
    "KR": 3,
    "CN": 4,
    "WIPO": 5,
    "PCT": 6,
    # 其他局排在最后，按字母序
}


def office_sort_key(office: str) -> tuple[int, str]:
    """返回排序 key：(优先级序号, 局名)。非 IP5 局优先级为 99。"""
    return (OFFICE_ORDER.get(office, 99), office)


def extract_family_links(html: str) -> list[dict]:
    """
    解析同族页面 HTML，提取每个成员的 View Dossier URL 和元信息。
    
    去重策略：基于 OFFICE+APP_NUM 组合去重，同一案号只保留第一个链接。
    （Global Dossier 中同一案号可能对应多个 GD_ID / 案卷视图，实际为同一申请。）
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()          # 用于 href 级别去重（去掉 /true 重复）
    seen_members = set()  # 用于 OFFICE+APP_NUM 级别去重

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not href or "details/" not in href:
            continue
        # 去掉 /true 结尾（Open New Window 版本）
        href_clean = re.sub(r"/true$", "", href)
        if href_clean in seen:
            continue
        seen.add(href_clean)

        # 解析路径：details/{OFFICE}/{APP_NUM}/{TYPE}/{ID}
        m = re.search(r"details/([^/]+)/([^/]+)/([^/]+)/(\d+)", href_clean)
        if not m:
            continue
        office, app_num, app_type, gd_id = m.groups()

        # 基于 OFFICE+APP_NUM 去重
        member_key = f"{office}_{app_num}"
        if member_key in seen_members:
            continue
        seen_members.add(member_key)

        # 获取申请号展示文字
        sr = a.find("span", class_="sr-only")
        label = sr.get_text(strip=True) if sr else a.get_text(strip=True)

        full_url = f"{BASE_URL}/{href_clean}" if href_clean.startswith("details/") else f"{BASE_URL}{href_clean}"
        links.append({
            "office": office,
            "app_num": app_num,
            "app_type": app_type,
            "gd_id": gd_id,
            "url": full_url,
            "label": label,
        })

    # 按专利局优先级排序：US → EP → JP → KR → CN → WIPO → Others
    links.sort(key=lambda lk: office_sort_key(lk["office"]))

    return links


# ──────────────────────────────────────────────
# Step 3: 访问每个同族成员的 dossier 页面
# ──────────────────────────────────────────────
async def get_member_dossier(page, member: dict, output_dir: Path) -> dict:
    """访问单个成员的档案页，获取 All Documents 和 Patent Family 文本。"""
    key = f"{member['office']}_{member['app_num']}"
    print(f"  → 访问: {key}  ({member['url']})")

    await page.goto(member["url"], wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(7000)

    all_docs_text = await page.evaluate("document.body.innerText")
    all_docs_html = await page.evaluate("document.documentElement.outerHTML")

    # 保存原始文本（调试用）
    safe_key = key.replace("/", "_")
    txt_path = output_dir / f"alldocs_{safe_key}.txt"
    txt_path.write_text(f"URL: {member['url']}\n\n{all_docs_text}", encoding="utf-8")

    # 尝试点击 "Patent Fam." 按钮
    patent_fam_text = ""
    try:
        btn = page.locator('button:has-text("Patent Fam")')
        count = await btn.count()
        if count > 0:
            await btn.first.click(timeout=5000)
            await page.wait_for_timeout(5000)
            patent_fam_text = await page.evaluate("document.body.innerText")
            pf_path = output_dir / f"pf_{safe_key}.txt"
            pf_path.write_text(f"URL: {page.url}\n\n{patent_fam_text}", encoding="utf-8")
    except Exception as e:
        print(f"    [WARN] Patent Fam. 按钮点击失败: {e}")

    return {
        "key": key,
        "office": member["office"],
        "app_num": member["app_num"],
        "all_docs_text": all_docs_text,
        "all_docs_html": all_docs_html,
        "patent_fam_text": patent_fam_text,
        "url": member["url"],
    }


# ──────────────────────────────────────────────
# Step 4: 从文本中提取结构化文件列表
# ──────────────────────────────────────────────
def parse_documents_from_text(text: str) -> list[dict]:
    """
    从 All Docs 页面文本中提取文件列表。
    Global Dossier 文档列表格式大致为：
        文件名 \n 日期 \n 下载链接文字
    返回 [{"date": ..., "name": ...}, ...]
    """
    docs = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 找到文档列表起始位置
    start_idx = 0
    for i, line in enumerate(lines):
        if re.search(r"Documents", line, re.IGNORECASE):
            start_idx = i
            break

    # 日期正则（多种格式）
    date_pattern = re.compile(
        r"\b(\d{4}/\d{2}/\d{2}|\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b"
    )

    i = start_idx
    while i < len(lines):
        line = lines[i]
        # 跳过仅含 Download / View 等控件文字的行
        if re.match(r"^(Download|View|Open|PDF|Pages|download|view)$", line, re.IGNORECASE):
            i += 1
            continue
        # 若当前行或下一行包含日期，认为是一条文档记录
        date_match = date_pattern.search(line)
        if date_match:
            # 文件名在上一行
            doc_name = lines[i - 1] if i > 0 else line
            doc_date = date_match.group(0)
            docs.append({"date": doc_date, "name": doc_name})
        i += 1

    return docs


def extract_status_from_text(text: str, office: str) -> str:
    """从页面文本提取申请状态关键词。"""
    text_lower = text.lower()
    
    # 中文关键词（CNIPA）
    if office in ("CN",):
        if "授权" in text or "patent granted" in text_lower:
            return "✅ 已授权"
        if "驳回" in text or "rejected" in text_lower:
            return "❌ 已驳回"
        if "撤回" in text or "withdrawn" in text_lower:
            return "📁 已撤回"
        if "视为撤回" in text:
            return "📁 视为撤回"
        if "第一次审查意见" in text or "office action" in text_lower:
            return "🔄 审查意见待复审"
        if "补充检索" in text or "supplementary search" in text_lower:
            return "🔄 补充检索完成，等待 OA"
        if "第一次检索" in text or "first search" in text_lower:
            return "🔄 检索完成，等待 OA"
        return "🔄 实质审查中"

    # KR
    if office == "KR":
        if "registration" in text_lower or "registered" in text_lower:
            return "✅ 已授权"
        if "final rejection" in text_lower:
            return "❌ 最终驳回"
        if "abandoned" in text_lower:
            return "📁 已放弃"
        if "office action" in text_lower or "noa" in text_lower or "oa" in text_lower:
            return "🔄 审查意见待复审"
        return "🔄 实质审查中"

    # EP
    if office == "EP":
        if "granted" in text_lower:
            return "✅ 已授权"
        if "refused" in text_lower:
            return "❌ 已拒绝"
        if "withdrawn" in text_lower:
            return "📁 已撤回"
        if "examination report" in text_lower or "office action" in text_lower:
            return "🔄 审查报告待答复"
        return "🔄 审查中"

    # WIPO / PCT
    if office in ("WIPO", "PCT"):
        if "iprp" in text_lower or "chapter ii" in text_lower:
            return "✅ PCT 程序完结（IPRP 已发出）"
        if "chapter i" in text_lower:
            return "✅ PCT 检索/审查完成"
        return "✅ PCT 程序"

    # US
    if office == "US":
        if "patented" in text_lower or "issued" in text_lower:
            return "✅ 已授权"
        if "abandoned" in text_lower:
            return "📁 已放弃"
        if "office action" in text_lower:
            return "🔄 审查意见待复审"
        return "🔄 审查中"

    return "🔄 审查中"


# ──────────────────────────────────────────────
# Step 5: 生成报告
# ──────────────────────────────────────────────
def extract_most_recent_docs(text: str, n: int = 5) -> list[dict]:
    """提取最近 n 条文档（已按日期降序排列）。"""
    docs = parse_documents_from_text(text)
    # 按日期降序排列（简单字符串比较，格式 YYYY/MM/DD 或 YYYY-MM-DD 可直接比较）
    docs_sorted = sorted(docs, key=lambda d: d["date"], reverse=True)
    return docs_sorted[:n]


def generate_report(app_number: str, search_result: dict, members_data: list[dict]) -> str:
    """生成 Markdown 格式的全球审查档案报告，按专利局分组排序。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 专利局分组名映射
    OFFICE_DISPLAY = {
        "US": "🇺🇸 美国专利局（USPTO）",
        "EP": "🇪🇺 欧洲专利局（EPO）",
        "JP": "🇯🇵 日本特许厅（JPO）",
        "KR": "🇰🇷 韩国特许厅（KIPO）",
        "CN": "🇨🇳 中国国家知识产权局（CNIPA）",
        "WIPO": "🌐 世界知识产权组织（WIPO/PCT）",
        "PCT": "🌐 世界知识产权组织（WIPO/PCT）",
    }
    OTHER_OFFICE_DISPLAY = "🌍 其他专利局（NON-IP5）"

    # 按专利局优先级排序
    sorted_members = sorted(members_data, key=lambda m: office_sort_key(m["office"]))

    # 统计
    office_counts = {}
    for m in sorted_members:
        office_counts[m["office"]] = office_counts.get(m["office"], 0) + 1
    
    report = f"""# 全球专利审查档案报告

**查询案号：** CN {app_number}  
**数据来源：** USPTO Global Dossier (<https://globaldossier.uspto.gov>)  
**查询时间：** {now}  

---

## 一、专利家族概览

共发现 **{len(sorted_members)} 个**去重同族成员，分布于 **{len(office_counts)} 个**专利局：

| # | 专利局 | 申请号 | 审查状态 |
|---|--------|--------|----------|
"""
    for i, m in enumerate(sorted_members, 1):
        status = extract_status_from_text(m["all_docs_text"], m["office"])
        report += f"| {i} | {m['office']} | {m['app_num']} | {status} |\n"

    report += "\n---\n\n## 二、各成员详细审查信息\n\n"

    # 按专利局分组输出
    current_section = None
    for m in sorted_members:
        key = m["key"]
        office = m["office"]
        app_num = m["app_num"]
        status = extract_status_from_text(m["all_docs_text"], office)

        # 判断分组标题
        if office in OFFICE_DISPLAY:
            section_title = OFFICE_DISPLAY[office]
        else:
            section_title = OTHER_OFFICE_DISPLAY

        if section_title != current_section:
            current_section = section_title
            report += f"## {section_title}\n\n"

        report += f"### {office} — {app_num}\n\n"
        report += f"- **档案链接：** {m['url']}\n"
        report += f"- **审查状态：** {status}\n\n"

        # Most Recent Documents（最近5条）
        recent_docs = extract_most_recent_docs(m["all_docs_text"], n=5)
        report += "#### Most Recent Documents（最近 5 条）\n\n"
        if recent_docs:
            report += "| 日期 | 文件名称 |\n|------|----------|\n"
            for doc in recent_docs:
                report += f"| {doc['date']} | {doc['name']} |\n"
        else:
            # 备用：截取文档区文本片段
            text = m["all_docs_text"]
            if "Documents" in text:
                idx = text.index("Documents")
                snippet = text[idx:idx+800].strip()
                report += f"```\n{snippet}\n```\n"
            else:
                report += "_（未能解析文件列表，请参阅原始文本文件）_\n"

        report += "\n"

    # 状态汇总
    report += "---\n\n## 三、审查状态汇总\n\n"
    status_summary = {}
    for m in sorted_members:
        status = extract_status_from_text(m["all_docs_text"], m["office"])
        if status not in status_summary:
            status_summary[status] = []
        status_summary[status].append(f"{m['office']}-{m['app_num']}")

    report += "| 状态 | 数量 | 成员 |\n|------|------|------|\n"
    for status, members in sorted(status_summary.items(), key=lambda x: x[1], reverse=True):
        report += f"| {status} | {len(members)} | {', '.join(members)} |\n"

    report += "\n---\n\n## 四、说明\n\n"
    report += """- 本报告基于 USPTO Global Dossier 公开数据自动生成，数据实时性依赖 USPTO 与各专利局的数据同步。
- "Most Recent Documents" 为各局档案中按日期降序排列的最新文件。
- 同族成员已按 OFFICE+APP_NUM 去重，同一申请号仅保留一个档案视图。
- 如需查看完整文件列表或下载原始文档，请访问上方各档案链接。
- 审查状态为基于页面文本关键词的自动识别，可能存在误差，请以各局官方系统为准。
"""

    return report


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def run(app_number: str, output_dir: Path, headless: bool = True):
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=UA,
        )
        page = await ctx.new_page()

        # ── 搜索
        search_result = await search_patent(page, app_number)

        # 保存家族页面 HTML（用于调试和链接提取）
        html_path = output_dir / "family_page_full.html"
        html_path.write_text(search_result["html"], encoding="utf-8")
        txt_path = output_dir / "family_page_text.txt"
        txt_path.write_text(search_result["text"], encoding="utf-8")

        # ── 提取同族链接
        print("\n[提取同族成员链接]")
        links = extract_family_links(search_result["html"])
        if not links:
            print("[WARN] 未从 HTML 中提取到任何 View Dossier 链接，尝试从文本推断...")
        else:
            print(f"  找到 {len(links)} 个同族成员:")
            for lk in links:
                print(f"    {lk['office']} / {lk['app_num']}")

        # 保存链接列表
        links_path = output_dir / "family_links.json"
        links_path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")

        # ── 访问每个成员
        print(f"\n[访问各同族成员档案页]")
        members_data = []
        for lk in links:
            data = await get_member_dossier(page, lk, output_dir)
            members_data.append(data)

        await browser.close()

    # ── 生成报告
    print(f"\n[生成报告]")
    report_text = generate_report(app_number, search_result, members_data)

    report_path = output_dir / f"全球专利审查档案报告_CN{app_number}.md"
    report_path.write_text(report_text, encoding="utf-8")

    print(f"\n[PASS] Report generated: {report_path}")
    return str(report_path)


def main():
    parser = argparse.ArgumentParser(
        description="USPTO Global Dossier — CN专利全球审查档案查询工具"
    )
    parser.add_argument("app_number", help="12位中国专利申请号，例如 202211613450")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="报告输出目录（默认：当前目录下的 patent-reports/<申请号>/）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="以无头模式运行浏览器（默认启用）",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        default=False,
        help="显示浏览器窗口（调试用）",
    )
    args = parser.parse_args()

    app_number = re.sub(r"\s+", "", args.app_number)
    if not re.match(r"^\d{12}$", app_number):
        print(f"[ERROR] 申请号格式不正确，需为12位数字，收到: {app_number!r}")
        sys.exit(1)

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path.cwd() / "patent-reports" / f"CN{app_number}"

    headless = not args.show_browser

    print(f"╔══════════════════════════════════════════════╗")
    print(f"  USPTO Global Dossier 全球专利审查档案查询")
    print(f"  申请号: CN {app_number}")
    print(f"  输出目录: {output_dir}")
    print(f"╚══════════════════════════════════════════════╝\n")

    asyncio.run(run(app_number, output_dir, headless=headless))


if __name__ == "__main__":
    main()
