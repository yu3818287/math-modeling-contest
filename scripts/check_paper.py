#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_paper.py —— 数学建模竞赛论文提交前硬校验

检查 references/verification.md 中列出的 A 类（脚本硬校验）项目：
  A1 数字可追溯          A2 页数合规            A3 摘要页合规
  A4 结构完整性          A5 核心检验完整性      A6 图表编号与引用
  A7 公式编号            A8 三线表合规          A9 身份信息泄露
另附：参考文献 \cite 与 refs.bib 一致性、LaTeX 溢出警告统计。

用法：
    python scripts/check_paper.py paper/main.tex --ruleset cumcm --numbers results/numbers.json

常用参数：
    --ruleset {cumcm,mcm}   赛事口径，决定页数上限与结构要求（默认 cumcm）
    --numbers PATH          numbers.json 路径，用于数字溯源（强烈建议提供）
    --pdf PATH              编译后的 PDF，用于精确页数统计（建议提供）
    --bib PATH              refs.bib 路径，默认在 main.tex 同目录查找
    --identity-words A,B    额外的身份敏感词（学校名、队号等）
    --json PATH             把报告同时写成 JSON
    --quiet                 只输出问题项

退出码：0 = 全部通过；1 = 存在失败项；2 = 用法或读文件错误
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# 规则口径
# --------------------------------------------------------------------------

RULESETS: dict[str, dict[str, Any]] = {
    "cumcm": {
        "name": "国赛 CUMCM",
        "body_page_limit": 30,
        "body_page_note": "正文不超过 30 页（2026 修订稿）；附录页数不限",
        "total_page_limit": None,
        "toc_allowed": False,
        "toc_note": "国赛明确要求正文不要目录",
        "structure": [
            ("摘要", [r"摘要", r"\\begin\s*\{abstract\}", r"\\abstract\s*\{"]),
            ("关键词", [r"关键词", r"\\keywords?"]),
            ("问题重述", [r"问题重述", r"问题提出", r"问题背景"]),
            ("问题分析", [r"问题分析", r"问题的?分析"]),
            ("模型假设", [r"模型假设", r"问题假设", r"假设与(?:说明|合理性)", r"\\section\*?\{[^}]*假设"]),
            ("符号说明", [r"符号(?:说明|表|约定)", r"\\section\*?\{[^}]*符号"]),
            ("模型建立与求解", [r"模型的?建立", r"建模与求解", r"模型求解", r"模型的?构建"]),
            ("结果分析", [r"结果(?:分析|与讨论)", r"求解结果", r"结果与(?:分析|检验)"]),
            ("模型检验", [r"模型(?:的)?检验", r"检验与(?:分析|灵敏度)", r"模型(?:的)?验证"]),
            ("优缺点与改进", [r"优缺点", r"模型的?评价", r"模型的?推广"]),
            ("参考文献", [r"参考文献", r"\\begin\s*\{thebibliography\}", r"\\bibliography\s*\{"]),
            ("附录", [r"附录", r"\\appendix"]),
        ],
        "checks_sections": [
            ("误差分析", [r"误差(?:分析|检验)"]),
            ("灵敏度分析", [r"灵敏(?:度|性)"]),
            ("稳健性分析", [r"稳健(?:性|度)", r"鲁棒性"]),
        ],
        "ai_required_markers": [
            ("AI 工具使用声明（规定措辞二选一）", [
                # 《人工智能工具使用规定（2026 年试行）》第 3 条指定的两句话
                r"本参赛队在竞赛过程中未使用任何\s*AI\s*工具",
                r"本参赛队在竞赛过程中使用了\s*AI\s*工具",
                # 容错：用户略有改写时仍能识别出来
                r"未使用任何\s*AI\s*工具",
                r"使用了\s*AI\s*工具",
                r"AI\s*工具?使用声明",
            ]),
        ],
        # 国赛 2026 新规：声明须位于参考文献之前
        "ai_declaration_before": [
            r"参考文献", r"\\begin\s*\{thebibliography\}", r"\\bibliography\s*\{",
        ],
        "identity_patterns": [
            r"[\u4e00-\u9fa5A-Za-z]{1,12}\s*(?:大学|学院|职业技术学院)",
            r"队号", r"参赛队号", r"学号", r"参赛学校", r"赛区",
            r"指导教师", r"指导老师", r"队员",
        ],
    },
    "mcm": {
        "name": "美赛 MCM/ICM",
        "body_page_limit": None,
        "body_page_note": "美赛不单独限制正文页数，限制的是整个提交文件",
        "total_page_limit": 25,
        "total_page_note": (
            "整个提交文件不超过 25 页，包含 Summary Sheet、正文、目录、"
            "参考文献、附录与代码；仅 Report on Use of AI 不计入"
        ),
        "toc_allowed": True,
        "toc_note": "美赛鼓励放目录（且计入 25 页）",
        "structure": [
            ("Summary Sheet", [r"\\section\*?\{Summary", r"Summary\s+Sheet", r"\\begin\{summary\}"]),
            ("Keywords", [r"Keywords?", r"关键词"]),
            ("Introduction / Restatement", [r"Introduction", r"Restatement", r"Problem\s+Restatement"]),
            ("Assumptions", [r"Assumptions?"]),
            ("Notations", [r"Notations?", r"Notation\s+Table"]),
            ("Model Development", [r"Model\s+Development", r"The\s+Model", r"Modeling"]),
            ("Results", [r"Results?"]),
            ("Sensitivity / Stability", [r"Sensitivit", r"Stabilit"]),
            ("Strengths and Weaknesses", [r"Strengths?\s+and\s+Weaknesses?", r"Strengths?\\?\s*(and|&)\\?\s*Weaknesses?"]),
            ("References", [r"References?", r"Bibliography"]),
            ("Appendices", [r"Appendices?", r"Appendix"]),
        ],
        "checks_sections": [
            ("Error analysis", [r"Error\s+(?:Analysis|Test)", r"误差"]),
            ("Sensitivity analysis", [r"Sensitivit"]),
            ("Stability analysis", [r"Stabilit", r"Robustness"]),
        ],
        "ai_required_markers": [
            ("Report on Use of AI", [r"Report\s+on\s+Use\s+of\s+AI", r"Use\s+of\s+AI"]),
        ],
        "identity_patterns": [
            r"[\u4e00-\u9fa5A-Za-z]{1,12}\s*(?:大学|学院)",
            r"Advisor", r"指导教师", r"指导老师", r"参赛学校", r"学号", r"姓名",
            r"Institution", r"University",
        ],
    },
}


# --------------------------------------------------------------------------
# 报告结构
# --------------------------------------------------------------------------

@dataclass
class Finding:
    check_id: str
    title: str
    status: str          # pass | fail | warn | skip
    detail: str = ""
    items: list[str] = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
        for f in self.findings:
            c[f.status] = c.get(f.status, 0) + 1
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.__dict__ for f in self.findings],
            "counts": self.counts(),
        }


# --------------------------------------------------------------------------
# LaTeX 读取与预处理
# --------------------------------------------------------------------------

IGNORE_MARKER = re.compile(r"%\s*check\s*:\s*ignore", re.IGNORECASE)


def read_tex(path: str, depth: int = 0) -> tuple[str, list[str]]:
    """读取 .tex，展开 \\input / \\include，返回 (全文, 原始行列表)。"""
    if depth > 10:
        raise RuntimeError(f"\\input 嵌套过深，疑似循环引用：{path}")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    base = os.path.dirname(os.path.abspath(path))

    def repl(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        if not target.lower().endswith(".tex"):
            target += ".tex"
        sub = target if os.path.isabs(target) else os.path.join(base, target)
        if os.path.exists(sub):
            sub_text, _ = read_tex(sub, depth + 1)
            return sub_text
        return f"% [check_paper] 未找到被包含文件: {target}\n"

    text = re.sub(r"\\(?:input|include)\s*\{([^}]*)\}", repl, text)
    return text, text.splitlines()


def split_comment(line: str) -> tuple[str, str]:
    """按第一个未转义的 % 拆成 (代码部分, 注释部分)。"""
    out = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == "%":
            return "".join(out), line[i:]
        out.append(ch)
        i += 1
    return "".join(out), ""


def strip_commands(text: str) -> str:
    """抹掉命令与排版参数，避免其中的数字被当作正文数字。

    这里要处理的噪声主要有三类：
      1. 引用类命令 \\ref{2} —— 里面的数字是编号，不是内容；
      2. 版面设置 \\geometry{left=2.5cm} —— 是排版尺寸，不是论文结论；
      3. 尺寸单位 12pt / 0.8\\textwidth —— 同样是排版参数。
    漏掉任何一类，校验报告都会被无关数字淹没，最后没人看。
    """
    for cmd in ("ref", "eqref", "pageref", "autoref", "cite", "citep", "citet", "label",
                "usepackage", "documentclass", "RequirePackage", "includegraphics",
                "input", "include", "bibliography", "bibliographystyle",
                "thebibliography", "hspace", "vspace", "rule", "geometry",
                "setlength", "addtolength", "setcounter", "addtocounter",
                "fontsize", "linespread", "renewcommand", "newcommand",
                "captionsetup", "hypersetup", "sisetup", "parbox", "makebox",
                "raisebox", "vskip", "hskip", "fontsize", "baselinestretch"):
        text = re.sub(r"\\%s\s*\*?\s*(?:\[[^\]]*\])?\s*\{[^}]*\}" % re.escape(cmd),
                      " ", text)
    # 可选参数 [12pt] [0.8\textwidth] [htbp] 等
    text = re.sub(r"\[[^\[\]]*\]", " ", text)
    # 尺寸：12pt / 2.5cm / 0.8\textwidth
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:cm|mm|pt|bp|in|em|ex|pc|dd|cc|sp)\b", " ", text)
    text = re.sub(r"\d*\.?\d*\s*\\(?:textwidth|linewidth|textheight|columnwidth|"
                  r"paperwidth|paperheight|baselineskip|parskip)", " ", text)
    # 数学结构：上下标与分数里的数字不是论文结论
    text = re.sub(r"\\[dt]?frac\s*\{[^{}]*\}\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"\\binom\s*\{[^{}]*\}\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"[_^]\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"[_^]\s*\S", " ", text)
    # 环境名，以及环境名后紧跟的一个参数（如 \begin{thebibliography}{9}）
    text = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}(?:\s*\{[^}]*\})?", " ", text)
    # 其余命令名
    text = re.sub(r"\\[a-zA-Z@]+\s*\*?", " ", text)
    text = re.sub(r"[{}$&_^~\\]", " ", text)
    return text


NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def normalize_number(tok: str) -> float | None:
    """把一个 token 解析成数值；不是数值则返回 None。

    这里要区分两类逗号：`1,234,567` 是千分位写法，`1,6,5,2` 是路径节点序列。
    论文里经常出现「依次执行 1,6,5,2 与 7,4,8,3」这种写法，
    如果一律去掉逗号当成 1652，校验报告就会被一串无关数字淹没。
    判据是：千分位写法中每个逗号后面恰好三位数字。
    """
    if "," in tok:
        parts = tok.split(",")
        if all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3:
            t = "".join(parts)
        else:
            return None
    else:
        t = tok

    if t.count(".") > 1:
        parts = t.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            t = "".join(parts)
        else:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def is_year(v: float) -> bool:
    return v.is_integer() and 1900 <= v <= 2099


def extract_numbers(lines: list[str]) -> list[dict[str, Any]]:
    """从 tex 正文里提取所有数值 token。

    参考文献条目的内容（年份、页码、卷期、访问日期）不算论文结论，
    整体跳过，否则每条引文都会产生一堆无法追溯的数字。
    """
    found: list[dict[str, Any]] = []
    in_bib = False
    for idx, raw in enumerate(lines, start=1):
        code, _comment = split_comment(raw)
        if re.search(r"\\begin\s*\{thebibliography\}", code):
            in_bib = True
            continue
        if re.search(r"\\end\s*\{thebibliography\}", code):
            in_bib = False
            continue
        if in_bib or IGNORE_MARKER.search(raw):
            continue
        cleaned = strip_commands(code)
        for m in NUM_RE.finditer(cleaned):
            tok = m.group(0)
            val = normalize_number(tok)
            if val is None:
                continue
            if is_year(val):
                continue
            found.append({
                "line": idx,
                "token": tok,
                "value": val,
                "display_guess": tok,
                "context": raw.strip()[:160],
            })
    return found


# --------------------------------------------------------------------------
# A1 数字可追溯
# --------------------------------------------------------------------------

def load_numbers(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def build_number_index(entries: dict[str, dict[str, Any]]) -> tuple[list[float], list[str]]:
    values: list[float] = []
    displays: list[str] = []
    for key, ent in entries.items():
        v = ent.get("value")
        if isinstance(v, (int, float)):
            values.append(float(v))
        d = ent.get("display")
        if isinstance(d, str):
            displays.append(d)
        # display 里嵌的数字也纳入匹配，例如 "128.45 万元"
        if isinstance(d, str):
            for m in NUM_RE.finditer(d):
                val = normalize_number(m.group(0))
                if val is not None:
                    values.append(val)
    return values, displays


def check_numbers(report: Report, tex_text: str, lines: list[str],
                  numbers_path: str | None) -> None:
    cid, title = "A1", "数字可追溯"
    if not numbers_path:
        report.add(Finding(cid, title, "skip",
                           "未提供 --numbers，跳过数字溯源检查。"
                           "这是本脚本最有价值的一项，建议总是提供 results/numbers.json。"))
        return

    entries = load_numbers(numbers_path)
    if not entries:
        report.add(Finding(cid, title, "fail",
                           f"numbers.json 不存在或为空：{numbers_path}"))
        return

    values, displays = build_number_index(entries)
    extracted = extract_numbers(lines)

    untraceable: list[str] = []
    for item in extracted:
        tok, val = item["token"], item["value"]
        # 命中 display 字符串
        if any(tok in d for d in displays):
            continue
        # 命中数值（容差比较）
        hit = False
        for v in values:
            if abs(v - val) <= max(1e-9, abs(v) * 1e-6):
                hit = True
                break
        if hit:
            continue
        untraceable.append(f"L{item['line']}: {tok}  ←  {item['context']}")

    if not untraceable:
        report.add(Finding(cid, title, "pass",
                           f"{len(extracted)} 个数值全部可追溯到 numbers.json"
                           f"（共 {len(entries)} 条登记）"))
        return

    # 区分高风险（非整数或量级较大）与低风险（小整数）
    high, low = [], []
    for line in untraceable:
        m = re.search(r":\s*([\d.,]+)\s", line)
        v = normalize_number(m.group(1)) if m else None
        if v is None or (v.is_integer() and abs(v) <= 10):
            low.append(line)
        else:
            high.append(line)

    detail = (f"{len(untraceable)} / {len(extracted)} 个数值无法追溯"
              f"（高风险 {len(high)}，小整数等低风险 {len(low)}）")
    items = []
    if high:
        items.append("—— 高风险（非整数或数值较大，必须处理）——")
        items.extend(high)
    if low:
        items.append("—— 低风险（小整数，可能只是分类计数或序号）——")
        items.extend(low[:30])
        if len(low) > 30:
            items.append(f"... 另有 {len(low) - 30} 条低风险项未列出")

    report.add(Finding(cid, title, "fail" if high else "warn", detail, items))


# --------------------------------------------------------------------------
# A2 页数
# --------------------------------------------------------------------------

def try_locate_body_pages(pdf_path: str) -> int | None:
    """尝试通过定位附录起始页来推算正文页数。

    国赛只在正文上设页数上限、附录不限，而 PDF 的总页数里含附录，
    所以单看总页数无法判断是否违规。这里提取每页文本、寻找"附录"标题，
    把附录之前的页数作为正文页数（再扣掉摘要页）。

    扫描件、字体缺 ToUnicode 映射等情况会导致提取失败，此时返回 None，
    由调用方退回到"提示人工确认"——宁可让用户自己数一遍，也不要瞎猜一个数。
    """
    reader = None
    for mod in ("pypdf", "PyPDF2"):
        try:
            reader = __import__(mod).PdfReader(pdf_path)
            break
        except Exception:
            continue
    if reader is None:
        return None
    try:
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if re.search(r"^\s*附\s*录\s*[A-Z一二三四五六1-9]?", text, re.MULTILINE):
                if idx >= 2:          # 至少要有摘要页 + 一页正文
                    return idx - 1    # 扣掉摘要页
                return None
    except Exception:
        return None
    return None


def count_pdf_pages(pdf_path: str) -> tuple[int | None, str]:
    """统计 PDF 页数，并区分「读不出来」的几种不同原因。

    这三种情况给用户的下一步动作完全不同，所以不能笼统报一句「无法解析」：
      - 文件不存在      → 先去编译
      - 文件被截断      → 重新编译（编译中途被打断，交上去会被判无效）
      - 缺少解析库      → pip install pypdf
    """
    if not os.path.exists(pdf_path):
        return None, f"PDF 不存在：{pdf_path}"

    try:
        with open(pdf_path, "rb") as fh:
            blob = fh.read()
    except Exception as exc:
        return None, f"读取失败：{exc}"

    if not blob.startswith(b"%PDF"):
        return None, "文件不是有效的 PDF（缺少 %PDF 文件头）"
    truncated = b"%%EOF" not in blob[-4096:]

    # 优先用解析库
    lib_err = None
    for mod in ("pypdf", "PyPDF2"):
        try:
            m = __import__(mod)
            reader = m.PdfReader(pdf_path)
            n = len(reader.pages)
            note = f"由 {mod} 读取"
            if truncated:
                note += "；但文件缺少 %%EOF 标记，可能被截断，建议重新完整编译一次"
            return n, note
        except Exception as exc:
            lib_err = f"{mod}: {type(exc).__name__}: {exc}"
            continue

    # 退路一：页树里的 /Count（对使用对象流的 PDF 1.5+ 仍有效）
    counts = [int(x) for x in re.findall(rb"/Count\s+(\d+)", blob)]
    if counts and max(counts) > 0:
        note = f"由 PDF 页树 /Count 估算（{lib_err or '未安装解析库'}）"
        if truncated:
            note += "；且文件缺少 %%EOF 标记，可能被截断"
        return max(counts), note

    # 退路二：直接数页对象
    n = len(re.findall(rb"/Type\s*/Page(?![s])", blob))
    if n:
        return n, "由 PDF 页对象计数估算（未安装解析库，可能略有偏差）"

    if truncated:
        return None, ("PDF 不完整：缺少 %%EOF 标记，编译可能未完成或文件被截断。"
                      "请重新完整编译后再校验——提交一个截断的 PDF 会被判为无效。")
    return None, (f"无法解析页数，且没有可用的解析库（{lib_err}）。"
                  f"建议 pip install pypdf 后重试。")


def check_pages(report: Report, cfg: dict[str, Any], pdf_path: str | None) -> None:
    cid, title = "A2", "页数合规"
    if not pdf_path:
        report.add(Finding(cid, title, "skip",
                           "未提供 --pdf，无法精确统计页数。"
                           "请先编译出 PDF 再跑一次："
                           "xelatex -interaction=nonstopmode main.tex"))
        return

    pages, how = count_pdf_pages(pdf_path)
    if pages is None:
        report.add(Finding(cid, title, "fail" if "不完整" in how else "skip", how))
        return

    problems, notes = [], [f"总页数 {pages}（{how}）"]

    if cfg.get("total_page_limit"):
        # 美赛：整个提交文件都有上限，总页数超了就是超了
        lim = cfg["total_page_limit"]
        notes.append(cfg["total_page_note"])
        if pages > lim:
            problems.append(f"总页数 {pages} 超过上限 {lim} 页，超出 {pages - lim} 页")
        report.add(Finding(cid, title, "fail" if problems else "pass",
                           "；".join(notes), problems))
        return

    if cfg.get("body_page_limit"):
        # 国赛：只有正文有上限，附录不限。而总页数里含附录，
        # 因此总页数超标并不等于违规——这里不能直接判失败，只能提示人工确认。
        lim = cfg["body_page_limit"]
        notes.append(cfg["body_page_note"])
        body_pages = try_locate_body_pages(pdf_path)
        if body_pages is not None:
            notes.append(f"据附录起始页推算，正文约 {body_pages} 页")
            if body_pages > lim:
                problems.append(f"正文约 {body_pages} 页，超过上限 {lim} 页")
            report.add(Finding(cid, title, "fail" if problems else "pass",
                               "；".join(notes), problems))
            return
        if pages > lim:
            report.add(Finding(cid, title, "warn",
                               "；".join(notes),
                               [f"总页数 {pages} 超过 {lim} 页，但国赛附录页数不限，"
                                f"总页数超标不等于违规。",
                                "请人工确认正文（摘要页之后、附录之前）的实际页数是否 ≤ "
                                f"{lim} 页——这一步脚本无法可靠代劳。"]))
            return

    report.add(Finding(cid, title, "pass", "；".join(notes), problems))


# --------------------------------------------------------------------------
# A3 目录与摘要页
# --------------------------------------------------------------------------

def check_toc(report: Report, cfg: dict[str, Any], lines: list[str]) -> None:
    cid, title = "A3", "目录与摘要页合规"
    has_toc = any(re.search(r"\\tableofcontents", split_comment(l)[0]) for l in lines)
    problems, notes = [], [cfg["toc_note"]]

    if cfg["toc_allowed"] and not has_toc:
        notes.append("未检测到 \\tableofcontents。美赛鼓励放目录，但这是建议而非硬性要求。")
    if not cfg["toc_allowed"] and has_toc:
        problems.append("检测到 \\tableofcontents，但该赛事要求正文不要目录，请删除")

    # 摘要页独立成页
    has_clearpage = any(re.search(r"\\(?:clearpage|newpage)", split_comment(l)[0])
                        for l in lines)
    if not has_clearpage:
        problems.append("未检测到 \\clearpage 或 \\newpage，摘要页可能与其他内容同页")
    else:
        notes.append("检测到分页命令，摘要页是否真正独占一页仍需看编译后的 PDF 确认")

    report.add(Finding(cid, title, "fail" if problems else "pass",
                       "；".join(notes), problems))


# --------------------------------------------------------------------------
# A4 / A5 结构与检验项
# --------------------------------------------------------------------------

def match_sections(lines: list[str], spec: list[tuple[str, list[str]]]) -> list[tuple[str, bool]]:
    result = []
    for label, pats in spec:
        hit = False
        for line in lines:
            code, _ = split_comment(line)
            for p in pats:
                if re.search(p, code, re.IGNORECASE):
                    hit = True
                    break
            if hit:
                break
        result.append((label, hit))
    return result


def check_structure(report: Report, cfg: dict[str, Any], lines: list[str]) -> None:
    res = match_sections(lines, cfg["structure"])
    missing = [label for label, ok in res if not ok]
    detail = f"共 {len(res)} 个必备模块，缺失 {len(missing)} 个"
    if missing:
        report.add(Finding("A4", "全文结构完整性", "fail", detail,
                           [f"未检测到：{m}" for m in missing]))
    else:
        report.add(Finding("A4", "全文结构完整性", "pass", detail))


def first_line_matching(lines: list[str], pats: list[str]) -> int | None:
    """返回第一个命中任一模式的正文行号（1 起），没有则 None。"""
    for i, line in enumerate(lines, 1):
        code, _ = split_comment(line)
        for p in pats:
            if re.search(p, code, re.IGNORECASE):
                return i
    return None


def check_core_tests(report: Report, cfg: dict[str, Any], lines: list[str]) -> None:
    res = match_sections(lines, cfg["checks_sections"])
    missing = [label for label, ok in res if not ok]
    detail = "误差分析 / 灵敏度分析 / 稳健性分析"
    if missing:
        report.add(Finding("A5", "核心检验完整性", "fail",
                           f"缺少 {len(missing)} 项检验", [f"未检测到：{m}" for m in missing]))
    else:
        report.add(Finding("A5", "核心检验完整性", "pass", detail + " 均已出现"))

    # AI 使用声明
    ai_res = match_sections(lines, cfg["ai_required_markers"])
    ai_missing = [label for label, ok in ai_res if not ok]
    if ai_missing:
        report.add(Finding("A5b", "AI 使用声明", "warn",
                           "未检测到 AI 工具使用声明。两个赛事都要求：使用了 AI 必须声明，"
                           "未使用也要按规定的措辞明确声明未使用，否则属违规。",
                           [f"未检测到：{m}" for m in ai_missing]))
        return

    # 位置检查：国赛 2026 新规要求声明位于参考文献之前
    anchor = cfg.get("ai_declaration_before")
    if anchor:
        ai_line = None
        for _label, pats in cfg["ai_required_markers"]:
            ai_line = first_line_matching(lines, pats)
            if ai_line:
                break
        ref_line = first_line_matching(lines, list(anchor))
        if ai_line and ref_line and ai_line > ref_line:
            report.add(Finding("A5b", "AI 使用声明", "fail",
                               f"检测到 AI 使用声明（第 {ai_line} 行），但它出现在"
                               f"「参考文献」（第 {ref_line} 行）之后。",
                               ["国赛 2026 年新规要求：AI 工具使用声明应设置在"
                                "论文参考文献之前，位置错误属于不符合规定",
                                "注意美赛相反——Report on Use of AI 放在正文之后"]))
            return
        if ai_line and ref_line:
            report.add(Finding("A5b", "AI 使用声明", "pass",
                               f"已检测到声明（第 {ai_line} 行），"
                               f"位于参考文献（第 {ref_line} 行）之前，位置正确"))
            return

    report.add(Finding("A5b", "AI 使用声明", "pass", "已检测到 AI 工具使用声明"))


# --------------------------------------------------------------------------
# A6 / A7 图表与公式
# --------------------------------------------------------------------------

def check_floats(report: Report, tex_text: str, lines: list[str]) -> None:
    """逐个数图/表环境，检查标题、标签与正文引用。

    只统计 figure/table 环境内部的 label，不要把公式的 label 也算进来——
    否则公式编号会被误报成"孤儿图表"。
    """
    floats = re.findall(
        r"\\begin\s*\{(figure|table)\*?\}(.*?)\\end\s*\{\1\*?\}",
        tex_text, re.DOTALL)
    refs = set(re.findall(r"\\(?:ref|eqref|autoref|pageref)\s*\{([^}]*)\}", tex_text))

    problems: list[str] = []
    for i, (kind, body) in enumerate(floats, 1):
        kind_cn = "图" if kind == "figure" else "表"
        if not re.search(r"\\caption\s*\{", body):
            problems.append(f"第 {i} 个{kind_cn}没有 \\caption，图表必须有编号与标题")
        labels = re.findall(r"\\label\s*\{([^}]*)\}", body)
        if not labels:
            problems.append(f"第 {i} 个{kind_cn}没有 \\label，无法在正文中引用")
        for lb in labels:
            if lb not in refs:
                problems.append(
                    f"第 {i} 个{kind_cn}的 \\label{{{lb}}} 从未被正文引用（孤儿图表）")

    detail = f"图/表环境 {len(floats)} 个，正文引用 {len(refs)} 处"
    if not floats:
        report.add(Finding("A6", "图表编号与引用", "warn",
                           detail, ["论文中没有检测到 figure/table 环境，"
                                    "请确认是否真的不需要图表"]))
        return
    report.add(Finding("A6", "图表编号与引用", "fail" if problems else "pass",
                       detail, problems))


def check_equations(report: Report, tex_text: str, lines: list[str]) -> None:
    numbered = len(re.findall(r"\\begin\s*\{(?:equation|align|gather|multline)\}", tex_text))
    numbered += len(re.findall(r"\\\[", tex_text)) * 0
    display_unnumbered = len(re.findall(r"\\begin\s*\{(?:equation\*|align\*|gather\*)\}", tex_text))
    inline_display = len(re.findall(r"\\\[", tex_text))

    problems: list[str] = []
    # 正文里用"上式""下式"指代公式，而不是用编号引用
    vague = [f"L{i}: {l.strip()[:120]}" for i, l in enumerate(lines, 1)
             if re.search(r"(上式|下式|前面的式子|上述公式)", split_comment(l)[0])]
    if vague:
        problems.append("正文中用「上式/下式」指代公式，应改用 \\eqref 引用公式编号")
    detail = (f"带编号公式环境 {numbered}，无编号 {display_unnumbered}，"
              f"行间公式 \\[ {inline_display}")
    if numbered == 0 and (display_unnumbered or inline_display):
        problems.append("所有行间公式都未编号。重要公式应使用带编号环境，便于正文引用")
    report.add(Finding("A7", "公式编号规范", "fail" if problems else "pass",
                       detail, problems + vague[:10]))


# --------------------------------------------------------------------------
# A8 三线表
# --------------------------------------------------------------------------

def check_tables(report: Report, tex_text: str) -> None:
    table_envs = re.findall(r"\\begin\s*\{table\*?\}(.*?)\\end\s*\{table\*?\}",
                            tex_text, re.DOTALL)
    tabulars = re.findall(r"\\begin\s*\{(?:tabular|tabularx|longtable)\*?\}"
                          r"(?:\[[^\]]*\])?\s*\{([^}]*)\}", tex_text)

    problems: list[str] = []
    for i, spec in enumerate(tabulars, 1):
        if "|" in spec:
            problems.append(f"第 {i} 个表格的列格式含竖线：{{{spec.strip()}}}，三线表不得有竖线")
    for i, body in enumerate(table_envs, 1):
        if re.search(r"\\hline", body) and not re.search(r"\\toprule", body):
            problems.append(f"第 {i} 个表格使用 \\hline 而非 booktabs 的 \\toprule/\\midrule/\\bottomrule")
        if re.search(r"\\toprule", body) and not re.search(r"\\bottomrule", body):
            problems.append(f"第 {i} 个表格有 \\toprule 但没有 \\bottomrule，三线表不完整")

    if not tabulars and not table_envs:
        report.add(Finding("A8", "三线表合规", "skip", "未检测到表格"))
        return

    detail = f"检测到 {len(table_envs)} 个表格环境、{len(tabulars)} 个 tabular"
    report.add(Finding("A8", "三线表合规", "fail" if problems else "pass",
                       detail, problems))


# --------------------------------------------------------------------------
# A9 身份信息
# --------------------------------------------------------------------------

def check_identity(report: Report, cfg: dict[str, Any], lines: list[str],
                   extra_words: list[str]) -> None:
    """扫描身份信息泄露。

    两个赛事都禁止在论文任何位置出现学校、姓名、赛区信息，违反可能被判违规。
    这里分两级：硬命中（明确的身份表述）直接判失败；软命中（单独的"大学/学院"
    这类词）单独列出，因为正文里可能只是普通用词，需要人确认。
    """
    pats = list(cfg["identity_patterns"]) + [re.escape(w) for w in extra_words if w]
    hard: list[str] = []
    soft: list[str] = []
    flagged: set[int] = set()

    # 赛事与机构的正式名称里天然含「大学」，它们出现在注释或出处说明中不是身份泄露。
    # 先把这些名称整段抹掉再扫描，否则每一句引用规范的地方都会误报。
    official_names = [
        "全国大学生数学建模竞赛", "美国大学生数学建模竞赛", "大学生数学建模竞赛",
        "中国大学生在线", "数学建模竞赛", "高等教育出版社",
    ]

    def scrub(line: str) -> str:
        for name in official_names:
            line = line.replace(name, "　")
        return line

    # \\author{} 非空 = 署名，几乎必然是身份泄露
    for i, line in enumerate(lines, 1):
        m = re.search(r"\\author\s*\{([^}]*)\}", line)
        if m and m.group(1).strip():
            hard.append(f"L{i}: \\author 填了内容「{m.group(1).strip()[:60]}」，"
                        f"论文中不得出现作者信息")
            flagged.add(i)
        # \\affiliation / \\institute / \\school 等
        for cmd in ("affiliation", "institute", "school", "email", "address"):
            m2 = re.search(r"\\%s\s*\{([^}]*)\}" % cmd, line)
            if m2 and m2.group(1).strip():
                hard.append(f"L{i}: \\{cmd} 填了内容「{m2.group(1).strip()[:60]}」")
                flagged.add(i)

    for i, line in enumerate(lines, 1):
        if i in flagged:
            continue  # 同一行已经在上面报过了，避免重复
        scanned = scrub(line)
        for p in pats:
            m = re.search(p, scanned)
            if m:
                hard.append(f"L{i}: 命中「{m.group(0)}」  ←  {line.strip()[:140]}")
                flagged.add(i)
                break

    # 本机路径泄露用户名
    for i, line in enumerate(lines, 1):
        m = re.search(r"[A-Za-z]:\\+Users\\+[^\\\s]+", line)
        if m:
            hard.append(f"L{i}: 出现本机路径「{m.group(0)}」，可能泄露用户名")

    # 软命中：单独出现的"大学/学院/学校"
    soft_pat = re.compile(r"(?<![\u4e00-\u9fa5A-Za-z])(?:大学|学院|学校)")
    for i, line in enumerate(lines, 1):
        code, _ = split_comment(line)
        m = soft_pat.search(scrub(code))
        if m:
            soft.append(f"L{i}: 出现「{m.group(0)}」  ←  {line.strip()[:140]}")

    if hard:
        report.add(Finding("A9", "身份信息泄露", "fail",
                           f"发现 {len(hard)} 处身份信息。两个赛事都禁止在摘要页、正文、"
                           f"附录任何位置出现学校、姓名、赛区信息，请逐条确认并删除。",
                           hard))
    elif soft:
        report.add(Finding("A9", "身份信息泄露", "warn",
                           f"未发现明确的身份信息，但有 {len(soft)} 处「大学/学院/学校」字样，"
                           f"请确认是普通用词而非校名",
                           soft[:20]))
    else:
        report.add(Finding("A9", "身份信息泄露", "pass", "未检测到疑似身份信息"))


# --------------------------------------------------------------------------
# 附带：参考文献一致性
# --------------------------------------------------------------------------

def check_images(report: Report, tex_text: str, tex_path: str) -> None:
    """检查 \\includegraphics 引用的图片文件是否真的存在。

    缺图会导致 XeLaTeX 直接报 File not found 而编译失败——论文根本交不出去。
    这一条之所以值得单独检查，是因为它在源码里完全看不出来：
    \\includegraphics{figures/xxx.png} 写在纸上一切正常，只有编译时才炸。
    """
    cid, title = "A10", "图片文件存在性"

    # graphicx 的 demo 选项会让 LaTeX 用占位框替代真实图片，此时不检查文件
    if re.search(r"\\usepackage\s*\[[^\]]*\bdemo\b[^\]]*\]\s*\{graphicx\}", tex_text):
        report.add(Finding(cid, title, "skip",
                           "检测到 \\usepackage[demo]{graphicx}，LaTeX 会用占位框替代图片，"
                           "跳过文件存在性检查。正式论文请去掉 demo 选项。"))
        return

    base = os.path.dirname(os.path.abspath(tex_path))

    # \graphicspath{{../figures/}{other/}} 声明了搜索目录，必须一并考虑，
    # 否则用了 graphicspath 的论文会被整篇误报为缺图。
    search_dirs = [base]
    for gm in re.finditer(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}", tex_text):
        for dm in re.finditer(r"\{([^{}]*)\}", gm.group(1)):
            d = dm.group(1).strip()
            if not d:
                continue
            search_dirs.append(d if os.path.isabs(d) else os.path.join(base, d))

    exts = ("", ".png", ".pdf", ".jpg", ".jpeg", ".eps", ".PNG", ".PDF")
    missing, ok = [], 0
    for raw in re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", tex_text):
        p = raw.strip()
        if not p:
            continue
        cands = [p] if os.path.isabs(p) else [os.path.join(d, p) for d in search_dirs]
        if any(os.path.exists(c + e) for c in cands for e in exts):
            ok += 1
        else:
            where = "、".join(os.path.normpath(d) for d in search_dirs)
            missing.append(f"{p}  →  在 {where} 下都找不到该文件")

    if not ok and not missing:
        report.add(Finding(cid, title, "skip", "论文中没有 \\includegraphics"))
        return

    detail = f"引用图片 {ok + len(missing)} 个，找到 {ok} 个"
    if missing:
        report.add(Finding(cid, title, "fail", detail,
                           ["以下图片文件不存在，编译会直接失败："] + missing))
    else:
        report.add(Finding(cid, title, "pass", detail))


def check_bib(report: Report, tex_text: str, bib_path: str | None) -> None:
    """核对正文引用与参考文献条目是否一一对应。

    支持两种写法学：BibTeX（\\cite + refs.bib）和手写 thebibliography（\\cite + \\bibitem）。
    两种都要检查，因为"引用了但没列"和"列了但没引"都是评委看得到的疏漏。
    """
    cid, title = "B1", "参考文献一致性"
    cited: set[str] = set()
    for m in re.finditer(r"\\cite[a-z]*\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", tex_text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k:
                cited.add(k)

    # 手写 thebibliography 的情况
    bibitems = set(re.findall(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", tex_text))
    if bibitems:
        missing = sorted(cited - bibitems)
        unused = sorted(bibitems - cited)
        problems = []
        if missing:
            problems.append(f"正文引用了但 thebibliography 中没有对应 \\bibitem：{', '.join(missing)}")
        if unused:
            problems.append(f"列出了但正文从未引用：{', '.join(unused)}")
        detail = f"正文引用 {len(cited)} 条，\\bibitem 定义 {len(bibitems)} 条"
        report.add(Finding(cid, title,
                           "fail" if missing else ("warn" if unused else "pass"),
                           detail, problems))
        return

    if bib_path and os.path.exists(bib_path):
        with open(bib_path, "r", encoding="utf-8", errors="replace") as fh:
            bib = fh.read()
        defined = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib))
        missing = sorted(cited - defined)
        unused = sorted(defined - cited)
        problems = []
        if missing:
            problems.append(f"正文引用了但 refs.bib 中不存在：{', '.join(missing)}")
        if unused:
            problems.append(f"refs.bib 中列出但正文从未引用：{', '.join(unused)}")
        detail = f"正文引用 {len(cited)} 条，bib 定义 {len(defined)} 条"
        report.add(Finding(cid, title, "fail" if missing else ("warn" if unused else "pass"),
                           detail, problems))
        return

    detail = f"正文引用 {len(cited)} 条"
    if cited:
        note = "未找到 refs.bib，也无法核对条目是否存在"
    else:
        note = ("正文中没有 \\cite，请确认参考文献是否在正文中被引用"
                "（两个赛事都要求正文标注引用）")
    report.add(Finding(cid, title, "warn" if cited else "fail", detail, [note]))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="数学建模竞赛论文提交前硬校验",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tex", help="论文主文件，例如 paper/main.tex")
    ap.add_argument("--ruleset", choices=sorted(RULESETS), default="cumcm",
                    help="赛事口径（默认 cumcm）")
    ap.add_argument("--numbers", default=None, help="results/numbers.json 路径")
    ap.add_argument("--pdf", default=None, help="编译后的 PDF 路径，用于页数统计")
    ap.add_argument("--bib", default=None, help="refs.bib 路径，默认在 tex 同目录查找")
    ap.add_argument("--identity-words", default="",
                    help="额外的身份敏感词，逗号分隔（学校名、队号等）")
    ap.add_argument("--json", dest="json_out", default=None, help="把报告写成 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出问题项")
    args = ap.parse_args(argv)

    if not os.path.exists(args.tex):
        print(f"[错误] 找不到文件：{args.tex}", file=sys.stderr)
        return 2

    cfg = RULESETS[args.ruleset]
    try:
        tex_text, lines = read_tex(args.tex)
    except Exception as exc:
        print(f"[错误] 读取 tex 失败：{exc}", file=sys.stderr)
        return 2

    bib_path = args.bib
    if bib_path is None:
        cand = os.path.join(os.path.dirname(os.path.abspath(args.tex)), "refs.bib")
        bib_path = cand if os.path.exists(cand) else None

    # 数字、结构、图表只扫正文；身份信息要扫全文，因为泄露常出现在导言区的 \author
    body_start = 0
    for i, line in enumerate(lines):
        if re.search(r"\\begin\s*\{document\}", line):
            body_start = i
            break
    body_lines = lines[body_start:]
    body_text = "\n".join(body_lines)

    report = Report()
    check_numbers(report, body_text, body_lines, args.numbers)
    check_pages(report, cfg, args.pdf)
    check_toc(report, cfg, body_lines)
    check_structure(report, cfg, body_lines)
    check_core_tests(report, cfg, body_lines)
    check_floats(report, body_text, body_lines)
    check_equations(report, body_text, body_lines)
    check_tables(report, body_text)
    check_identity(report, cfg, lines,
                   [w.strip() for w in args.identity_words.split(",") if w.strip()])
    # 图片检查要用全文：\includegraphics 在正文里，但 graphicx 的 demo 选项在导言区
    check_images(report, tex_text, args.tex)
    check_bib(report, body_text, bib_path)

    # ---- 输出 ----
    counts = report.counts()
    print()
    print("=" * 74)
    print(f"  数学建模论文提交前校验 · {cfg['name']}")
    print(f"  文件：{args.tex}")
    print("=" * 74)

    icon = {"pass": "[通过]", "fail": "[失败]", "warn": "[警告]", "skip": "[跳过]"}
    for f in report.findings:
        if args.quiet and f.status == "pass":
            continue
        print(f"\n{icon[f.status]} {f.check_id}  {f.title}")
        if f.detail:
            print(f"       {f.detail}")
        for item in f.items:
            prefix = "       " if item.startswith("——") else "         · "
            print(f"{prefix}{item}")

    print()
    print("-" * 74)
    print(f"  通过 {counts['pass']}   失败 {counts['fail']}   "
          f"警告 {counts['warn']}   跳过 {counts['skip']}")
    if counts["fail"]:
        print("  存在失败项，请修复后重新校验。")
    elif counts["warn"]:
        print("  没有失败项，但有警告项需要人工确认。")
    else:
        print("  硬校验全部通过。别忘了继续做 verification.md 里 B 类与 C 类的人工核查。")
    print("-" * 74)
    print("  提示：本脚本只覆盖 A 类可机器判定的项目。")
    print("  B 类（数据真实性、图表匹配、子问题闭环、参数依据、假设合规）")
    print("  与 C 类（题意理解、逻辑因果、模型选型、常识合理性、写作同质化等）")
    print("  必须人工核查，见 references/verification.md。")
    print("=" * 74)

    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)
            print(f"\n报告已写入：{os.path.abspath(args.json_out)}")
        except Exception as exc:
            print(f"[警告] 写 JSON 失败：{exc}", file=sys.stderr)

    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
