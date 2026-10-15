# -*- coding: utf-8 -*-
"""
mmfig —— 数学建模竞赛论文 matplotlib 绘图工具模块
=================================================

这个模块把竞赛论文的绘图硬性规范固化成代码，让"照着它画"就等于"自动合规"：

============  ==========================================================
规范           本模块的落实方式
============  ==========================================================
1 图例在右侧   ``legend_right()`` 把图例放到坐标轴右侧外部，并主动为它预留
               画布空间；所有绘图函数都调用它，所以不压数据也不会被裁切
2 图内无标题   ``save()`` 检测到任何 title / suptitle 就告警（标题归 LaTeX
               的 ``\\caption``）
3 禁 2x2 拼图  ``save()`` 检测到 >=2 行且 >=2 列的坐标轴网格直接抛错，
               模块也不提供任何拼图函数
4 字号配图幅   画布尺寸就是最终印刷尺寸（``figsize()``），字号按印刷尺寸给，
               LaTeX 不再缩放图片，因此 10pt 印出来就是 10pt
5 非浅色配色   ``palette()`` 返回 4 个深色、色盲友好、黑白可辨的颜色；
               连续量用注册好的 ``mm_seq`` colormap
6 数据一致     图只应读 ``results/`` 里的数据；``save(data=...)`` 顺手把
               作图数据存成 ``.data.json`` 便于反向核对
7 示意图       ``flow_diagram()``（算法流程）、``derivation_diagram()``
               （公式推导）用 matplotlib patch 直接画，不依赖外部绘图工具
============  ==========================================================

典型用法
--------
::

    import sys; sys.path.insert(0, "scripts")
    import mmfig

    mmfig.use_style()                     # 加载样式 + 探测中文字体
    plan = {"方案A": a, "方案B": b}       # 数据从 results/ 读，不要硬编码
    fig, ax = mmfig.line_trend(x, plan, xlabel="时间 (天)", ylabel="成本 (元)")
    mmfig.save(fig, "figures/q1_trend")   # 输出 .png 与 .svg，并打印绝对路径

中文字体
--------
``use_style()`` 会真的用 FreeType 去查字形覆盖（汉字 + U+2212 减号），
而不是只信字体名字。找不到中文字体时**大声告警**，不会静默画出方框。
探测结果会写进返回值，``verbose=True`` 时同时打印到控制台。
"""

from __future__ import annotations

import json
import io
import os
import sys
import contextlib
import unicodedata
import warnings
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 后端选择：agent 通常在无交互的 shell 里跑脚本，TkAgg 之类会在 plt.show()
# 或某些后端初始化时卡住。非交互环境自动切 Agg。
# ---------------------------------------------------------------------------
import matplotlib

if "MPLBACKEND" not in os.environ and not sys.stdout.isatty():
    try:
        matplotlib.use("Agg")
    except Exception:  # pragma: no cover - 后端不可用时保持原样
        pass

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from cycler import cycler  # noqa: E402  (matplotlib 的依赖包)
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402

__all__ = [
    "use_style", "palette", "figsize", "save", "legend_right", "style_axes",
    "line_trend", "errorbar_plot", "bar_chart", "scatter_fit",
    "scatter_fit_multi", "heatmap", "pareto_front", "flow_diagram",
    "derivation_diagram", "figure_report", "detect_collisions", "verify_style",
    "register_cmaps", "font_report", "COLORS", "MARKERS", "LINESTYLES",
    "HATCHES", "TEXT_WIDTH_IN",
]

# ===========================================================================
# 常量：配色与形状循环 —— 全仓库唯一的颜色事实源
# ===========================================================================
# 选色理由（详见 scripts/README.md）：
#   #0072B2 深蓝 / #D55E00 朱红 / #009E73 墨绿 是 Okabe-Ito 色盲安全色板中
#   最稳的三个色相（蓝-橙-绿在红绿色盲下可分），全部为深色调，不浅、不粉。
#   #3D3D3D 石墨灰作为第四个色，专门留给"基准 / 对照 / 参考解"，
#   它在灰度打印里是接近黑的深灰，与另外三色的亮度差最大。
# 四个色的相对亮度约为 87 / 119 / 106 / 42，跨度足够，黑白打印可区分；
# 此外线型与标记也参与循环，双保险。
COLORS = ("#0072B2", "#D55E00", "#009E73", "#3D3D3D")
COLOR_NAMES = {
    "#0072B2": "深蓝",
    "#D55E00": "朱红",
    "#009E73": "墨绿",
    "#3D3D3D": "石墨灰",
}
MARKERS = ("o", "s", "^", "D")
LINESTYLES = ("-", "--", "-.", ":")
HATCHES = ("", "//", "..", "xx")

EDGE_COLOR = "#2B2B2B"
GRID_COLOR = "#DCDCDC"
MUTED_COLOR = "#4D4D4D"

#: A4 论文、左右各 2.5cm 页边距时的正文宽度（英寸）。画布宽度 = 该值 x width_frac。
TEXT_WIDTH_IN = 6.3
DEFAULT_ASPECT = 0.62

_HERE = Path(__file__).resolve().parent
DEFAULT_STYLE = _HERE.parent / "assets" / "mm.mplstyle"

# 中文字体候选：按优先级排序。前几个是 Windows 自带、字形规整、带粗体的黑体族。
CJK_CANDIDATES = (
    "Microsoft YaHei",   # msyh.ttc   最优先：字形现代、有粗体、含 U+2212 真减号
    "SimHei",            # simhei.ttf 国赛论文最常用的黑体
    "Noto Sans SC",      # 跨平台/Linux
    "Source Han Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei", # Linux 常见
    "Microsoft JhengHei",
    "PingFang SC",       # macOS
    "Hiragino Sans GB",
    "DengXian",
    "SimSun",
    "KaiTi",
    "FangSong",
    "STSong",
    "Arial Unicode MS",
)

# 某些环境（精简版 Windows、绿色版 Python）里字体文件存在但没被 fontconfig
# 注册，光靠名字找不到，所以再按文件名兜底扫一遍。
CJK_FONT_FILES = (
    "msyh.ttc", "msyhbd.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc",
    "simkai.ttf", "simfang.ttf", "Deng.ttf", "msjh.ttc",
    "SourceHanSansSC-Regular.otf", "SourceHanSansCN-Regular.otf",
    "NotoSansCJKsc-Regular.otf", "NotoSansSC-Regular.otf",
    "wqy-zenhei.ttc", "wqy-microhei.ttc", "PingFang.ttc", "STHeiti Light.ttc",
)

_PROBE_CJK = "汉字图表数值算法模型优化结果"
_PROBE_MINUS = "\u2212"  # − 排版用减号，SimHei/SimSun 等没有这个字形


def _say(msg: str) -> None:
    """打印，并且在控制台编码撑不住中文时退化成替换字符而不是崩溃。"""
    try:
        print(msg)
    except UnicodeEncodeError:  # pragma: no cover
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"))


def _ensure_console_cjk() -> None:
    """控制台编码画不出中文时，至少别抛 UnicodeEncodeError 把脚本打断。"""
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "中文".encode(enc)
    except Exception:  # pragma: no cover
        try:
            sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ===========================================================================
# 中文字体探测
# ===========================================================================
def _font_covers(path: str, probe: str = _PROBE_CJK) -> bool:
    """用 FreeType 真正查一遍字形覆盖，而不是相信字体名字。"""
    try:
        from matplotlib.ft2font import FT2Font

        face = FT2Font(path)
    except Exception:
        return False
    for ch in probe:
        try:
            if face.get_char_index(ord(ch)) == 0:
                return False
        except Exception:
            return False
    return True


def _font_has_minus(path: str) -> bool:
    """字体是否含 U+2212（排版减号）。没有就得退回 ASCII 连字符。"""
    try:
        from matplotlib.ft2font import FT2Font

        return FT2Font(path).get_char_index(ord(_PROBE_MINUS)) != 0
    except Exception:
        return False


def _register_extra_font_files() -> list:
    """把没被注册的中文字体文件补进 matplotlib 的字体表，返回新增的路径。"""
    dirs = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
        Path.home() / ".fonts",
        Path.home() / ".local" / "share" / "fonts",
        Path("/usr/share/fonts"),
        Path("/System/Library/Fonts"),
    ]
    added = []
    for d in dirs:
        if not d or not str(d) or not d.is_dir():
            continue
        for fname in CJK_FONT_FILES:
            fp = d / fname
            if not fp.is_file():
                continue
            try:
                fm.fontManager.addfont(str(fp))
                added.append(str(fp))
            except Exception:
                pass
    if added:
        for clear in ("cache_clear",):
            for obj in (getattr(fm, "_get_font", None), getattr(fm.findfont, clear, None)):
                try:
                    obj.cache_clear()
                except Exception:
                    pass
    return added


def _scan_all_fonts_for_cjk():
    """终极兜底：把 matplotlib 已知的全部字体按字形覆盖筛一遍。"""
    seen = {}
    for entry in fm.fontManager.ttflist:
        fname = getattr(entry, "fname", None)
        if not fname or fname in seen:
            continue
        seen[fname] = entry.name
    # 先试无衬线，再试其它；命中即返回
    for want_serif in (False, True):
        for fname, name in seen.items():
            if ("serif" in name.lower()) != want_serif:
                continue
            if _font_covers(fname):
                return name, fname
    return None, None


def detect_cjk_font(verbose: bool = False) -> dict:
    """探测系统里可用的中文字体。

    返回 dict:

    ``family``    最终选用的字体族名（None 表示没找到可用中文字体）
    ``path``      字体文件绝对路径
    ``has_minus`` 是否含 U+2212 真减号
    ``source``    ``"candidate"`` / ``"scan"`` / ``"none"``，说明是怎么找到的
    """
    _register_extra_font_files()

    # 第一轮：按候选名逐个查，并且要求真的覆盖汉字
    for name in CJK_CANDIDATES:
        try:
            path = fm.findfont(fm.FontProperties(family=name), fallback_to_default=False)
        except Exception:
            continue
        if path and Path(path).is_file() and _font_covers(path):
            return {
                "family": name,
                "path": str(Path(path).resolve()),
                "has_minus": _font_has_minus(path),
                "source": "candidate",
            }

    # 第二轮：扫描全部已注册字体
    name, path = _scan_all_fonts_for_cjk()
    if name:
        return {
            "family": name,
            "path": str(Path(path).resolve()),
            "has_minus": _font_has_minus(path),
            "source": "scan",
        }

    return {"family": None, "path": None, "has_minus": False, "source": "none"}


_FONT_INFO = {"family": None, "path": None, "has_minus": False, "source": "unset"}


def font_report() -> dict:
    """返回最近一次 ``use_style()`` 的字体探测结果（未调用过则现场探一次）。"""
    global _FONT_INFO
    if _FONT_INFO["source"] == "unset":
        _FONT_INFO = detect_cjk_font()
    return dict(_FONT_INFO)


# ===========================================================================
# colormap
# ===========================================================================
def register_cmaps() -> str:
    """注册连续量 colormap ``mm_seq``（幂等）。

    ``mm_seq`` 的取色思路：深蓝 -> 蓝 -> 墨绿 -> 朱红，
    相对亮度单调递增（约 25 -> 58 -> 82 -> 106 -> 119），因此热力图可读；
    两端都不是浅色/粉彩色，符合"不使用浅色调"的规范，也接近 viridis 的
    色盲友好特性。不用 jet/rainbow 那种亮度非单调的彩虹色。
    """
    if "mm_seq" not in plt.colormaps():
        cmap = mcolors.LinearSegmentedColormap.from_list(
            "mm_seq",
            ["#0B1D2E", "#123E63", "#0F6E9E", "#009E73", "#D55E00"],
            N=256,
        )
        try:
            matplotlib.colormaps.register(cmap, name="mm_seq")
        except Exception:  # pragma: no cover - 旧版本走 cm 注册表
            import matplotlib.cm as cm

            cm.register_cmap(name="mm_seq", cmap=cmap)
    return "mm_seq"


# ===========================================================================
# 样式
# ===========================================================================
def _load_style_file(path: Path) -> list:
    """加载样式文件，返回解析器抱怨过的行（正常情况下为空列表）。

    matplotlib 加载样式文件时会**静默丢弃**解析失败的行，只在 stderr 上打一行
    ``Bad value in file ...`` 或 ``Bad key ...``。最阴的一点是：

        grid.color: #DCDCDC

    里的 ``#`` 被当成注释起始符，值变成空串，颜色直接退回默认值 —— 肉眼看图
    完全看不出来。所以这里把 stderr 抓下来，交给 use_style() 大声告警。
    本仓库的 mm.mplstyle 已全部改用浮点三元组 ``0.86, 0.86, 0.86`` 写颜色。
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            try:
                plt.style.use(str(path))
            except UnicodeDecodeError:
                # matplotlib 用 locale 编码读 .mplstyle，中文 Windows 是 GBK，
                # 于是任何含中文注释的样式文件都会在这里炸。剥掉注释行转成
                # ASCII 临时文件再加载：rcParams 只关心键值对，注释丢了无影响。
                text = Path(path).read_text(encoding="utf-8")
                keep = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
                bad = [(i + 1, ln) for i, ln in enumerate(keep)
                       if any(ord(c) > 127 for c in ln)]
                if bad:
                    raise ValueError(
                        f"样式文件 {path} 的配置行含非 ASCII 字符，无法在当前区域"
                        "设置下加载：\n"
                        + "\n".join(f"  第 {i} 行: {ln[:80]}" for i, ln in bad[:5])
                        + "\n请把中文注释放到 scripts/README.md，样式文件保持纯 ASCII。"
                    )
                import tempfile

                with tempfile.NamedTemporaryFile(
                    "w", suffix=".mplstyle", delete=False, encoding="ascii", newline="\n"
                ) as fh:
                    fh.write("# generated by mmfig: comments stripped for locale safety\n")
                    fh.write("\n".join(keep) + "\n")
                    tmp = fh.name
                plt.style.use(tmp)
                buf.write(
                    f"note: {path} 含非 ASCII 注释，已自动剥离注释后加载；"
                    "建议另存为纯 ASCII。\n"
                )
    finally:
        complaints = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    return complaints


def use_style(scale: float = 1.0, style_path=None, verbose: bool = True) -> dict:
    """加载 ``assets/mm.mplstyle`` 并配置中文字体。**画任何图之前先调用它。**

    参数
    ----
    scale : float
        整体放大系数，同时作用于字号与线宽/标记（默认 1.0）。
        注意：控制"字看起来多大"的正确手段是 ``figsize(width_frac)`` 而不是
        把图缩小；``scale`` 只用于确实想让字整体更粗大时。
    style_path : str | Path | None
        自定义样式文件；默认使用仓库自带的 ``assets/mm.mplstyle``。
    verbose : bool
        是否把字体探测结果与告警打到控制台。

    返回
    ----
    dict
        字体探测结果，字段见 :func:`detect_cjk_font`。
    """
    global _FONT_INFO
    _ensure_console_cjk()

    path = Path(style_path) if style_path else DEFAULT_STYLE
    if not path.is_file():
        raise FileNotFoundError(f"找不到样式文件：{path}")
    complaints = _load_style_file(path)
    if complaints:
        warnings.warn(
            f"样式文件 {path} 有 {len(complaints)} 行被 matplotlib 丢弃，"
            "相关设置会退回默认值（图上看不出来，但确实没生效）：\n  "
            + "\n  ".join(complaints[:6]),
            UserWarning, stacklevel=2,
        )
        if verbose:
            _say(f"[mmfig] 样式文件被丢弃的行：\n  " + "\n  ".join(complaints[:6]))

    register_cmaps()

    # 中文字体：探测 -> 写入 rcParams -> 找不到就大声告警
    info = detect_cjk_font(verbose=verbose)
    if info["family"]:
        families = [info["family"]] + [
            f for f in rcParams["font.sans-serif"] if f != info["family"]
        ]
        rcParams["font.sans-serif"] = families
        # 字体含 U+2212 才敢用真减号，否则退回 ASCII 连字符
        rcParams["axes.unicode_minus"] = bool(info["has_minus"])
    else:
        rcParams["axes.unicode_minus"] = False
        msg = (
            "\n" + "=" * 74 + "\n"
            "【mmfig 严重警告】系统里没有找到任何可用的中文字体！\n"
            "  图里的中文会渲染成方框（□□□），这不是可以忽略的告警。\n"
            "  处理办法（任选其一）：\n"
            "    1) Windows：确认 C:\\Windows\\Fonts\\ 下有 msyh.ttc 或 simhei.ttf；\n"
            "    2) 把任意中文 .ttf/.ttc/.otf 放到 ~/.fonts/ 后重跑；\n"
            "    3) 在 mmfig.CJK_CANDIDATES 里加上你的字体族名；\n"
            "    4) 实在没有中文字体时，把图中的中文标签改成英文。\n"
            + "=" * 74
        )
        warnings.warn("mmfig: 未找到可用中文字体，中文将渲染为方框", UserWarning, stacklevel=2)
        if verbose:
            _say(msg)

    # 颜色循环：必须在 Python 里设。mpl 的 .mplstyle 解析器不支持
    # axes.prop_cycle，写进样式文件只会被静默忽略（stderr 打一行 Bad value）。
    rcParams["axes.prop_cycle"] = cycler("color", list(COLORS))

    # 线型与标记也跟着循环，保证黑白打印能区分曲线
    if scale != 1.0:
        _apply_scale(float(scale))

    _FONT_INFO = info
    if verbose:
        if info["family"]:
            _say(
                f"[mmfig] 中文字体: {info['family']}  ({info['path']})"
                f"  真减号 U+2212: {'有' if info['has_minus'] else '无，已退回 ASCII 连字符'}"
            )
        _say(
            f"[mmfig] 样式: {path}  配色: {' '.join(COLORS)}  画布: {figsize()}"
        )
    return info


_FONT_SCALE_KEYS = (
    "font.size", "axes.labelsize", "axes.titlesize", "figure.titlesize",
    "xtick.labelsize", "ytick.labelsize", "legend.fontsize",
)
_LINE_SCALE_KEYS = (
    "lines.linewidth", "lines.markersize", "axes.linewidth", "grid.linewidth",
    "xtick.major.width", "ytick.major.width", "xtick.major.size",
    "ytick.major.size", "patch.linewidth", "errorbar.capsize",
    "errorbar.linewidth",
)


def _apply_scale(scale: float) -> None:
    for key in _FONT_SCALE_KEYS + _LINE_SCALE_KEYS:
        base = rcParams.defaultParams.get(key, rcParams[key])
        try:
            rcParams[key] = float(base) * scale
        except Exception:
            pass


#: use_style() 之后这些 rcParam 必须真的等于给定值。
#: 存在的意义：matplotlib 丢弃样式文件里解析失败的行时**不报错**，只往 stderr
#: 写一行。没有这张对照表，"颜色没生效"这种问题在图上是看不出来的。
_EXPECTED_STYLE = {
    "figure.figsize": (6.3, 3.9),
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "font.size": 10,
    "axes.labelsize": 10.5,
    "xtick.labelsize": 9.5,
    "legend.fontsize": 9.5,
    "axes.grid": True,
    "axes.axisbelow": True,
    "axes.edgecolor": (0.2, 0.2, 0.2),
    "grid.color": (0.8627, 0.8627, 0.8627),
    "grid.linewidth": 0.6,
    "legend.edgecolor": (0.6902, 0.6902, 0.6902),
    "patch.edgecolor": (0.1686, 0.1686, 0.1686),
    "lines.linewidth": 1.6,
    "errorbar.capsize": 3.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "axes.unicode_minus": None,   # 跟着字体走，单独判
    "axes.prop_cycle": None,      # 单独判
}


def verify_style() -> tuple:
    """核对样式是否**真的**生效（对付 matplotlib 的静默丢行行为）。

    必须在 :func:`use_style` 之后调用。返回 ``(是否全部通过, 问题列表)``。
    典型问题：样式文件里的颜色写成了 ``#RRGGBB``——``#`` 会被当注释吃掉，
    颜色静默退回默认值，图上看不出任何异常。
    """
    problems = []
    for key, want in _EXPECTED_STYLE.items():
        if want is None:
            continue
        got = rcParams[key]
        ok = False
        if isinstance(want, float):
            ok = isinstance(got, (int, float)) and abs(float(got) - want) < 1e-6
        elif isinstance(want, tuple):
            try:
                ok = len(got) == len(want) and all(
                    abs(float(a) - float(b)) < 1e-3 for a, b in zip(got, want)
                )
            except Exception:
                ok = False
        else:
            ok = got == want
        if not ok:
            problems.append(f"{key} 期望 {want!r}，实际 {got!r}")

    colors = [c["color"] for c in rcParams["axes.prop_cycle"]]
    if [str(c).lower() for c in colors] != [c.lower() for c in COLORS]:
        problems.append(f"axes.prop_cycle 期望 {list(COLORS)}，实际 {colors}")

    info = font_report()
    want_minus = bool(info.get("has_minus"))
    if bool(rcParams["axes.unicode_minus"]) != want_minus:
        problems.append(
            f"axes.unicode_minus 期望 {want_minus}（字体 U+2212 覆盖="
            f"{info.get('has_minus')}），实际 {rcParams['axes.unicode_minus']}"
        )
    family = rcParams["font.sans-serif"][0]
    if info.get("family") and family != info["family"]:
        problems.append(f"font.sans-serif 首位期望 {info['family']}，实际 {family}")

    return (not problems), problems


# ===========================================================================
# 基础工具
# ===========================================================================
def palette(n: int = None, as_hex: bool = True) -> list:
    """返回论文配色。

    参数
    ----
    n : int | None
        需要几种颜色。``None`` 返回全部 4 种。**n 最大为 4**，超过会直接报错，
        因为"配色总数 3-4 种"是硬规范，不给悄悄扩展的机会。
    as_hex : bool
        默认返回 ``'#RRGGBB'`` 字符串；``False`` 返回 matplotlib 可直接用的
        ``(r, g, b)`` 元组。

    适用场景
    --------
    任何需要显式指定颜色的地方，例如 ``color=mmfig.palette()[1]``。
    折线/柱状图的系列颜色建议直接用默认循环，不要手工一个个指定。
    """
    n = len(COLORS) if n is None else int(n)
    if n < 1:
        raise ValueError("palette(n) 的 n 至少为 1")
    if n > len(COLORS):
        raise ValueError(
            f"配色总数最多 {len(COLORS)} 种（规范：3-4 种），请求了 {n} 种。"
            "系列更多时请合并同类项，或把次要系列并成一条'其它'。"
        )
    picked = list(COLORS[:n])
    if as_hex:
        return picked
    return [mcolors.to_rgb(c) for c in picked]


def figsize(width_frac: float = 1.0, aspect: float = DEFAULT_ASPECT, height: float = None):
    """按"最终印刷尺寸"给出画布大小。

    参数
    ----
    width_frac : float
        图在论文里占正文宽度的比例。整栏图用 1.0，半栏图用 0.5，
        三分之二栏用 0.67。
    aspect : float
        高宽比，默认 0.62（6.3in 宽 -> 3.9in 高）。
    height : float | None
        直接指定高度（英寸），给了就忽略 ``aspect``。

    为什么这样设计
    --------------
    这是"字号与图幅匹配"的落地方式：画布宽度就等于图片最终印在纸上的宽度，
    因此 rcParams 里的 10pt 字印出来真的就是 10pt。反过来，如果把一张 6.3in
    宽的图在 LaTeX 里缩到半栏，字号会等效掉到 5pt —— 那正是规范禁止的
    "图很大、字很小"。
    """
    w = float(TEXT_WIDTH_IN) * float(width_frac)
    h = float(height) if height is not None else w * float(aspect)
    return (round(w, 3), round(h, 3))


def _meta(fig, **kw):
    """把作图元信息挂在 figure 上，供自测/agent 自检读取。"""
    meta = getattr(fig, "_mm_meta", None) or {}
    meta.update(kw)
    fig._mm_meta = meta
    return fig


def _renderer(fig):
    try:
        return fig.canvas.get_renderer()
    except Exception:
        fig.canvas.draw()
        return fig.canvas.renderer


def _finish(fig, ax, kind, legend=None, colorbar=None, data=None):
    _meta(fig, kind=kind, legend=legend, colorbar=colorbar, data=data)
    return fig, ax


# ---------------------------------------------------------------------------
# 图例：统一放右侧
# ---------------------------------------------------------------------------
def legend_right(ax, handles=None, labels=None, title=None, ncol=1, gap=0.018,
                 fontsize=None, reserve=True, loc="center left", **kwargs):
    """把图例放到坐标轴**右侧外部**，并为它预留画布空间。

    参数
    ----
    ax : Axes
        目标坐标轴。``handles``/``labels`` 给定时用它们建图例，否则用轴上的
        图例元素。
    title : str | None
        图例小标题（例如 "方案"）。为 None 时不显示。
    ncol : int
        图例列数。**默认 1（纵向排列）**；置成 2 以上会让图例变宽、把坐标轴
        挤窄，非必要不要用。
    gap : float
        图例与坐标轴右边界之间的间隙，单位是"坐标轴宽度"的比例。
    fontsize : float | None
        图例字号，默认取 rcParams。
    reserve : bool
        是否自动收缩坐标轴、为图例腾出真实画布空间（默认 True）。
        这样即使有人不用 ``bbox_inches='tight'`` 直接 ``fig.savefig``，
        图例也不会被裁掉。

    返回
    ----
    matplotlib.legend.Legend
    """
    if handles is not None and labels is not None:
        leg = ax.legend(handles, labels, loc=loc, bbox_to_anchor=(1.0 + gap, 0.5),
                        ncol=ncol, title=title, fontsize=fontsize,
                        borderaxespad=0.0, **kwargs)
    else:
        leg = ax.legend(loc=loc, bbox_to_anchor=(1.0 + gap, 0.5), ncol=ncol,
                        title=title, fontsize=fontsize, borderaxespad=0.0,
                        **kwargs)
    if reserve:
        _reserve_right_space(ax, leg)
    return leg


def _reserve_right_space(ax, leg, gap_in=0.06, pad_in=0.03, min_keep=0.45):
    """收缩坐标轴，给右侧图例留出真实空间（单位：英寸）。"""
    fig = ax.figure
    fig.canvas.draw()  # 图例尺寸要画一次才准
    rend = _renderer(fig)
    try:
        leg_w = leg.get_window_extent(rend).transformed(fig.dpi_scale_trans.inverted()).width
    except Exception:
        return
    fig_w, _ = fig.get_size_inches()
    pos = ax.get_position()
    left_in = pos.x0 * fig_w
    avail = fig_w - left_in - leg_w - gap_in - pad_in
    if avail <= 0:
        warnings.warn(
            "mmfig: 图例太宽，画布塞不下。请缩短图例标签，或减少 ncol。"
            "（保存时 bbox_inches='tight' 仍能保证不被裁切）",
            UserWarning, stacklevel=3,
        )
        return
    new_w = avail / fig_w
    if new_w < min_keep * pos.width:
        warnings.warn(
            "mmfig: 图例过宽，已强行限制收缩幅度，绘图区会比较窄。"
            "建议把图例标签改短，或把图例内容写进正文表格。",
            UserWarning, stacklevel=3,
        )
        new_w = min_keep * pos.width
    ax.set_position([pos.x0, pos.y0, new_w, pos.height])


# ---------------------------------------------------------------------------
# 坐标轴收尾
# ---------------------------------------------------------------------------
def style_axes(ax, xlabel=None, ylabel=None, xlim=None, ylim=None,
               headroom=0.08, grid=None):
    """统一设置坐标轴标注/范围/留白。绘图函数内部会调用，也可单独用。

    参数
    ----
    xlabel, ylabel : str | None
        轴标注。**必须写全**，含单位，例如 ``"时间 (天)"``、``"成本 (万元)"``。
    xlim, ylim : tuple | None
        显式范围。为 None 时自动，并在数据上方留 ``headroom`` 比例的空隙，
        给数值标注让位。
    headroom : float
        顶部留白比例。
    grid : bool | None
        是否画网格，None 表示沿用样式（默认开）。

    返回
    ----
    Axes
    """
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    if grid is not None:
        ax.grid(bool(grid), axis="both")
    if xlim is not None:
        ax.set_xlim(*xlim)
    if ylim is not None:
        ax.set_ylim(*ylim)
    else:
        _headroom_y(ax, headroom)
    return ax


def _headroom_y(ax, frac=0.08):
    """在 y 方向留白，避免数值标注顶到边框。"""
    lo, hi = ax.get_ylim()
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        return
    span = hi - lo
    if lo >= 0:
        ax.set_ylim(lo, hi + span * frac)
    elif hi <= 0:
        ax.set_ylim(lo - span * frac, hi)
    else:
        ax.set_ylim(lo - span * frac * 0.6, hi + span * frac * 0.6)


def _headroom_x(ax, frac=0.05):
    lo, hi = ax.get_xlim()
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        return
    span = hi - lo
    ax.set_xlim(lo - span * frac, hi + span * frac)


def fit_margins(ax, left=True, bottom=True, pad_in=0.06):
    """把坐标轴往里收，保证轴标签与刻度文字留在画布内。

    为什么需要它：``bbox_inches='tight'`` 会把**超出画布**的内容也算进导出范围，
    于是长中文刻度标签（如"东部沿海枢纽仓"）会把最终 PNG 撑得比设定尺寸更宽。
    插进论文后被 LaTeX 按栏宽一缩放，字号就不等于设定值了——正好踩中"字号与图幅
    不匹配"。这里先量出左侧/下方真正需要多少英寸，再把坐标轴边界内收，
    保持右边界与上边界不动（右侧图例的位置因此不受影响）。

    参数
    ----
    left, bottom : bool
        是否处理左侧（y 刻度标签 + y 轴名）与下方（x 刻度标签 + x 轴名）。
    pad_in : float
        额外留出的安全余量（英寸）。

    返回
    ----
    Axes
    """
    fig = ax.figure
    fig.canvas.draw()
    rend = _renderer(fig)
    fig_w, fig_h = fig.get_size_inches()
    pos = ax.get_position()

    def _extent(t):
        try:
            if not t.get_text():
                return 0.0, 0.0
            bb = t.get_window_extent(rend)
            return bb.width / fig.dpi, bb.height / fig.dpi
        except Exception:
            return 0.0, 0.0

    if left:
        need = max([_extent(t)[0] for t in ax.get_yticklabels()] + [0.0])
        need += _extent(ax.yaxis.label)[0] + pad_in
        new_x0 = max(pos.x0, need / fig_w)
        if new_x0 > pos.x0 and pos.x1 - new_x0 > 0.25 * pos.width:
            ax.set_position([new_x0, pos.y0, pos.x1 - new_x0, pos.height])

    if bottom:
        need = max([_extent(t)[1] for t in ax.get_xticklabels()] + [0.0])
        need += _extent(ax.xaxis.label)[1] + pad_in
        new_y0 = max(pos.y0, need / fig_h)
        if new_y0 > pos.y0 and pos.y1 - new_y0 > 0.25 * pos.height:
            ax.set_position([ax.get_position().x0, new_y0,
                             ax.get_position().width, pos.y1 - new_y0])
    return ax


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------
def _axes_grid_shape(fig, tol=0.02):
    """推断可见坐标轴排成几行几列，用于识别 2x2 拼图。"""
    axes = [a for a in fig.axes if a.get_visible()]
    if len(axes) < 2:
        return (1, 1)
    pos = [a.get_position() for a in axes]

    def cluster(vals):
        vals = sorted(vals)
        groups = [[vals[0]]]
        for v in vals[1:]:
            if v - groups[-1][-1] > tol:
                groups.append([v])
            else:
                groups[-1].append(v)
        return groups

    cols = len(cluster([p.x0 for p in pos]))
    rows = len(cluster([p.y0 for p in pos]))
    return (rows, cols)


def _collect_texts(fig):
    """收集图中所有可见、非空的文字对象，按身份去重。"""
    from matplotlib.text import Text
    seen, out = set(), []
    for t in fig.findobj(match=Text):
        if id(t) in seen:
            continue
        seen.add(id(t))
        try:
            if not t.get_visible():
                continue
            s = t.get_text()
        except Exception:
            continue
        if s and str(s).strip():
            out.append(t)
    return out


def _label_of(t) -> str:
    s = str(t.get_text()).replace("\n", "⏎").strip()
    return (s[:25] + "...") if len(s) > 28 else s


def detect_collisions(fig, tol_pt: float = 1.5, warn_frac: float = 0.10,
                      fix_frac: float = 0.50, overflow_pt: float = 12.0,
                      verbose: bool = False) -> dict:
    """用渲染器实测的包围盒，检测图中文字是否互相压住、是否越出画布。

    为什么值得单独做这件事：竞赛绘图规范的第 1 条就是"图例和图片内容不要
    重叠"，但靠肉眼看很容易漏——真正出问题的是三类地方：数值标注之间、
    曲线末端标注与图例之间、刻度标签与轴标题之间。这些在缩略图上看不
    出来，印到纸上才发现。

    实现上直接取 matplotlib 渲染后的文字包围盒做两两比对，**不需要任何
    额外依赖**（不需要 PyMuPDF、不需要导出 PDF 再解析）。

    参数
    ----
    tol_pt : float
        判定为"压住"的容差（磅）。小于这个量的贴边不算重叠——正常排版里
        文字挨得近是常事，真正的问题是压上去。
    warn_frac : float
        重叠面积占较小那个包围盒的比例超过它，就报出来让人看一眼。
    fix_frac : float
        超过它判定为必须修。
    overflow_pt : float
        元素超出画布的容忍量（磅）。刻度标签探出画布边缘几个磅是常态，
        保存时 ``bbox_inches='tight'`` 会把它收进来，不算问题；但整块图例
        探出去几十磅就说明版面比声明的宽，插进论文会被整体缩小。默认 12 磅。

    返回
    ----
    dict
        ``checked``        参与检测的文字对象数
        ``collisions``     重叠列表，每项含 ``a`` / ``b`` / ``overlap_pt`` / ``area_frac``
        ``overflow``       超出画布超过 ``overflow_pt`` 的元素，含 ``text`` / ``pt`` / ``side``
        ``verdict``        ``'OK'`` / ``'REVIEW REQUIRED'`` / ``'FIX BEFORE DELIVERY'``

    用法::

        fig, ax = mmfig.bar_chart(...)
        rep = mmfig.detect_collisions(fig)
        if rep["verdict"] != "OK":
            print(rep["collisions"])

    ``save()`` 会自动调用它，因此正常流程不需要手动跑；
    单独调用适合在调布局时快速迭代。
    """
    # 必须先真正画一遍再量。get_renderer() 只拿渲染器、不触发布局计算，
    # 图例和各种标注的位置在 draw 之前是"待定"的——此时量出来的包围盒
    # 会大面积重合，把好图误报成排版事故。
    try:
        fig.canvas.draw()
    except Exception:
        pass

    rend = _renderer(fig)
    px_per_pt = fig.dpi / 72.0
    tol_px = tol_pt * px_per_pt

    boxes = []
    for t in _collect_texts(fig):
        try:
            bb = t.get_window_extent(renderer=rend)
        except Exception:
            continue
        if bb is None or bb.width <= 0 or bb.height <= 0:
            continue
        boxes.append((t, bb))

    collisions = []
    for i in range(len(boxes)):
        ti, bi = boxes[i]
        for j in range(i + 1, len(boxes)):
            tj, bj = boxes[j]
            ox = min(bi.x1, bj.x1) - max(bi.x0, bj.x0)
            oy = min(bi.y1, bj.y1) - max(bi.y0, bj.y0)
            if ox <= tol_px or oy <= tol_px:
                continue
            smaller = min(bi.width * bi.height, bj.width * bj.height)
            frac = (ox * oy) / smaller if smaller > 0 else 0.0
            if frac < warn_frac:
                continue
            collisions.append({
                "a": _label_of(ti),
                "b": _label_of(tj),
                "overlap_pt": (round(ox / px_per_pt, 2), round(oy / px_per_pt, 2)),
                "area_frac": round(frac, 3),
            })
    collisions.sort(key=lambda c: -c["area_frac"])

    fbb = fig.bbox
    overflow = []
    for t, bb in boxes:
        over_r = (bb.x1 - fbb.x1) / px_per_pt
        over_l = (fbb.x0 - bb.x0) / px_per_pt
        over_t = (bb.y1 - fbb.y1) / px_per_pt
        over_b = (fbb.y0 - bb.y0) / px_per_pt
        worst = max(over_r, over_l, over_t, over_b)
        if worst <= overflow_pt:
            continue
        side = max((("右", over_r), ("左", over_l), ("上", over_t), ("下", over_b)),
                   key=lambda kv: kv[1])[0]
        overflow.append({"text": _label_of(t), "pt": round(worst, 1), "side": side})
    overflow.sort(key=lambda o: -o["pt"])

    if any(c["area_frac"] >= fix_frac for c in collisions):
        verdict = "FIX BEFORE DELIVERY"
    elif collisions or overflow:
        verdict = "REVIEW REQUIRED"
    else:
        verdict = "OK"

    rep = {
        "checked": len(boxes),
        "collisions": collisions,
        "overflow": overflow,
        "verdict": verdict,
    }
    if verbose:
        _say(f"[mmfig] 碰撞检测：{len(boxes)} 个文字对象，"
             f"重叠 {len(collisions)} 处，明显越界 {len(overflow)} 处 → {verdict}")
    return rep


def figure_report(fig) -> dict:
    """体检一张图是否符合绘图规范，返回可编程判定的结论。

    返回 dict 字段：

    ``kind``            图型名（由绘图函数写入）
    ``panel_grid``      ``(行, 列)``，坐标轴排布
    ``is_multipanel``   是否是 >=2x2 的拼图（规范禁止）
    ``titles``          图内残留的标题（规范要求为空）
    ``legend_side``     ``'right'`` / ``'inside'`` / ``'none'``
    ``legend_clipped``  图例是否超出 tight 包围盒（正常应为 False）
    ``legend_overlaps_axes`` 图例是否压住绘图区（正常应为 False）
    ``colors``          图里实际用到的十六进制颜色
    ``off_palette``     不在 :data:`COLORS` 里的颜色（应为空）
    ``collisions``      :func:`detect_collisions` 的完整结果，含 ``verdict``
    """
    rep = {
        "kind": getattr(fig, "_mm_meta", {}).get("kind", "unknown"),
        "panel_grid": _axes_grid_shape(fig),
        "is_multipanel": False,
        "titles": [],
        "legend_side": "none",
        "legend_clipped": False,
        "legend_overlaps_axes": False,
        "colors": [],
        "off_palette": [],
    }
    rows, cols = rep["panel_grid"]
    rep["is_multipanel"] = rows >= 2 and cols >= 2

    titles = []
    for ax in fig.axes:
        if ax.get_title():
            titles.append(ax.get_title())
    try:
        if fig.get_suptitle():
            titles.append(fig.get_suptitle())
    except Exception:
        pass
    rep["titles"] = titles

    rend = _renderer(fig)
    # get_tightbbox() 的数值是"英寸"（带 dpi_scale_trans），图例的 window_extent
    # 是"像素"。必须换算到同一单位再比，否则永远判成被裁切。
    tight = fig.get_tightbbox(rend).transformed(fig.dpi_scale_trans)
    meta = getattr(fig, "_mm_meta", {})
    leg = meta.get("legend")
    cb = meta.get("colorbar")

    if leg is not None:
        lbb = leg.get_window_extent(rend)
        host = leg.axes
        rep["legend_clipped"] = bool(
            lbb.x0 < tight.x0 - 1 or lbb.x1 > tight.x1 + 1
            or lbb.y0 < tight.y0 - 1 or lbb.y1 > tight.y1 + 1
        )
        if host is not None:
            abb = host.get_window_extent(rend)
            rep["legend_side"] = "right" if lbb.x0 >= abb.x0 else "inside"
            rep["legend_overlaps_axes"] = bool(
                lbb.x0 < abb.x1 - 2 and lbb.x1 > abb.x0 + 2
                and lbb.y0 < abb.y1 - 2 and lbb.y1 > abb.y0 + 2
            )
    elif cb is not None:
        # 热力图用 colorbar 充当"图例"，同样要求在右侧
        cabb = cb.ax.get_window_extent(rend)
        main = [a for a in fig.axes if a is not cb.ax]
        if main:
            abb = main[0].get_window_extent(rend)
            rep["legend_side"] = "right" if cabb.x0 >= abb.x1 - 2 else "inside"
        rep["legend_clipped"] = bool(cabb.x1 > tight.x1 + 1)

    # 统计实际用到的颜色。跳过 colorbar 轴（它的 collection 是整条 colormap，
    # 256 个色值会把报告冲垮，而且那不是"系列配色"）。
    skip = {id(cb.ax)} if cb is not None else set()
    used = []
    for ax in fig.axes:
        if id(ax) in skip:
            continue
        for line in ax.get_lines():
            used.append(mcolors.to_hex(line.get_color()))
        for patch in ax.patches:
            try:
                fc = patch.get_facecolor()
                if fc is not None and len(fc) and fc[3] > 0:
                    used.append(mcolors.to_hex(fc))
                ec = patch.get_edgecolor()
                if ec is not None and len(ec) and ec[3] > 0:
                    used.append(mcolors.to_hex(ec))
            except Exception:
                pass
        for coll in ax.collections:
            # AxesImage 不是系列配色，跳过
            if isinstance(coll, matplotlib.image.AxesImage):
                continue
            for getter in ("get_facecolor", "get_edgecolor"):
                try:
                    arr = getattr(coll, getter)()
                except Exception:
                    continue
                if arr is None or not len(arr):
                    continue
                arr = np.atleast_2d(np.asarray(arr, dtype=float))
                for row in arr[:, :4 if arr.shape[1] >= 4 else 3]:
                    if len(row) >= 4 and row[3] <= 0:
                        continue
                    used.append(mcolors.to_hex(row[:3]))
    uniq = []
    for c in used:
        c = str(c).lower()
        if c not in uniq:
            uniq.append(c)
    rep["colors"] = uniq
    pal = {c.lower() for c in COLORS}
    # 白/黑/灰这类中性色不算"配色"，边框、白描边、网格都属于中性
    neutral = {"#ffffff", "#000000", "#1a1a1a", "#111111", "#2b2b2b", "#333333",
               "#4d4d4d", "#e8e8e8", "#dcdcdc", "#b0b0b0", "#c0c0c0", "#d0d0d0"}
    rep["off_palette"] = [c for c in uniq if c not in pal and c not in neutral]

    # 几何碰撞检测：文字/图例/标注是否互相压住。规范第 1 条的要求，
    # 靠肉眼看缩略图很容易漏，这里必须在最终布局确定后实测一次。
    try:
        rep["collisions"] = detect_collisions(fig)
    except Exception as exc:  # pragma: no cover - 渲染器不可用时不要弄崩体检
        rep["collisions"] = {
            "checked": 0, "collisions": [], "overflow": [],
            "verdict": "NOT AUDITABLE", "error": f"{type(exc).__name__}: {exc}",
        }
    return rep


def save(fig, path, formats=("png", "svg"), dpi: int = 300, data=None,
         close: bool = True, allow_multipanel: bool = False,
         check_collisions: bool = True, verbose: bool = True) -> list:
    """保存图，默认**同时输出 300dpi 的 PNG 与矢量 SVG**，并打印绝对路径。

    参数
    ----
    fig : Figure
    path : str | Path
        不带后缀的路径，例如 ``"figures/q1_trend"``。给了 ``.png/.svg/.pdf``
        后缀会自动去掉再拼。
    formats : tuple
        要输出的格式，默认 ``("png", "svg")``。PNG 供 Word/快速查看，
        SVG/PDF 供 LaTeX（矢量不失真）。
    dpi : int
        PNG 分辨率，默认 300（竞赛印刷要求）。
    data : dict | None
        作图用到的数据。给了就在图旁边写一份 ``<path>.data.json``，
        用于核对"图的数据与正文一致"（规范6）。建议把关键数值传进来。
    close : bool
        保存后是否关闭 figure 释放内存，默认 True。
    allow_multipanel : bool
        是否放行 2x2 及以上拼图。默认 False 会直接抛错（规范3）。
        确有必要（例如四张完全独立的对照图）时才置 True。
    check_collisions : bool
        是否在保存前做文字碰撞检测（规范1）。默认 True：
        文字真的互相压住时**直接抛错**，贴边或轻微接触只发警告。
        调整布局的过程中确实需要先存一张看看时，可以临时置 False。

    返回
    ----
    list[Path]
        实际写出的文件绝对路径列表。
    """
    if not allow_multipanel:
        rows, cols = _axes_grid_shape(fig)
        if rows >= 2 and cols >= 2:
            raise ValueError(
                f"检测到 {rows}x{cols} 拼图布局。竞赛规范禁止 2x2 拼图，"
                "也不要把 4 张图拼成 1 张：请拆成独立图片分别编号"
                "（图 3、图 4 ...），每张图各自带完整坐标轴与图例。"
                "确有必要时传 allow_multipanel=True 显式放行。"
            )

    meta = getattr(fig, "_mm_meta", {})
    titles = [a.get_title() for a in fig.axes if a.get_title()]
    try:
        if fig.get_suptitle():
            titles.append(fig.get_suptitle())
    except Exception:
        pass
    if titles:
        warnings.warn(
            f"图内检测到标题 {titles}。规范要求图内不加标题——标题交给 LaTeX 的 "
            "\\caption，图里再写一遍是重复信息且会被评委视作排版不规范。",
            UserWarning, stacklevel=2,
        )

    # 碰撞检测：规范第 1 条要求"图例和图片内容不要重叠"。
    # 这里只在真的压住时出声，贴边不算——所以正常图不会被打扰。
    if check_collisions:
        try:
            col = detect_collisions(fig)
        except Exception:
            col = {"verdict": "NOT AUDITABLE", "collisions": [], "out_of_bounds": []}
        if col.get("verdict") == "FIX BEFORE DELIVERY":
            worst = col["collisions"][0]
            raise ValueError(
                f"检测到文字重叠：「{worst['a']}」压住了「{worst['b']}」"
                f"（重叠 {worst['overlap_pt'][0]}×{worst['overlap_pt'][1]} 磅，"
                f"占较小者的 {worst['area_frac']:.0%}）。"
                f"共 {len(col['collisions'])} 处。请调整标注位置、缩小字号，"
                "或改用地标注错开。确需放行时传 check_collisions=False。"
            )
        if col.get("verdict") == "REVIEW REQUIRED":
            detail = []
            if col["collisions"]:
                c = col["collisions"][0]
                detail.append(f"「{c['a']}」与「{c['b']}」重叠 {c['area_frac']:.0%}")
            if col.get("overflow"):
                o = col["overflow"][0]
                detail.append(f"「{o['text']}」向{o['side']}超出画布 {o['pt']} 磅")
            warnings.warn(
                f"图中文字可能有排版问题（{'；'.join(detail)}）。"
                "请打开图片在**最终物理尺寸**下看一眼——缩略图上看不出来，"
                "印到纸上才发现就晚了。",
                UserWarning, stacklevel=2,
            )

    base = Path(path)
    if base.suffix.lower() in (".png", ".svg", ".pdf", ".eps", ".jpg"):
        base = base.with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)

    outs = []
    for ext in formats:
        fp = base.with_suffix("." + ext.lstrip("."))
        fig.savefig(
            fp, dpi=dpi, bbox_inches="tight", pad_inches=0.02,
            facecolor=fig.get_facecolor(), edgecolor="none",
        )
        outs.append(fp.resolve())

    if data is not None:
        side = base.with_suffix(".data.json")
        payload = {
            "figure": base.name,
            "kind": meta.get("kind"),
            "palette": list(COLORS),
            "style": str(DEFAULT_STYLE),
            "font": font_report().get("family"),
            "data": _jsonable(data),
        }
        side.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outs.append(side.resolve())

    if verbose:
        for fp in outs:
            try:
                size = fp.stat().st_size / 1024
                _say(f"[mmfig] 已保存 {fp}  ({size:.0f} KB)")
            except OSError:
                _say(f"[mmfig] 已保存 {fp}")
    if close:
        plt.close(fig)
    return outs


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


# ===========================================================================
# 数据归一化小工具
# ===========================================================================
def _as_series(series, x=None):
    """把多种输入统一成 ``[(label, y_array), ...]``。

    支持：``{label: y}``、``[(label, y), ...]``、``[y1, y2]``、单个 ``y``。
    """
    def _is_pair(obj):
        """(标签, 一维数组) 形式：第一个元素是标量/字符串，第二个是序列。"""
        return (
            isinstance(obj, (tuple, list)) and len(obj) == 2
            and isinstance(obj[0], (str, int, float, np.integer, np.floating))
            and not np.isscalar(obj[1])
        )

    out = []
    if isinstance(series, dict):
        for k, v in series.items():
            out.append((str(k), np.asarray(v, dtype=float).ravel()))
    elif isinstance(series, (list, tuple)):
        if len(series) == 0:
            raise ValueError("series 为空")
        if _is_pair(series[0]) or _is_pair(series):
            items = list(series)
        elif np.isscalar(series[0]):
            items = [("数据", series)]
        else:
            items = [(f"系列{i + 1}", v) for i, v in enumerate(series)]
        for item in items:
            if _is_pair(item):
                out.append((str(item[0]), np.asarray(item[1], dtype=float).ravel()))
            else:
                out.append(("数据", np.asarray(item, dtype=float).ravel()))
    else:
        out.append(("数据", np.asarray(series, dtype=float).ravel()))

    n = len(out[0][1])
    for lab, y in out:
        if len(y) != n:
            raise ValueError(f"系列 '{lab}' 长度 {len(y)} 与其它系列 {n} 不一致")
    xa = np.arange(n, dtype=float) if x is None else np.asarray(x, dtype=float).ravel()
    if len(xa) != n:
        raise ValueError(f"x 长度 {len(xa)} 与 y 长度 {n} 不一致")
    return xa, out


def _style_kw(i):
    """第 i 个系列的线型/标记/颜色，三个通道同时循环以兼顾黑白打印。"""
    return {
        "color": COLORS[i % len(COLORS)],
        "linestyle": LINESTYLES[(i // len(COLORS)) % len(LINESTYLES)] if i >= len(COLORS) else "-",
        "marker": MARKERS[i % len(MARKERS)],
    }


def _fmt_val(v, fmt="{:.4g}"):
    if v is None or not np.isfinite(v):
        return ""
    s = fmt.format(v)
    # 与坐标轴刻度保持一致：字体支持 U+2212 时，标注里的负号也用真减号
    if s.startswith("-") and rcParams["axes.unicode_minus"]:
        s = "\u2212" + s[1:]
    return s


def _annotate_last(ax, x, y, text, color, dx=-5, dy=6, fontsize=None):
    """在线末端标数值，放在点内侧，避免和图例/边框打架。"""
    if not np.isfinite(y[-1]):
        return
    ax.annotate(
        text, xy=(x[-1], y[-1]), xytext=(dx, dy), textcoords="offset points",
        ha="right", va="bottom", color=color,
        fontsize=fontsize if fontsize is not None else rcParams["font.size"] - 1.5,
        fontweight="bold", zorder=6,
    )


# ===========================================================================
# 1. 折线趋势对比图
# ===========================================================================
def line_trend(x=None, series=None, xlabel="", ylabel="", annotate_last=True,
               value_fmt="{:.4g}", width_frac=1.0, aspect=DEFAULT_ASPECT,
               xlim=None, ylim=None, logx=False, logy=False, legend_title=None,
               ax=None, fill_between=False, **legend_kw):
    """折线趋势对比图：多方案随同一自变量变化的对比。

    参数
    ----
    x : array-like | None
        自变量。None 表示用 0,1,2,... 序号。
    series : dict | list
        ``{方案名: y数组}``，或 ``[(方案名, y数组), ...]``。
        **建议 3-4 条线**；更多会挤在一起，也让配色超出规范。
    xlabel, ylabel : str
        坐标轴标注，**务必带单位**，如 ``"迭代次数"``、``"总成本 (万元)"``。
    annotate_last : bool
        是否在每条线末端标出终值（默认 True）。多方案对比时，读者最需要
        知道的往往就是"最后各是多少"。
    value_fmt : str
        数值格式，默认 ``"{:.4g}"``（4 位有效数字，够用且不啰嗦）。
    width_frac : float
        图占正文宽度比例，见 :func:`figsize`。
    logx, logy : bool
        是否用对数坐标（数量级跨度大时用）。
    legend_title : str | None
        图例标题，例如 ``"求解算法"``。
    fill_between : bool
        是否给每条线加同色浅填充（仅 1 条线时好看；多条线慎用）。

    适用场景
    --------
    随时间/迭代次数变化的趋势、不同参数方案的对比、模型预测值与真实值对照。

    返回
    ----
    (Figure, Axes)
    """
    if series is None:
        raise ValueError("line_trend 需要 series 参数，例如 {'方案A': y1, '方案B': y2}")
    xa, pairs = _as_series(series, x)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    for i, (label, y) in enumerate(pairs):
        kw = _style_kw(i)
        ax.plot(xa, y, label=label, linewidth=rcParams["lines.linewidth"],
                markersize=rcParams["lines.markersize"] * 0.85, **kw)
        if fill_between:
            ax.fill_between(xa, y, np.nanmin(y), color=kw["color"], alpha=0.12, zorder=1)
        if annotate_last:
            _annotate_last(ax, xa, y, _fmt_val(y[-1], value_fmt), kw["color"])

    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    style_axes(ax, xlabel, ylabel, xlim, ylim, headroom=0.10)
    _headroom_x(ax, 0.04)

    leg = legend_right(ax, title=legend_title, **legend_kw)
    return _finish(fig, ax, "line_trend", legend=leg,
                   data={"x": xa, **{lab: y for lab, y in pairs}})


# ===========================================================================
# 2. 误差棒 / 置信区间图
# ===========================================================================
def errorbar_plot(x=None, series=None, yerr=None, xlabel="", ylabel="",
                  err_label="95% 置信区间", value_fmt="{:.4g}", width_frac=1.0,
                  aspect=DEFAULT_ASPECT, xlim=None, ylim=None, band=False,
                  legend_title=None, ax=None, annotate_last=True, **legend_kw):
    """带误差棒或置信区间的对比图。

    参数
    ----
    x : array-like | None
        自变量。
    series : dict | list
        ``{方案名: 均值数组}``。每个系列的误差单独给（见 ``yerr``）。
    yerr : dict | array | None
        误差。可以是 ``{方案名: 误差数组}``、单个数组（所有系列共用），
        或 ``None``（不给误差棒，只画点线）。
    err_label : str
        误差含义，写进图例，例如 ``"标准差"``、``"95% 置信区间"``。
        **必须写清楚是标准差还是标准误还是置信区间**，否则读者无法判断。
    band : bool
        默认 False 画误差棒；True 画半透明置信带（适合连续曲线）。
    annotate_last : bool
        是否标注末端数值。

    适用场景
    --------
    多次重复实验的均值±波动、预测区间、蒙特卡洛结果的置信区间、
    不同算法的稳定性对比（误差棒短 = 稳定）。

    返回
    ----
    (Figure, Axes)
    """
    if series is None:
        raise ValueError("errorbar_plot 需要 series 参数")
    xa, pairs = _as_series(series, x)

    def err_of(label, i):
        if yerr is None:
            return None
        if isinstance(yerr, dict):
            key = label if label in yerr else list(yerr)[i]
            return np.asarray(yerr[key], dtype=float).ravel()
        arr = np.asarray(yerr, dtype=float)
        return arr.ravel() if arr.ndim == 1 else arr[i]

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    handles, labels = [], []
    for i, (label, y) in enumerate(pairs):
        kw = _style_kw(i)
        e = err_of(label, i)
        if band and e is not None:
            h = ax.plot(xa, y, label=label, linewidth=rcParams["lines.linewidth"], **kw)[0]
            ax.fill_between(xa, y - e, y + e, color=kw["color"], alpha=0.18, zorder=1)
        elif e is not None:
            h = ax.errorbar(
                xa, y, yerr=e, label=label, capsize=rcParams["errorbar.capsize"],
                linewidth=rcParams["lines.linewidth"], elinewidth=1.2,
                markersize=rcParams["lines.markersize"] * 0.85, **kw,
            )
        else:
            h = ax.plot(xa, y, label=label, linewidth=rcParams["lines.linewidth"], **kw)[0]
        handles.append(h)
        labels.append(label)
        if annotate_last:
            _annotate_last(ax, xa, y, _fmt_val(y[-1], value_fmt), kw["color"])

    if yerr is not None and err_label:
        # 造一个纯图例条目说明误差棒含义，不让读者去猜
        from matplotlib.lines import Line2D

        handles.append(Line2D([], [], color=MUTED_COLOR, marker="|", linestyle="none",
                              markersize=rcParams["lines.markersize"] * 1.6,
                              markeredgewidth=1.0))
        labels.append(err_label)

    style_axes(ax, xlabel, ylabel, xlim, ylim, headroom=0.14)
    _headroom_x(ax, 0.04)
    leg = legend_right(ax, handles, labels, title=legend_title, **legend_kw)
    return _finish(fig, ax, "errorbar_plot", legend=leg, data={"x": xa})


# ===========================================================================
# 3. 柱状图
# ===========================================================================
def bar_chart(categories, series=None, xlabel="", ylabel="", value_fmt="{:.4g}",
              width_frac=1.0, aspect=DEFAULT_ASPECT, ylim=None, annotate=True,
              hatch=False, label_rotation="auto", legend_title=None,
              horizontal=False, ax=None, **legend_kw):
    """柱状图：数值直接标在柱上，不需要读者去量高度。

    参数
    ----
    categories : list[str]
        横轴类别，例如 ``["周一", "周二", ...]`` 或 ``["方案A", "方案B"]``。
    series : dict | list
        ``{系列名: 数值数组}``。**单系列也给成 dict 或单元素列表**，
        这样一定会有图例（规范要求图例统一在右侧）。
    xlabel, ylabel : str
        轴标注，带单位。
    value_fmt : str
        柱顶数值格式，默认 ``"{:.4g}"``。
    annotate : bool
        是否把数值标在柱上（默认 True，这是本图型的主要求）。
    hatch : bool
        是否给不同系列加不同底纹。黑白打印且柱子较多时开启，更易区分。
    label_rotation : "auto" | int
        柱顶数值的旋转角度。auto 表示系列 >= 3 且类别 >= 4 时自动转 90 度，
        避免数字互相压住。
    horizontal : bool
        横向柱状图。类别名很长（如中文方案名）时用横向更清楚。

    适用场景
    --------
    不同类别/方案的离散指标对比、评价得分、频数统计。

    返回
    ----
    (Figure, Axes)
    """
    if series is None:
        raise ValueError("bar_chart 需要 series 参数，例如 {'总分': [88, 92, 79]}")
    cats = [str(c) for c in categories]
    if isinstance(series, dict):
        pairs = [(str(k), np.asarray(v, dtype=float).ravel()) for k, v in series.items()]
    elif isinstance(series, (list, tuple)) and series and np.isscalar(series[0]):
        pairs = [("数值", np.asarray(series, dtype=float).ravel())]
    elif isinstance(series, (list, tuple)) and series and isinstance(series[0], (tuple, list)):
        pairs = [(str(k), np.asarray(v, dtype=float).ravel()) for k, v in series]
    else:
        pairs = [("数值", np.asarray(series, dtype=float).ravel())]

    n_cat = len(cats)
    for lab, vals in pairs:
        if len(vals) != n_cat:
            raise ValueError(f"系列 '{lab}' 有 {len(vals)} 个数，类别有 {n_cat} 个，对不上")

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    n_ser = len(pairs)
    total_w = 0.78
    bw = total_w / n_ser
    idx = np.arange(n_cat, dtype=float)

    if label_rotation == "auto":
        rot = 90 if (n_ser >= 3 and n_cat >= 4) else 0
    else:
        rot = int(label_rotation)

    all_vals = np.concatenate([v for _, v in pairs])
    span = np.nanmax(all_vals) - np.nanmin(all_vals)
    span = span if span > 0 else max(abs(np.nanmax(all_vals)), 1.0)
    pad = 0.015 * span

    for i, (label, vals) in enumerate(pairs):
        off = (i - (n_ser - 1) / 2.0) * bw
        kw = {"color": COLORS[i % len(COLORS)], "edgecolor": EDGE_COLOR,
              "linewidth": rcParams["patch.linewidth"], "zorder": 3}
        if hatch:
            kw["hatch"] = HATCHES[i % len(HATCHES)] or None
        fs = rcParams["xtick.labelsize"] - (0.8 if n_ser >= 3 else 0.0)
        if horizontal:
            rects = ax.barh(idx + off, vals, bw * 0.92, label=label, **kw)
            for rect, v in zip(rects, vals):
                if not (annotate and np.isfinite(v)):
                    continue
                ha = "left" if v >= 0 else "right"
                x = v + pad if v >= 0 else v - pad
                ax.annotate(
                    _fmt_val(v, value_fmt),
                    xy=(x, rect.get_y() + rect.get_height() / 2),
                    ha=ha, va="center", fontsize=fs, color="#1A1A1A", zorder=6,
                )
        else:
            rects = ax.bar(idx + off, vals, bw * 0.92, label=label, **kw)
            if annotate:
                for rect, v in zip(rects, vals):
                    if not np.isfinite(v):
                        continue
                    va = "bottom" if v >= 0 else "top"
                    y = v + pad if v >= 0 else v - pad
                    ax.annotate(
                        _fmt_val(v, value_fmt),
                        xy=(rect.get_x() + rect.get_width() / 2, y),
                        ha="center", va=va, fontsize=fs, rotation=rot,
                        rotation_mode="anchor", color="#1A1A1A", zorder=6,
                    )

    if horizontal:
        ax.set_yticks(idx)
        ax.set_yticklabels(cats)
        ax.invert_yaxis()  # 第一个类别放最上面，符合阅读顺序
        if n_ser == 1:
            ax.margins(y=0.04)
        style_axes(ax, xlabel, ylabel)
        _headroom_x(ax, 0.14)
        ax.set_axisbelow(True)
        fit_margins(ax, left=True, bottom=True)
    else:
        ax.set_xticks(idx)
        ax.set_xticklabels(cats)
        if n_ser == 1:
            ax.margins(x=0.04)
        style_axes(ax, xlabel, ylabel, None, ylim, headroom=0.14)
        ax.set_axisbelow(True)
        fit_margins(ax, left=True, bottom=True)

    leg = legend_right(ax, title=legend_title, **legend_kw)
    return _finish(fig, ax, "bar_chart", legend=leg,
                   data={"categories": cats, **{k: v for k, v in pairs}})


# ===========================================================================
# 4. 散点 + 拟合线
# ===========================================================================
def _fit_and_r2(x, y, degree=1):
    coeffs = np.polyfit(x, y, degree)
    yhat = np.polyval(coeffs, x)
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return coeffs, r2


def _poly_eq(coeffs, var="x"):
    """把多项式系数写成 $y = ...$ 的 mathtext 形式。"""
    terms = []
    n = len(coeffs) - 1
    for i, c in enumerate(coeffs):
        p = n - i
        if abs(c) < 1e-12:
            continue
        sign = "-" if c < 0 else ("+" if terms else "")
        a = abs(c)
        coef_s = f"{a:.4g}"
        if p == 0:
            body = coef_s
        elif p == 1:
            body = f"{coef_s}{var}"
        else:
            body = f"{coef_s}{var}^{{{p}}}"
        terms.append(f"{sign} {body}" if sign else body)
    return "$y = " + (" ".join(terms) if terms else "0") + "$"


def scatter_fit(x, y, xlabel="", ylabel="", degree=1, point_label="观测数据",
                fit_label="拟合曲线", width_frac=1.0, aspect=DEFAULT_ASPECT,
                xlim=None, ylim=None, show_eq=True, legend_title=None,
                ax=None, **legend_kw):
    """散点 + 拟合线，并在图上显示 R²。

    参数
    ----
    x, y : array-like
        成对样本数据，长度必须一致。
    degree : int
        拟合多项式阶数，默认 1（线性）。2 表示抛物线拟合。
    point_label, fit_label : str
        散点与拟合线的图例名。
    show_eq : bool
        是否在图上以标注框给出拟合方程与 R²。R² 始终进图例，
        方程进标注框（放图例里太长）。
    width_frac, aspect, xlim, ylim, legend_title
        同其它图型。

    适用场景
    --------
    相关性分析、回归建模、模型预测值与真实值的吻合度展示。
    **R² 是回归类题目的必答数字，必须出现在图上或正文中**。

    返回
    ----
    (Figure, Axes)
    """
    xa = np.asarray(x, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if len(xa) != len(ya):
        raise ValueError(f"x 长度 {len(xa)} 与 y 长度 {len(ya)} 不一致")

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    kw = _style_kw(0)
    ax.scatter(xa, ya, s=rcParams["lines.markersize"] ** 2 * 1.15,
               color=kw["color"], marker="o", alpha=0.85,
               edgecolors="white", linewidths=0.7, label=point_label, zorder=4)

    coeffs, r2 = _fit_and_r2(xa, ya, degree)
    xs = np.linspace(xa.min(), xa.max(), 200)
    fk = _style_kw(1)
    ax.plot(xs, np.polyval(coeffs, xs), label=f"{fit_label} ($R^2$={r2:.4f})",
            color=fk["color"], linestyle="--", linewidth=rcParams["lines.linewidth"] + 0.2,
            zorder=5)

    style_axes(ax, xlabel, ylabel, xlim, ylim, headroom=0.12)
    _headroom_x(ax, 0.05)

    if show_eq:
        slope = coeffs[-2] if degree >= 1 else 0.0
        loc = "lower right" if slope >= 0 else "upper left"
        txt = _poly_eq(coeffs) + f"\n$R^2$ = {r2:.4f}    $n$ = {len(xa)}"
        ax.text(
            0.03 if loc == "upper left" else 0.97,
            0.95 if loc == "upper left" else 0.06,
            txt, transform=ax.transAxes, fontsize=rcParams["font.size"] - 0.5,
            ha="left" if loc == "upper left" else "right",
            va="top" if loc == "upper left" else "bottom",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                      edgecolor="#B0B0B0", linewidth=0.7, alpha=0.95),
            zorder=7,
        )

    leg = legend_right(ax, title=legend_title, **legend_kw)
    return _finish(fig, ax, "scatter_fit", legend=leg,
                   data={"x": xa, "y": ya, "degree": degree,
                         "coeffs": coeffs, "r2": r2})


def scatter_fit_multi(groups, xlabel="", ylabel="", degree=1, width_frac=1.0,
                      aspect=DEFAULT_ASPECT, xlim=None, ylim=None,
                      legend_title=None, ax=None, **legend_kw):
    """多组散点各自拟合并对比：R² 直接写进图例。

    参数
    ----
    groups : list | dict
        ``[(组名, x, y), ...]`` 或 ``{组名: (x, y)}``。每组一条拟合虚线与
        对应的散点颜色，图例里带上该组的 $R^2$。

    适用场景
    --------
    不同类别/地区/实验条件下分别回归，比较哪一组的相关性更强。

    返回
    ----
    (Figure, Axes)
    """
    if isinstance(groups, dict):
        items = [(str(k), np.asarray(v[0], float).ravel(), np.asarray(v[1], float).ravel())
                 for k, v in groups.items()]
    else:
        items = [(str(g[0]), np.asarray(g[1], float).ravel(), np.asarray(g[2], float).ravel())
                 for g in groups]

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    handles, labels, stats = [], [], {}
    for i, (name, xa, ya) in enumerate(items):
        if len(xa) != len(ya):
            raise ValueError(f"组 '{name}' 的 x/y 长度不一致")
        kw = _style_kw(i)
        ax.scatter(xa, ya, s=rcParams["lines.markersize"] ** 2 * 1.0,
                   color=kw["color"], marker=kw["marker"], alpha=0.8,
                   edgecolors="white", linewidths=0.6, zorder=3 + i)
        coeffs, r2 = _fit_and_r2(xa, ya, degree)
        xs = np.linspace(xa.min(), xa.max(), 100)
        h, = ax.plot(xs, np.polyval(coeffs, xs), color=kw["color"], linestyle="--",
                     linewidth=rcParams["lines.linewidth"], zorder=6)
        handles.append(h)
        labels.append(f"{name}  ($R^2$={r2:.4f})")
        stats[name] = {"coeffs": coeffs.tolist(), "r2": r2, "n": int(len(xa))}

    style_axes(ax, xlabel, ylabel, xlim, ylim, headroom=0.10)
    _headroom_x(ax, 0.05)
    leg = legend_right(ax, handles, labels, title=legend_title, **legend_kw)
    return _finish(fig, ax, "scatter_fit_multi", legend=leg, data=stats)


# ===========================================================================
# 5. 热力图
# ===========================================================================
def heatmap(matrix, row_labels=None, col_labels=None, xlabel="", ylabel="",
            cbar_label="", value_fmt="{:.3g}", cmap=None, annot=True,
            width_frac=1.0, aspect=0.72, vmin=None, vmax=None, ax=None):
    """热力图（连续量矩阵），**右侧 colorbar 充当图例**，格子内直接标数值。

    参数
    ----
    matrix : 2-D array-like
        形状 ``(行数, 列数)`` 的数值矩阵。
    row_labels, col_labels : list[str] | None
        行列标签。行标签建议简短（中文 2-6 字），太长会占掉标尺空间。
    cbar_label : str
        色标含义，**必须写**，例如 ``"需求满足率"``、``"相关系数"``。
    value_fmt : str
        格内数值格式。``None`` 或空串表示只画色块不标数字。
    cmap : str | Colormap | None
        默认 ``mm_seq``（深蓝->橙，亮度单调递增、无浅色端）。
        **不要用 jet / rainbow**：亮度非单调，黑白打印和色盲读者都读不出来。
    annot : bool
        是否在格内写数值（默认 True）。数值多到看不清时置 False，
        改用 colorbar 读数。

    适用场景
    --------
    相关系数矩阵、不同方案在不同指标上的得分、时空分布（时段 x 区域）、
    参数敏感性分析。

    返回
    ----
    (Figure, Axes)
    """
    M = np.asarray(matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("heatmap 需要二维矩阵")
    nr, nc = M.shape
    rl = [str(v) for v in (row_labels if row_labels is not None else range(nr))]
    cl = [str(v) for v in (col_labels if col_labels is not None else range(nc))]
    if len(rl) != nr or len(cl) != nc:
        raise ValueError("行列标签数量与矩阵形状不一致")

    if cmap is None:
        cmap = register_cmaps()
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    vmin = float(np.nanmin(M)) if vmin is None else vmin
    vmax = float(np.nanmax(M)) if vmax is None else vmax
    im = ax.imshow(M, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    ax.set_xticks(np.arange(nc))
    ax.set_xticklabels(cl)
    ax.set_yticks(np.arange(nr))
    ax.set_yticklabels(rl)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(False)  # 网格会盖在色块上，热力图不要网格
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(EDGE_COLOR)
    # 用白色细线分隔格子，边界更清楚
    ax.set_xticks(np.arange(-0.5, nc, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, nr, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.9)
    ax.tick_params(which="minor", length=0)

    if annot and value_fmt:
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        cm = plt.get_cmap(cmap)
        for i in range(nr):
            for j in range(nc):
                v = M[i, j]
                if not np.isfinite(v):
                    continue
                rgba = cm(norm(v))
                lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                ax.text(j, i, _fmt_val(v, value_fmt), ha="center", va="center",
                        color="white" if lum < 0.55 else "#111111",
                        fontsize=rcParams["xtick.labelsize"] - 0.5)

    fit_margins(ax, left=True, bottom=True)
    cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
    if cbar_label:
        cb.set_label(cbar_label)
    cb.outline.set_linewidth(0.6)
    cb.outline.set_edgecolor("#B0B0B0")
    return _finish(fig, ax, "heatmap", colorbar=cb,
                   data={"matrix": M, "row_labels": rl, "col_labels": cl})


# ===========================================================================
# 6. 帕累托前沿 / 多目标权衡
# ===========================================================================
def pareto_front(x, y, minimize=(True, True), labels=None, point_label="可行解",
                 front_label="Pareto 前沿", annotate_knee=True, annotate_points=False,
                 xlabel="", ylabel="", width_frac=1.0, aspect=DEFAULT_ASPECT,
                 xlim=None, ylim=None, legend_title=None, ax=None,
                 direction_text=None, **legend_kw):
    """帕累托前沿 / 多目标权衡图：把"非支配解"从一堆可行解里挑出来画。

    参数
    ----
    x, y : array-like
        两个目标函数值，长度一致。
    minimize : (bool, bool)
        两个目标是否都是"越小越好"。例如成本最小 + 效益最大 就是 ``(True, False)``。
        **方向搞反，帕累托前沿就会挑错**，务必按题意确认。
    labels : list[str] | None
        每个解的名字，用于标注前沿点（例如 ``"方案1"``）。
    annotate_knee : bool
        是否标注"膝点"（前沿上拐弯最厉害、通常最值得选的那个折中解）。
    annotate_points : bool
        是否给前沿上每个点都标名字。点少（<= 8）时可以开。
    direction_text : str | None
        在图上标出改进方向的文字，例如 ``"成本 ↓ / 效益 ↑"``。
        多目标图里"哪个方向更好"必须让人一眼看出来。

    适用场景
    --------
    成本-效益权衡、精度-耗时权衡、多目标优化结果展示、
    "给出若干推荐方案并说明取舍"这类问法。

    返回
    ----
    (Figure, Axes)
    """
    xa = np.asarray(x, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if len(xa) != len(ya):
        raise ValueError("x 与 y 长度不一致")
    n = len(xa)
    sign = np.array([-1.0 if m else 1.0 for m in minimize])  # 统一成"越大越好"

    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        dom = (sign[0] * xa >= sign[0] * xa[i]) & (sign[1] * ya >= sign[1] * ya[i])
        strict = (sign[0] * xa > sign[0] * xa[i]) | (sign[1] * ya > sign[1] * ya[i])
        dominated = dom & strict
        dominated[i] = False
        if dominated.any():
            keep[i] = False
    front = np.where(keep)[0]
    order = np.argsort(xa[front])
    front = front[order]

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize(width_frac, aspect))
    else:
        fig = ax.figure

    inner = np.setdiff1d(np.arange(n), front)
    sc = ax.scatter(xa[inner], ya[inner], s=rcParams["lines.markersize"] ** 2 * 1.1,
                    color=COLORS[3], marker="o", alpha=0.55, edgecolors="white",
                    linewidths=0.6, label=point_label, zorder=3)
    ln, = ax.plot(xa[front], ya[front], color=COLORS[1], linestyle="--",
                  linewidth=rcParams["lines.linewidth"], marker="D",
                  markersize=rcParams["lines.markersize"] * 0.95,
                  markerfacecolor=COLORS[1], markeredgecolor="white",
                  markeredgewidth=0.7, label=front_label, zorder=5)

    if annotate_points and labels is not None:
        for i in front:
            ax.annotate(str(labels[i]), xy=(xa[i], ya[i]), xytext=(4, 5),
                        textcoords="offset points", fontsize=rcParams["font.size"] - 1.5,
                        color="#1A1A1A", zorder=7)

    style_axes(ax, xlabel, ylabel, xlim, ylim, headroom=0.12)
    _headroom_x(ax, 0.06)

    # 角落在哪放注释，由数据密度决定：把说明框放在最空的角，箭头指向膝点。
    # 固定偏移量在小图上会把说明框顶出坐标轴，压住刻度标签。
    corners = _emptiest_corners(ax, xa, ya)

    if annotate_knee and not annotate_points and len(front) >= 3:
        k = _knee_index(xa[front], ya[front])
        cname = corners[0]
        cx, cy = _CORNER_ANCHOR[cname]
        ax.annotate(
            "折中最优解\n" + f"({_fmt_val(xa[front][k])}, {_fmt_val(ya[front][k])})",
            xy=(xa[front][k], ya[front][k]), xycoords="data",
            xytext=(cx, cy + (0.05 if "lower" in cname else -0.05)),
            textcoords="axes fraction",
            ha="left" if "left" in cname else "right",
            va="bottom" if "lower" in cname else "top",
            fontsize=rcParams["font.size"] - 1.0, color="#1A1A1A", zorder=8,
            arrowprops=dict(arrowstyle="->", color=MUTED_COLOR, linewidth=1.0,
                            shrinkA=2, shrinkB=3),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#B0B0B0", linewidth=0.7),
        )

    if direction_text:
        cname = corners[1] if len(corners) > 1 else "upper right"
        cx, cy = _CORNER_ANCHOR[cname]
        ax.text(cx, cy, direction_text, transform=ax.transAxes,
                ha="left" if "left" in cname else "right",
                va="bottom" if "lower" in cname else "top",
                fontsize=rcParams["font.size"] - 1.0, color=MUTED_COLOR,
                bbox=dict(boxstyle="round,pad=0.28", facecolor="white",
                          edgecolor="#D0D0D0", linewidth=0.6), zorder=7)

    leg = legend_right(ax, title=legend_title, **legend_kw)
    return _finish(fig, ax, "pareto_front", legend=leg,
                   data={"x": xa, "y": ya, "front_index": front,
                         "front_x": xa[front], "front_y": ya[front]})


_CORNER_ANCHOR = {
    "lower left": (0.03, 0.04),
    "lower right": (0.97, 0.04),
    "upper left": (0.03, 0.96),
    "upper right": (0.97, 0.96),
}


def _emptiest_corners(ax, xa, ya, box=0.32):
    """按四个角附近的数据点数量排序，返回从最空到最挤的角名列表。

    在坐标轴内放说明框时，"最空的角"是唯一稳的判断依据：帕累托前沿的形状
    随题意变化，任何写死的偏移量都会在某些数据上压住别的元素。
    """
    try:
        pix = ax.transData.transform(np.column_stack([np.asarray(xa, float),
                                                      np.asarray(ya, float)]))
        pts = ax.transAxes.inverted().transform(pix)
    except Exception:
        return ["lower right", "upper left", "lower left", "upper right"]
    counts = {}
    for name, (cx, cy) in _CORNER_ANCHOR.items():
        x0, x1 = (0.0, box) if cx < 0.5 else (1.0 - box, 1.0)
        y0, y1 = (0.0, box) if cy < 0.5 else (1.0 - box, 1.0)
        m = ((pts[:, 0] >= x0) & (pts[:, 0] <= x1)
             & (pts[:, 1] >= y0) & (pts[:, 1] <= y1))
        counts[name] = int(m.sum())
    return sorted(counts, key=lambda k: counts[k])


def _knee_index(fx, fy):
    """膝点：到首尾连线距离最大的前沿点（归一化后）。"""
    if len(fx) < 3:
        return 0
    x0, x1 = fx[0], fx[-1]
    y0, y1 = fy[0], fy[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = np.hypot(dx, dy)
    if norm == 0:
        return 0
    dist = np.abs(dy * (fx - x0) - dx * (fy - y0)) / norm
    return int(np.argmax(dist))


# ===========================================================================
# 7. 示意图：算法流程
# ===========================================================================
def _wrap_cjk(text, units):
    """按显示宽度折行：中日韩字符算 2 个单位，其它算 1 个。"""
    lines, cur, w = [], [], 0
    for ch in str(text):
        if ch == "\n":
            lines.append("".join(cur))
            cur, w = [], 0
            continue
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > units and cur:
            lines.append("".join(cur))
            cur, w = [], 0
        cur.append(ch)
        w += cw
    if cur:
        lines.append("".join(cur))
    return "\n".join(lines)


def flow_diagram(steps, width_frac=0.78, row_in=0.68, feedback=None,
                 xlabel=None, ylabel=None, legend_items=None, fontsize=None,
                 detail_fontsize=None, box_label=None, ax=None):
    """算法流程图（用 matplotlib patch 直接画，不依赖 Visio/PPT 截图）。

    参数
    ----
    steps : list
        流程步骤。每个元素可以是：

        - ``str``：普通处理框的文字；
        - ``dict``：``{"text": 主文字, "detail": 补充说明, "kind": 种类,
          "note": 画在右侧的旁注}``。

        ``kind`` 可选：``"start"``（起止，实心深色）、``"process"``（处理，
        默认）、``"decision"``（判断，六边形）、``"io"``（输入输出，平行四边形）、
        ``"end"``（结束，实心深色）。
    width_frac : float
        图占正文宽度比例。流程图一般用 0.7-0.85，太宽显得空。
    row_in : float
        每一步占的物理高度（英寸），影响疏密。
    feedback : str | None
        迭代回边文字，例如 ``"未收敛则继续迭代"``。给了就从最后一个框画一条
        弧线回到第一个框——**迭代类算法必须画出这条回边**，否则流程是错的。
    legend_items : list[tuple] | None
        右侧图例 ``[(颜色, 说明), ...]``，用来解释框中颜色的含义。
    box_label : str | None
        图例标题。

    适用场景
    --------
    算法主流程、模型求解步骤、数据处理管线、评价指标体系构建流程。
    这类内容用文字写又臭又长，用一张流程图最省篇幅。

    返回
    ----
    (Figure, Axes)
    """
    steps = list(steps)
    if not steps:
        raise ValueError("flow_diagram 需要至少一个步骤")
    n = len(steps)
    fig_h = 0.5 + row_in * n
    fig_w = TEXT_WIDTH_IN * width_frac
    if ax is None:
        fig, ax = plt.subplots(figsize=(round(fig_w, 3), round(fig_h, 3)))
    else:
        fig = ax.figure
    ax.set_axis_off()
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, n)
    ax.set_aspect("auto")

    if fontsize is None:
        fontsize = rcParams["font.size"]
    if detail_fontsize is None:
        detail_fontsize = fontsize - 1.5

    bx0, bx1 = 1.35, 7.4           # 主框左右边界（右侧留给旁注与图例）
    box_h = 0.62                   # 框高（数据单位）；1 单位约 0.68in
    loop_x = 0.34                  # 迭代回边的横向位置
    note_gap = 0.32                # 旁注与框右边界之间的空隙（数据单位）
    # 旁注列可用宽度（英寸）-> 折行宽度（显示宽度单位，汉字算 2）
    note_in = max(0.6, (10.0 - (bx1 + note_gap)) / 10.0 * fig_w)
    note_units = max(8, int(note_in / (detail_fontsize / 72.0)) * 2 - 2)
    inner_in = (bx1 - bx0) / 10.0 * fig_w
    wrap_units = max(6, int(inner_in / (fontsize / 72.0)) * 2 - 2)

    def geom(i):
        cy = n - i - 0.5
        return cy - box_h / 2.0, cy + box_h / 2.0

    for i, raw in enumerate(steps):
        if isinstance(raw, str):
            spec = {"text": raw}
        else:
            spec = dict(raw)
        kind = spec.get("kind", "process")
        y0, y1 = geom(i)
        cy = (y0 + y1) / 2.0
        text = _wrap_cjk(spec.get("text", ""), wrap_units)
        detail = spec.get("detail")

        if kind in ("start", "end"):
            face, edge, tcol = COLORS[0], COLORS[0], "white"
            style = "round,pad=0.02,rounding_size=0.18"
        elif kind == "decision":
            face, edge, tcol = "#FFFFFF", COLORS[1], "#1A1A1A"
            style = "round,pad=0.02,rounding_size=0.08"
        elif kind == "io":
            face, edge, tcol = "#FFFFFF", COLORS[2], "#1A1A1A"
            style = "round,pad=0.02,rounding_size=0.06"
        else:
            face, edge, tcol = "#FFFFFF", EDGE_COLOR, "#1A1A1A"
            style = "round,pad=0.02,rounding_size=0.10"

        if kind == "decision":
            skew = 0.45
            pts = [(bx0 + skew, y0), (bx1, y0), (bx1 - skew, y1), (bx0, y1)]
            patch = Polygon(pts, closed=True, facecolor=face, edgecolor=edge,
                            linewidth=1.1, zorder=3)
            ax.add_patch(patch)
        elif kind == "io":
            skew = 0.5
            pts = [(bx0 + skew, y0), (bx1, y0), (bx1 - skew, y1), (bx0, y1)]
            patch = Polygon(pts, closed=True, facecolor=face, edgecolor=edge,
                            linewidth=1.1, zorder=3)
            ax.add_patch(patch)
        else:
            patch = FancyBboxPatch(
                (bx0, y0), bx1 - bx0, y1 - y0, boxstyle=style,
                facecolor=face, edgecolor=edge, linewidth=1.1, zorder=3,
                mutation_aspect=1.0,
            )
            ax.add_patch(patch)

        if detail:
            ax.text((bx0 + bx1) / 2.0, cy + 0.10, text, ha="center", va="center",
                    fontsize=fontsize, color=tcol, zorder=4, linespacing=1.25)
            ax.text((bx0 + bx1) / 2.0, cy - 0.16, _wrap_cjk(detail, wrap_units),
                    ha="center", va="center", fontsize=detail_fontsize,
                    color="#4D4D4D" if tcol != "white" else "#E8E8E8",
                    zorder=4, linespacing=1.2)
        else:
            ax.text((bx0 + bx1) / 2.0, cy, text, ha="center", va="center",
                    fontsize=fontsize, color=tcol, zorder=4, linespacing=1.3)

        note = spec.get("note")
        if note:
            # 旁注锚在框右边界之外（数据坐标），加一段空隙，避免压在框线上
            ax.text(bx1 + note_gap, cy, _wrap_cjk(note, note_units),
                    ha="left", va="center", fontsize=detail_fontsize,
                    color=MUTED_COLOR, zorder=5, linespacing=1.25)

    # 竖向箭头
    xc = (bx0 + bx1) / 2.0
    for i in range(n - 1):
        _, y_bot = geom(i)
        y_top_next, _ = geom(i + 1)
        ax.add_patch(FancyArrowPatch(
            (xc, y_bot), (xc, y_top_next), arrowstyle="-|>",
            mutation_scale=11, linewidth=1.1, color=EDGE_COLOR,
            shrinkA=0, shrinkB=0, zorder=2,
        ))

    # 迭代回边：从最后一个框沿左侧画一条弧线回到第一个框。
    # 弧线向左鼓出，标签放在弧线再左边，两者不打架。
    if feedback:
        y_first = (geom(0)[0] + geom(0)[1]) / 2.0
        y_last = (geom(n - 1)[0] + geom(n - 1)[1]) / 2.0
        ax.add_patch(FancyArrowPatch(
            (bx0 - 0.06, y_last), (bx0 - 0.06, y_first),
            connectionstyle="arc3,rad=-0.30", arrowstyle="-|>",
            mutation_scale=11, linewidth=1.15, color=COLORS[1],
            shrinkA=0, shrinkB=0, zorder=2,
        ))
        ax.text(loop_x, (y_first + y_last) / 2.0, _wrap_cjk(feedback, 16),
                ha="center", va="center", rotation=90,
                fontsize=detail_fontsize, color=COLORS[1], zorder=3)

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    leg = None
    if legend_items:
        from matplotlib.patches import Patch

        handles, labels = [], []
        for item in legend_items:
            if len(item) == 3:
                face, text, edge = item
            else:
                face, text = item
                edge = EDGE_COLOR
            handles.append(Patch(facecolor=face, edgecolor=edge, linewidth=0.9,
                                 label=text))
            labels.append(text)
        # reserve=True：让 legend_right 收缩坐标轴给图例腾地方。
        # 用 reserve=False 时图例挂在轴外却没预留宽度，实测会挤出画布约 45 磅，
        # 保存出来的图比声明的宽，插进论文会被整体缩小。
        leg = legend_right(ax, handles, labels, title=box_label, reserve=True)
    return _finish(fig, ax, "flow_diagram", legend=leg)


# ===========================================================================
# 8. 示意图：公式推导
# ===========================================================================
def derivation_diagram(steps, width_frac=0.92, row_in=0.62, fontsize=None,
                       note_fontsize=None, eq_left=0.05, note_x=0.68, ax=None,
                       min_fontsize=6.5):
    """公式推导示意图：把"怎么从上一步推下一步"画出来。

    参数
    ----
    steps : list
        每一步。元素可以是：

        - ``str``：公式。含 ``$`` 的按 mathtext 渲染（如 ``r"$T(n)=2T(n/2)+O(n)$"``），
          不含 ``$`` 的按普通文字渲染（可以直接写中文）；
        - ``dict``：``{"expr": 公式, "note": 右侧小字说明, "op": 该步用到的
          变换（写在箭头边，如 "两边同乘 $e^{-rt}$"）}``。
    row_in : float
        每一步占的物理高度（英寸）。
    eq_left : float
        公式列的左边界（0-1 比例）。公式在 ``[eq_left, note_x]`` 这一列内居中，
        保证再宽的公式也不会爬到旁注栏里。
    note_x : float
        旁注列的左边界。
    min_fontsize : float
        公式自动缩小的下限。某个公式宽到放不进公式列时，会先缩字号，缩到下限
        仍放不下就告警——那时候应该拆公式或加大 width_frac。

    注意
    ----
    公式用 **mathtext** 语法，不是 LaTeX：``\\text{}``、``\\limits``、``align``
    这些都不支持（``\\lim\\limits_{t\\to\\infty}`` 会被画成 "limlimits"）。
    写 ``\\lim_{t\\to\\infty}`` 即可，下标位置 mathtext 自己会处理。

    适用场景
    --------
    微分方程求解步骤、递推式展开、评价模型归一化公式的来历、
    优化问题的 KKT 条件推导——这些内容光看公式编号很难跟，配一张推导图
    读者立刻明白每一步在干什么。

    返回
    ----
    (Figure, Axes)
    """
    steps = list(steps)
    if not steps:
        raise ValueError("derivation_diagram 需要至少一个步骤")
    n = len(steps)
    fig_h = 0.45 + row_in * n
    fig_w = TEXT_WIDTH_IN * width_frac
    if ax is None:
        fig, ax = plt.subplots(figsize=(round(fig_w, 3), round(fig_h, 3)))
    else:
        fig = ax.figure
    ax.set_axis_off()
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, n)

    if fontsize is None:
        fontsize = rcParams["font.size"] + 0.5
    if note_fontsize is None:
        note_fontsize = rcParams["font.size"] - 1.5

    eq_cx = (eq_left + note_x) / 2.0        # 公式列中心
    eq_right = note_x - 0.03                # 公式列右边界（留 3% 空隙）
    # 旁注折行宽度：把英寸换算成"显示宽度单位"（汉字算 2 个单位）
    note_in = max(0.5, (1.0 - note_x - 0.02) * fig_w)
    note_units = max(8, int(note_in / (note_fontsize / 72.0)) * 2 - 2)

    eq_texts, note_texts = [], []
    for i, raw in enumerate(steps):
        spec = {"expr": raw} if isinstance(raw, str) else dict(raw)
        y = n - i - 0.5
        expr = str(spec.get("expr", ""))
        eq_texts.append(ax.text(eq_cx, y, expr, ha="center", va="center",
                                fontsize=fontsize, color="#111111", zorder=3))

        note = spec.get("note")
        if note:
            note_texts.append(ax.text(
                note_x, y, _wrap_cjk(note, note_units), ha="left", va="center",
                fontsize=note_fontsize, color=MUTED_COLOR, zorder=4, linespacing=1.3))

        if i < n - 1:
            ax.add_patch(FancyArrowPatch(
                (eq_cx, y - 0.28), (eq_cx, y - 0.72), arrowstyle="-|>",
                mutation_scale=11, linewidth=1.1, color=EDGE_COLOR,
                shrinkA=0, shrinkB=0, zorder=2,
            ))
            op = spec.get("op")
            if op:
                ax.text(eq_cx + 0.035, y - 0.5, op, ha="left", va="center",
                        fontsize=note_fontsize, color=COLORS[1], zorder=4)

    _fit_texts(fig, ax, eq_texts, x0=eq_left, x1=eq_right, min_size=min_fontsize,
               what="公式")
    return _finish(fig, ax, "derivation_diagram",
                   data={"steps": n, "exprs": [t.get_text() for t in eq_texts]})


def _fit_texts(fig, ax, texts, x0, x1, min_size=6.5, what="文本"):
    """把超宽的文本字号压到能塞进 [x0, x1]（axes 比例坐标）为止。

    宁可让某个公式小半号，也不要它压在旁边的说明文字上。
    """
    if not texts:
        return
    fig.canvas.draw()
    rend = _renderer(fig)
    inv = ax.transAxes.inverted()
    avail = x1 - x0
    too_wide = []
    for t in texts:
        try:
            bb = t.get_window_extent(rend).transformed(inv)
        except Exception:
            continue
        w = bb.x1 - bb.x0
        if w > avail > 0:
            size = t.get_fontsize()
            new = max(min_size, size * avail / w)
            t.set_fontsize(new)
            if new <= min_size + 1e-6 and size * avail / w < min_size:
                too_wide.append(t.get_text()[:36])
    if too_wide:
        warnings.warn(
            f"mmfig: {len(too_wide)} 个{what}即使缩到 {min_size}pt 仍放不下，"
            "可能压到右侧说明文字。请拆分公式，或把 width_frac 调大。\n  "
            + "\n  ".join(too_wide[:3]),
            UserWarning, stacklevel=3,
        )
