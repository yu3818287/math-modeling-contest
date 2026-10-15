#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_tests.py —— check_paper.py 的回归测试

校验器最怕的不是漏报，而是"改了之后悄悄坏了"：正例开始误报、反例不再报错。
这个脚本把两类样例的期望结果固定下来，改完校验器跑一次就知道有没有弄坏。

用法：
    python tests/run_tests.py            # 跑全部
    python tests/run_tests.py --compile  # 额外编译正例，连页数统计一起测（需要 xelatex）

退出码：0 = 全部符合预期；1 = 有不符合预期的项
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECKER = os.path.join(ROOT, "scripts", "check_paper.py")
FIXTURES = os.path.join(HERE, "fixtures")

# 反例应该报出的检查项编号。校验器如果漏掉任何一项，说明它退化了。
BAD_EXPECT_FAIL = ["A1", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
# 反例里这些项应该通过（用来抓"到处乱报"的退化）
BAD_EXPECT_PASS = []
# 正例应该全部通过（A10 因样例用了 graphicx 的 demo 选项而跳过）
GOOD_EXPECT_FAIL: list[str] = []
GOOD_EXPECT_PASS = ["A1", "A3", "A4", "A5", "A5b", "A6", "A7", "A8", "A9", "B1"]


def run_checker(tex: str, numbers: str, ruleset: str = "cumcm",
                pdf: str | None = None, as_json: bool = True) -> tuple[int, dict]:
    json_out = None
    cmd = [sys.executable, CHECKER, tex, "--ruleset", ruleset, "--numbers", numbers]
    if pdf:
        cmd += ["--pdf", pdf]
    if as_json:
        fd, json_out = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        cmd += ["--json", json_out]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    report = {}
    if json_out and os.path.exists(json_out):
        try:
            with open(json_out, "r", encoding="utf-8") as fh:
                report = json.load(fh)
        finally:
            os.unlink(json_out)
    return proc.returncode, report


def status_map(report: dict) -> dict[str, str]:
    return {f["check_id"]: f["status"] for f in report.get("findings", [])}


def check_case(name: str, tex: str, numbers: str, ruleset: str,
               expect_fail: list[str], expect_pass: list[str],
               pdf: str | None = None, expect_exit: int | None = None) -> list[str]:
    """返回问题描述列表，空列表表示该用例通过。"""
    problems: list[str] = []
    if not os.path.exists(tex):
        return [f"{name}: 找不到样例文件 {tex}"]

    code, report = run_checker(tex, numbers, ruleset, pdf)
    st = status_map(report)

    if not st:
        return [f"{name}: 校验器没有产出报告（退出码 {code}），请先单独运行确认报错"]

    for cid in expect_fail:
        if st.get(cid) not in ("fail", "warn"):
            problems.append(
                f"{name}: {cid} 期望报出问题，实际是 {st.get(cid, '缺失')}")
    for cid in expect_pass:
        if st.get(cid) != "pass":
            problems.append(
                f"{name}: {cid} 期望通过，实际是 {st.get(cid, '缺失')}")
    if expect_exit is not None and code != expect_exit:
        problems.append(f"{name}: 期望退出码 {expect_exit}，实际 {code}")

    label = "通过" if not problems else "失败"
    print(f"  [{label}] {name}"
          + ("" if not problems else f"  ({len(problems)} 项不符)"))
    return problems


def compile_fixture(tex_path: str) -> str | None:
    """编译正例到一个临时目录，返回 PDF 路径；失败返回 None。

    整个 fixture 目录（含 figures/）一起复制，否则 \\includegraphics
    会因为找不到图片而编译失败。
    """
    if not shutil.which("xelatex"):
        print("  [跳过] 未找到 xelatex，跳过编译与页数统计测试")
        return None
    src_dir = os.path.dirname(tex_path)
    tmp = tempfile.mkdtemp(prefix="mmcontest-test-")
    for name in os.listdir(src_dir):
        s = os.path.join(src_dir, name)
        d = os.path.join(tmp, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy(s, d)
    try:
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=tmp, capture_output=True, text=True, timeout=180)
        pdf = os.path.join(tmp, "main.pdf")
        return pdf if os.path.exists(pdf) else None
    except Exception as exc:
        print(f"  [跳过] 编译失败：{exc}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="check_paper.py 回归测试")
    ap.add_argument("--compile", action="store_true",
                    help="额外编译正例并测试页数统计（需要 xelatex）")
    args = ap.parse_args()

    print()
    print("=" * 66)
    print("  check_paper.py 回归测试")
    print("=" * 66)

    all_problems: list[str] = []

    print("\n[反例] 应报出全部问题")
    all_problems += check_case(
        "bad_paper (cumcm)",
        os.path.join(FIXTURES, "bad_paper", "main.tex"),
        os.path.join(FIXTURES, "bad_paper", "numbers.json"),
        "cumcm", BAD_EXPECT_FAIL, BAD_EXPECT_PASS, expect_exit=1)

    print("\n[正例] 应全部通过")
    all_problems += check_case(
        "good_paper (cumcm)",
        os.path.join(FIXTURES, "good_paper", "main.tex"),
        os.path.join(FIXTURES, "good_paper", "numbers.json"),
        "cumcm", GOOD_EXPECT_FAIL, GOOD_EXPECT_PASS, expect_exit=0)

    print("\n[口径区分] 中文国赛论文在美赛口径下应报出结构问题")
    all_problems += check_case(
        "good_paper (mcm 口径)",
        os.path.join(FIXTURES, "good_paper", "main.tex"),
        os.path.join(FIXTURES, "good_paper", "numbers.json"),
        "mcm", ["A4"], ["A1", "A8", "A9"], expect_exit=1)

    # 国赛 2026 新规：AI 声明必须在参考文献之前。放在之后应被判失败。
    print("\n[新规] AI 声明置于参考文献之后应被判失败")
    late_dir = os.path.join(FIXTURES, "late_ai_decl")
    all_problems += check_case(
        "late_ai_decl (cumcm)",
        os.path.join(late_dir, "main.tex"),
        os.path.join(FIXTURES, "good_paper", "numbers.json"),
        "cumcm", ["A5b"], [], expect_exit=None)
    # 同一份文件按美赛口径检查时不应因位置报错（美赛要求正好相反）
    code_late, rep_late = run_checker(
        os.path.join(late_dir, "main.tex"),
        os.path.join(FIXTURES, "good_paper", "numbers.json"), "mcm")
    if status_map(rep_late).get("A5b") == "fail":
        all_problems.append(
            "late_ai_decl (mcm 口径): 美赛不要求声明在参考文献之前，"
            "不应因此判失败（两个赛事的声明位置是相反的）")
        print("  [失败] late_ai_decl (mcm 口径) 不应因位置判失败")
    else:
        print("  [通过] late_ai_decl (mcm 口径) 未因位置判失败")

    if args.compile:
        print("\n[编译] 正例编译后测页数统计")
        pdf = compile_fixture(os.path.join(FIXTURES, "good_paper", "main.tex"))
        if pdf:
            code, report = run_checker(
                os.path.join(FIXTURES, "good_paper", "main.tex"),
                os.path.join(FIXTURES, "good_paper", "numbers.json"),
                "cumcm", pdf)
            st = status_map(report)
            if st.get("A2") != "pass":
                all_problems.append(
                    f"good_paper 带 PDF 时 A2 期望通过，实际 {st.get('A2')}")
                print(f"  [失败] A2 页数统计（实际 {st.get('A2')}）")
            else:
                print("  [通过] A2 页数统计")
            os.unlink(pdf)
            shutil.rmtree(os.path.dirname(pdf), ignore_errors=True)

    print("\n" + "-" * 66)
    if all_problems:
        print(f"  {len(all_problems)} 项不符合预期：")
        for p in all_problems:
            print(f"    · {p}")
        print("-" * 66)
        return 1
    print("  全部符合预期。")
    print("-" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
