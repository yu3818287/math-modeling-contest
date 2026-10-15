# -*- coding: utf-8 -*-
"""
selftest_mmfig.py —— mmfig 绘图模块自测 / 验收脚本
==================================================

把 ``mmfig`` 里每一种图型各画一张真实的 PNG + SVG，然后**用代码去判定**
是否踩了论文绘图规范的红线：

* 有没有抛异常、有没有 matplotlib 字体告警（``missing from font``）
* 图上每一个非 ASCII 字符，所选字体文件里是否真的有对应字形
  （这是"中文不乱码"的机器判据，比肉眼看更严格）
* 图例是否在坐标轴右侧、是否压住绘图区、是否被画布裁切
  （裁切用像素判据：PNG 四边最外侧必须全是白像素）
* 有没有图内标题、有没有 2x2 拼图、有没有跑出配色的颜色
* 配色本身是否合规：3-4 种、非浅色、灰度可分

用法::

    python scripts/selftest_mmfig.py              # 画到临时目录，跑完自动删除
    python scripts/selftest_mmfig.py --keep shots # 保留图片，便于人眼复核
    python scripts/selftest_mmfig.py -v           # 打印每张图的保存路径

退出码 0 表示全部通过，1 表示有失败项（CI 可直接用）。
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import shutil
import sys
import tempfile
import warnings
from contextlib import redirect_stderr, redirect_stdout  # noqa: E402
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from matplotlib.text import Text  # noqa: E402

import mmfig  # noqa: E402

# ===========================================================================
# 自测用例：全部用中文标签，且刻意覆盖长类别名、负值、多系列等边界情况
# ===========================================================================
DAYS = np.array([0, 7, 14, 21, 28, 35])
CITY = ["北京", "上海", "广州", "深圳", "成都", "武汉"]


def case_line_trend():
    """折线趋势对比：三种调度方案的成本随天数变化。"""
    plans = {
        "方案一（贪心）": np.array([120.0, 108.5, 99.2, 93.8, 90.1, 88.6]),
        "方案二（遗传算法）": np.array([120.0, 101.3, 90.7, 84.2, 80.5, 78.9]),
        "方案三（混合整数规划）": np.array([120.0, 98.6, 86.4, 79.5, 75.8, 74.2]),
    }
    return mmfig.line_trend(DAYS, plans, xlabel="调度周期 (天)",
                            ylabel="日均总成本 (万元)", legend_title="调度方案")


def case_errorbar():
    """误差棒：四种预测模型的误差均值与 95% 置信区间。"""
    x = np.array([1, 2, 3, 4, 5])
    series = {
        "线性回归": np.array([8.42, 7.95, 7.61, 7.40, 7.22]),
        "随机森林": np.array([6.85, 6.12, 5.78, 5.51, 5.34]),
        "LSTM 网络": np.array([6.10, 5.42, 5.03, 4.81, 4.66]),
        "本文组合模型": np.array([5.32, 4.61, 4.20, 3.95, 3.78]),
    }
    err = {
        "线性回归": np.array([0.92, 0.85, 0.79, 0.74, 0.71]),
        "随机森林": np.array([0.71, 0.64, 0.58, 0.55, 0.52]),
        "LSTM 网络": np.array([0.63, 0.55, 0.49, 0.46, 0.44]),
        "本文组合模型": np.array([0.41, 0.35, 0.31, 0.28, 0.26]),
    }
    return mmfig.errorbar_plot(x, series, yerr=err, xlabel="预测步长 (周)",
                               ylabel="平均绝对百分比误差 (%)",
                               err_label="95% 置信区间", legend_title="预测模型")


def case_bar_grouped():
    """分组柱状图：两种指标在六个城市上的取值，数值直接标在柱上。"""
    series = {
        "需求满足率 (%)": np.array([92.4, 88.7, 85.1, 90.3, 83.6, 79.8]),
        "运力利用率 (%)": np.array([78.5, 82.1, 74.3, 80.6, 71.2, 68.4]),
    }
    return mmfig.bar_chart(CITY, series, xlabel="城市", ylabel="比率 (%)",
                           legend_title="评价指标", value_fmt="{:.1f}")


def case_bar_single_longname():
    """横向柱状图 + 长中文类别名 + 负增长：检验边界情况。"""
    cats = ["东部沿海枢纽仓", "中部铁路中转仓", "西部公路集散仓", "北部冷链专用仓"]
    vals = np.array([12.8, -4.6, 7.3, -1.9])
    return mmfig.bar_chart(cats, {"同比增速 (%)": vals}, xlabel="同比增速 (%)",
                           ylabel="仓库类型", horizontal=True, value_fmt="{:+.1f}",
                           legend_title="口径")


def case_scatter_fit():
    """散点 + 拟合线：物流量与区域生产总值的关系，图上给出 R²。"""
    rng = np.random.default_rng(20250913)
    x = np.linspace(120, 980, 42)
    y = 2.35 * x + 180 + rng.normal(0, 95, x.size)
    return mmfig.scatter_fit(x, y, xlabel="区域生产总值 (亿元)",
                             ylabel="年物流吞吐量 (万吨)", point_label="样本城市",
                             fit_label="线性拟合")


def case_scatter_fit_multi():
    """多组散点拟合：三类区域各自的拟合线与 R²。"""
    rng = np.random.default_rng(7)
    groups = {}
    for name, slope, base in (("东部地区", 2.6, 150), ("中部地区", 1.7, 90),
                              ("西部地区", 1.1, 40)):
        x = np.linspace(100, 700, 26)
        y = slope * x + base + rng.normal(0, 70, x.size)
        groups[name] = (x, y)
    return mmfig.scatter_fit_multi(groups, xlabel="区域生产总值 (亿元)",
                                   ylabel="年物流吞吐量 (万吨)", legend_title="区域")


def case_heatmap():
    """热力图：六个城市之间的相关系数矩阵，格子内直接写数值。"""
    rng = np.random.default_rng(11)
    base = rng.normal(size=(6, 6))
    m = np.corrcoef(base)
    np.fill_diagonal(m, 1.0)
    return mmfig.heatmap(m, CITY, CITY, xlabel="城市", ylabel="城市",
                         cbar_label="皮尔逊相关系数", value_fmt="{:.2f}")


def case_pareto():
    """帕累托前沿：成本与效益的双目标权衡。"""
    rng = np.random.default_rng(3)
    n = 120
    cost = rng.uniform(40, 160, n)
    benefit = 210 - 0.85 * cost + rng.normal(0, 9, n) - 0.004 * (cost - 100) ** 2
    return mmfig.pareto_front(cost, benefit, minimize=(True, False),
                              xlabel="建设总成本 (万元)", ylabel="年均综合效益 (万元)",
                              direction_text="成本 ↓ 越低越好 / 效益 ↑ 越高越好",
                              legend_title="解的类型")


def case_flow():
    """算法流程图：含判断框、输入输出框与迭代回边。"""
    steps = [
        {"text": "读取附件数据", "kind": "start"},
        {"text": "数据清洗与标准化", "detail": "缺失值插补 / 3σ 异常剔除",
         "note": "对应正文 3.1 节"},
        {"text": "构建多目标规划模型", "detail": "成本最小 + 效益最大",
         "note": "式 (7)—(12)"},
        {"text": "是否满足收敛条件？", "kind": "decision",
         "note": "相邻两代目标值差 < 1e-4"},
        {"text": "输出最优方案集", "kind": "end"},
    ]
    return mmfig.flow_diagram(steps, feedback="未收敛则更新种群后继续迭代",
                              legend_items=[(mmfig.COLORS[0], "起止节点"),
                                            ("#FFFFFF", "判断 / 迭代", mmfig.COLORS[1]),
                                            ("#FFFFFF", "处理步骤")],
                              box_label="图例")


def case_derivation():
    """公式推导示意图：把每一步变换写清楚。"""
    steps = [
        {"expr": r"$C(t) = a\,e^{-rt} + \dfrac{b}{r}\left(1-e^{-rt}\right)$",
         "note": "一阶线性微分方程的通解"},
        {"expr": r"$C(0) = a = C_0$", "op": "代入初值 $t=0$"},
        {"expr": r"$C(t) = C_0 e^{-rt} + \dfrac{b}{r}\left(1-e^{-rt}\right)$",
         "note": "单位成本随时间趋于稳态 $b/r$", "op": "整理同类项"},
        {"expr": r"$\lim_{t\to\infty} C(t) = \dfrac{b}{r}$",
         "op": "令 $t\to\infty$", "note": "稳态值即长期平均成本"},
    ]
    return mmfig.derivation_diagram(steps)


CASES = [
    ("line_trend", case_line_trend, True),
    ("errorbar", case_errorbar, True),
    ("bar_grouped", case_bar_grouped, True),
    ("bar_horizontal", case_bar_single_longname, True),
    ("scatter_fit", case_scatter_fit, True),
    ("scatter_fit_multi", case_scatter_fit_multi, True),
    ("heatmap", case_heatmap, True),
    ("pareto_front", case_pareto, True),
    ("flow_diagram", case_flow, False),        # 图例可选：给了就检查
    ("derivation_diagram", case_derivation, False),  # 公式推导图无系列，不需要图例
]

# ===========================================================================
# 检查工具
# ===========================================================================
FAIL = []
PASS = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append((name, detail))
    mark = "  OK  " if ok else " FAIL "
    print(f"[{mark}] {name}" + (f"   {detail}" if detail and not ok else ""))
    return ok


def rel_luminance(hex_color):
    """WCAG 相对亮度，用来判"是不是浅色"。"""
    r, g, b = mcolors.to_rgb(hex_color)
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def gray_level(hex_color):
    """黑白打印时的灰度值（0-255）。"""
    r, g, b = mcolors.to_rgb(hex_color)
    return 255.0 * (0.299 * r + 0.587 * g + 0.114 * b)


def strip_mathtext(s):
    """去掉 $...$ 片段：数学公式由 mathtext 自己的字体渲染，与中文字体无关。"""
    return re.sub(r"\$[^$]*\$", "", s)


def collect_nonascii(fig):
    chars = set()
    for t in fig.findobj(Text):
        try:
            s = t.get_text()
        except Exception:
            continue
        for ch in strip_mathtext(str(s)):
            if ord(ch) > 127 and not ch.isspace():
                chars.add(ch)
    return chars


def font_covers(font_path, chars):
    from matplotlib.ft2font import FT2Font

    face = FT2Font(font_path)
    missing = [c for c in sorted(chars) if face.get_char_index(ord(c)) == 0]
    return missing


def border_is_clean(png_path, margin=2):
    """PNG 最外侧若干列/行是否全白 —— 用来证明图例没被画布裁切。"""
    from PIL import Image

    im = Image.open(png_path).convert("L")
    a = np.asarray(im, dtype=np.uint8)
    m = int(margin)
    edges = {
        "left": a[:, :m], "right": a[:, -m:],
        "top": a[:m, :], "bottom": a[-m:, :],
    }
    bad = {k: int((v < 250).sum()) for k, v in edges.items()}
    return all(v == 0 for v in bad.values()), bad


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="mmfig 自测")
    ap.add_argument("--keep", metavar="DIR", default=None,
                    help="把测试图保留到该目录（默认写临时目录并在结束时删除）")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印保存路径")
    args = ap.parse_args()

    tmp = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="mmfig_selftest_"))
    tmp.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print(f"mmfig 自测  输出目录: {tmp}")
    print("=" * 78)

    # ---- 捕获所有警告与 matplotlib 日志 ------------------------------------
    logbuf = io.StringIO()
    handler = logging.StreamHandler(logbuf)
    handler.setLevel(logging.WARNING)
    mpl_logger = logging.getLogger("matplotlib")
    mpl_logger.addHandler(handler)
    old_level = mpl_logger.level
    mpl_logger.setLevel(logging.WARNING)

    warn_rec = []
    stdout_buf = io.StringIO()
    style_complaints = []
    exit_code = 0
    try:
        with warnings.catch_warnings(record=True) as wlist:
            warnings.simplefilter("always")
            with redirect_stdout(stdout_buf), redirect_stderr(io.StringIO()) as errbuf:
                info = mmfig.use_style(verbose=True)
                style_complaints = [
                    ln for ln in errbuf.getvalue().splitlines() if ln.strip()
                ]
                figures = {}
                for name, builder, _need_legend in CASES:
                    fig, ax = builder()
                    figures[name] = (fig, ax)
            warn_rec = list(wlist)
            saved = {}
            with redirect_stdout(stdout_buf):
                for name, (fig, _ax) in figures.items():
                    saved[name] = mmfig.save(fig, tmp / name, data={"case": name})
    finally:
        mpl_logger.removeHandler(handler)
        mpl_logger.setLevel(old_level)

    if args.verbose:
        print(stdout_buf.getvalue())

    log_text = logbuf.getvalue()
    warn_text = "\n".join(f"{w.category.__name__}: {w.message}" for w in warn_rec)

    # ---- 1. 字体 -----------------------------------------------------------
    print("\n--- 中文字体 ---")
    check("use_style() 探测到中文字体", bool(info["family"]),
          f"family={info['family']} source={info['source']}")
    check("字体文件存在", bool(info["path"]) and Path(info["path"]).is_file(),
          str(info["path"]))
    check("字体真的覆盖汉字（FreeType 字形检查）",
          bool(info["path"]) and not font_covers(info["path"], set(mmfig._PROBE_CJK)),
          "探针字符有缺失")

    # ---- 2. 样式是否真的生效（对付 matplotlib 静默丢行） -------------------
    print("\n--- 样式文件 ---")
    style_ok, style_problems = mmfig.verify_style()
    check("样式文件的每一项都真的生效（无静默丢弃）", style_ok,
          "; ".join(style_problems[:5]))
    check("样式解析器无 Bad value / Bad key 抱怨",
          not any("Bad value" in s or "Bad key" in s for s in style_complaints),
          "; ".join(style_complaints[:3]))
    check("配色循环已装载（.mplstyle 装不了，由 use_style 从 Python 装）",
          [c["color"] for c in matplotlib.rcParams["axes.prop_cycle"]]
          == list(mmfig.COLORS))

    # ---- 3. 乱码 / 缺字告警 ------------------------------------------------
    print("\n--- 告警与缺字 ---")
    font_warns = [w for w in warn_rec
                  if "missing from font" in str(w.message) or "Glyph" in str(w.message)]
    check("无 'missing from font' 类告警", not font_warns,
          f"{len(font_warns)} 条: {[str(w.message)[:70] for w in font_warns[:3]]}")
    check("matplotlib 日志中无缺字记录",
          "missing from font" not in log_text and "Glyph" not in log_text,
          log_text.strip()[:200])
    other = [w for w in warn_rec if w not in font_warns]
    check("无其它 matplotlib 警告", not other,
          "; ".join(f"{w.category.__name__}:{str(w.message)[:80]}" for w in other[:4]))

    # ---- 3. 配色规范 -------------------------------------------------------
    print("\n--- 配色 ---")
    pal = mmfig.palette()
    check("配色数量在 3-4 种之间", 3 <= len(pal) <= 4, f"{len(pal)} 种")
    lums = {c: rel_luminance(c) for c in pal}
    light = {c: round(v, 3) for c, v in lums.items() if v > 0.5}
    check("不使用浅色调（相对亮度 < 0.5）", not light, f"过亮: {light}")
    grays = sorted(gray_level(c) for c in pal)
    min_gap = min(b - a for a, b in zip(grays, grays[1:]))
    check("黑白打印可区分（灰度最小间隔 >= 12/255）", min_gap >= 12,
          f"灰度={[round(g) for g in grays]} 最小间隔={min_gap:.1f}")
    dists = []
    for i in range(len(pal)):
        for j in range(i + 1, len(pal)):
            a = np.array(mcolors.to_rgb(pal[i]))
            b = np.array(mcolors.to_rgb(pal[j]))
            dists.append(float(np.linalg.norm(a - b)) * 255)
    check("配色两两色距足够（RGB 欧氏距离 > 60）", min(dists) > 60,
          f"最小色距={min(dists):.1f}")
    try:
        mmfig.palette(5)
        check("palette(5) 被拒绝（配色上限 4）", False, "没有抛错")
    except ValueError:
        check("palette(5) 被拒绝（配色上限 4）", True)

    # ---- 4. 逐图检查 -------------------------------------------------------
    print("\n--- 逐图检查 ---")
    # 保存时已关闭 figure，这里重画一遍做结构体检
    reports = {}
    with warnings.catch_warnings(record=True) as w2:
        warnings.simplefilter("always")
        with redirect_stdout(io.StringIO()):
            for name, builder, _n in CASES:
                fig, _ax = builder()
                reports[name] = mmfig.figure_report(fig)
                plt.close(fig)

    for name, _builder, need_legend in CASES:
        rep = reports[name]
        files = saved[name]
        png = [p for p in files if p.suffix == ".png"]
        svg = [p for p in files if p.suffix == ".svg"]
        tag = f"{name}"
        check(f"{tag}: 输出 PNG + SVG", bool(png and svg), f"{files}")
        check(f"{tag}: 非 2x2 拼图（坐标轴 {rep['panel_grid'][0]}x{rep['panel_grid'][1]}）",
              not rep["is_multipanel"], str(rep["panel_grid"]))
        check(f"{tag}: 图内无标题", not rep["titles"], str(rep["titles"]))
        if need_legend or rep["legend_side"] != "none":
            check(f"{tag}: 图例在右侧", rep["legend_side"] == "right", rep["legend_side"])
            check(f"{tag}: 图例未压住绘图区", not rep["legend_overlaps_axes"])
            check(f"{tag}: 图例未被裁切", not rep["legend_clipped"])
        check(f"{tag}: 颜色全部来自规范配色", not rep["off_palette"],
              str(rep["off_palette"]))
        if png:
            clean, bad = border_is_clean(png[0])
            check(f"{tag}: PNG 四边无墨迹（未被裁切）", clean, str(bad))

    # ---- 5. 中文乱码：逐图收集非 ASCII 字符，核对字形 ----------------------
    print("\n--- 中文渲染（逐图逐字符校验字形）---")
    all_chars = set()
    with redirect_stdout(io.StringIO()):
        for name, builder, _n in CASES:
            fig, _ax = builder()
            all_chars |= collect_nonascii(fig)
            plt.close(fig)
    missing = font_covers(info["path"], all_chars) if info["path"] else sorted(all_chars)
    check(f"图中 {len(all_chars)} 个非 ASCII 字符全部有字形", not missing,
          f"缺字: {''.join(missing)}")
    print(f"         实际用到汉字示例: {''.join(sorted(all_chars)[:24])} ...")

    # ---- 6. 帕累托前沿的正确性（独立复算，防"方向搞反"） ------------------
    print("\n--- 帕累托前沿正确性 ---")
    with redirect_stdout(io.StringIO()):
        fig, ax = case_pareto()
    d = fig._mm_meta["data"]
    xs, ys = np.asarray(d["x"]), np.asarray(d["y"])
    front = set(int(i) for i in d["front_index"])

    def brute_front(minimize):
        s = np.array([-1.0 if m else 1.0 for m in minimize])
        keep = set()
        for i in range(len(xs)):
            dom = False
            for j in range(len(xs)):
                if i == j:
                    continue
                if (s[0] * xs[j] >= s[0] * xs[i] and s[1] * ys[j] >= s[1] * ys[i]
                        and (s[0] * xs[j] > s[0] * xs[i] or s[1] * ys[j] > s[1] * ys[i])):
                    dom = True
                    break
            if not dom:
                keep.add(i)
        return keep

    check("帕累托前沿与独立暴力复算一致",
          front == brute_front((True, False)),
          f"mmfig {len(front)} 个 vs 暴力 {len(brute_front((True, False)))} 个")
    check("帕累托前沿按 x 单调（折线不会自交）",
          bool(np.all(np.diff(np.asarray(d["front_x"])) >= 0)))
    check("非支配解确实不被任何其它解支配",
          all(not any(
              (xs[j] <= xs[i] and ys[j] >= ys[i]
               and (xs[j] < xs[i] or ys[j] > ys[i]))
              for j in range(len(xs)) if j != i)
              for i in front))
    plt.close(fig)

    # ---- 7. 规范拦截是否真的生效 ------------------------------------------
    print("\n--- 规范拦截 ---")
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 5.0))
    try:
        mmfig.save(fig, tmp / "_should_fail", verbose=False)
        check("save() 拦截 2x2 拼图", False, "竟然保存成功了")
    except ValueError:
        check("save() 拦截 2x2 拼图", True)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_title("不该出现的图内标题")
    with warnings.catch_warnings(record=True) as w3:
        warnings.simplefilter("always")
        mmfig.save(fig, tmp / "_title_warn", verbose=False)
    check("save() 对图内标题告警",
          any("标题" in str(w.message) for w in w3),
          "; ".join(str(w.message)[:60] for w in w3))
    plt.close("all")

    # ---- 8. 碰撞检测 -------------------------------------------------------
    print("\n--- 碰撞检测 ---")
    # 8.1 每张标准图都不应报出重叠或明显越界
    #     注意：上面的 save() 已经把 figure 关掉了，这里要用 CASES 重建，
    #     不能在已关闭的 figure 上量包围盒。
    dirty = []
    for name, builder, _need_legend in CASES:
        try:
            fig, _ax = builder()
            col = mmfig.detect_collisions(fig)
            plt.close(fig)
        except Exception as exc:
            dirty.append(f"{name} 检测异常 {type(exc).__name__}: {exc}")
            continue
        if col["verdict"] != "OK":
            extra = [f"{c['a']}×{c['b']}" for c in col["collisions"][:2]]
            extra += [f"{o['text']}越界{o['pt']}磅" for o in col["overflow"][:2]]
            dirty.append(f"{name}: {col['verdict']} {extra}")
    check(f"{len(CASES)} 张标准图全部无重叠、无越界", not dirty, "; ".join(dirty))

    # 8.2 故意把两段文字叠在一起，必须被抓出来
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "完全重合的文字", ha="center", va="center", fontsize=14)
    ax.text(0.5, 0.5, "完全重合的文字", ha="center", va="center", fontsize=14)
    col = mmfig.detect_collisions(fig)
    check("重叠的文字能被检测出来",
          bool(col["collisions"]) and col["verdict"] == "FIX BEFORE DELIVERY",
          f"verdict={col['verdict']} n={len(col['collisions'])}")
    check("重叠检测给出重叠面积占比",
          bool(col["collisions"]) and col["collisions"][0]["area_frac"] > 0.5,
          str(col["collisions"][:1]))

    # 8.3 重叠时 save() 必须拦住
    try:
        mmfig.save(fig, tmp / "_overlap_should_fail", verbose=False)
        check("save() 拦截文字重叠", False, "竟然保存成功了")
    except ValueError as exc:
        check("save() 拦截文字重叠", "重叠" in str(exc), str(exc)[:70])
    plt.close("all")

    # 8.4 check_collisions=False 时放行
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "重叠", ha="center", va="center")
    ax.text(0.5, 0.5, "重叠", ha="center", va="center")
    try:
        mmfig.save(fig, tmp / "_overlap_allowed", verbose=False,
                   check_collisions=False)
        check("check_collisions=False 可放行", True)
    except ValueError as exc:
        check("check_collisions=False 可放行", False, str(exc)[:70])
    plt.close("all")

    # ---- 汇总 --------------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败明细：")
        for name, detail in FAIL:
            print(f"  - {name}  {detail}")
        exit_code = 1
    else:
        print("全部通过：图型、中文、图例、配色、规范拦截均符合要求。")
    if args.keep:
        pngs = sorted(tmp.glob("*.png"))
        print(f"\n图片保留在 {tmp}（{len(pngs)} 张 PNG + 对应 SVG），请人工过目。")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n已清理临时目录 {tmp}")
    print("=" * 78)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
