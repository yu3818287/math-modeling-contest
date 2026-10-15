# scripts

两个脚本，都可以脱离 Agent 独立使用。

| 脚本 | 用途 | 依赖 |
|---|---|---|
| `check_paper.py` | 提交前的论文硬校验（12 项） | Python 3.9+；`pypdf` 可选（用于精确页数） |
| `mmfig.py` | 按竞赛绘图规范出图 | matplotlib、numpy |

`selftest_mmfig.py` 是 `mmfig.py` 的自测脚本，逐图校验中文渲染、图例位置、配色与裁切，共 97 项。

## check_paper.py

```bash
python check_paper.py paper/main.tex \
  --ruleset cumcm \
  --numbers results/numbers.json \
  --pdf paper/main.pdf
```

| 参数 | 说明 |
|---|---|
| `--ruleset {cumcm,mcm}` | 赛事口径，决定页数上限与结构要求，默认 `cumcm` |
| `--numbers PATH` | `numbers.json`，用于数值溯源。**这是最有价值的一项，建议总是提供** |
| `--pdf PATH` | 编译后的 PDF，用于精确页数统计 |
| `--bib PATH` | `refs.bib`，默认在 tex 同目录查找 |
| `--identity-words A,B` | 额外的身份敏感词（学校名、队号等） |
| `--json PATH` | 同时输出机器可读的报告 |
| `--quiet` | 只输出问题项 |

退出码：`0` 全部通过，`1` 存在失败项，`2` 用法或读文件错误。

跳过某一行的数字检查：在该行加 `% check:ignore`。

## mmfig.py

先把 `scripts/` 与 `assets/` 加入路径：

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("<skill>/scripts")))
import mmfig

info = mmfig.use_style()          # 加载 assets/mm.mplstyle 并配置中文字体
print(info)                       # 报告探测到的中文字体
```

`use_style()` 会探测系统中的中文字体并注册回退。**找不到中文字体时会明确警告**，而不是静默把中文画成方框——方框图在脚本层面是"成功"的，只有打开图片才看得出来，所以这个警告很重要。

### 常用图型

```python
# 折线趋势对比（多方案）
fig = mmfig.line_trend(days, {"方案 A": a, "方案 B": b},
                       xlabel="调度周期 (天)", ylabel="总成本 (万元)")
mmfig.save(fig, "figures/fig_cost_trend")

# 带误差棒 / 置信区间
fig = mmfig.errorbar_plot(x, series, yerr=err,
                          xlabel="预测步长 (周)", ylabel="误差 (%)")

# 柱状图（数值直接标在柱上）
fig = mmfig.bar_chart(cities, {"覆盖率 (%)": vals}, xlabel="城市", ylabel="比率 (%)")

# 散点 + 拟合线（图中显示 R²）
fig = mmfig.scatter_fit(x, y, xlabel="区域生产总值 (亿元)", ylabel="能耗 (万吨标煤)")

# 多组散点拟合
fig = mmfig.scatter_fit_multi(groups, xlabel="...", ylabel="...")

# 热力图
fig = mmfig.heatmap(matrix, row_labels, col_labels, xlabel="...", ylabel="...")

# 帕累托前沿 / 多目标权衡
fig = mmfig.pareto_front(cost, benefit, minimize=(True, False))

# 算法流程图
fig = mmfig.flow_diagram(steps, feedback="未收敛则更新种群后继续迭代")

# 公式推导示意图
fig = mmfig.derivation_diagram(steps)
```

其他函数：`palette()` 取配色，`figsize()` 按论文正文宽度算画布尺寸，`legend_right(ax)` 放右侧图例，`style_axes(ax, ...)` 统一坐标轴，`font_report()` 报告字体探测结果。

### 自检

```python
rep = mmfig.figure_report(fig)    # 报告图例位置、字号、配色数、碰撞结论
print(rep["collisions"]["verdict"])
mmfig.save(fig, "figures/fig_x", data={"q1": 1284500})
```

`save()` 同时输出 `.png` 与 `.svg`（300dpi、tight、字体可嵌入），并打印保存路径，方便据此打开查看。

`save()` 还会**主动拦截三类违规**，都是显式报错而不是建议：

| 拦截项 | 行为 |
|---|---|
| 2×2 及以上拼图布局 | 直接抛错 |
| 图内标题（标题应由 LaTeX 的 `\caption` 负责） | 发警告 |
| **文字互相压住**（重叠面积超过较小者的 50%） | 直接抛错 |

调整布局的过程中需要先存一张看看时，可以传 `check_collisions=False` 临时放行。

### 碰撞检测

`detect_collisions()` 用 matplotlib 渲染器实测的包围盒，逐对检查文字元素是否压住：

```python
rep = mmfig.detect_collisions(fig)
rep["verdict"]      # 'OK' / 'REVIEW REQUIRED' / 'FIX BEFORE DELIVERY'
rep["collisions"]   # [{'a': ..., 'b': ..., 'overlap_pt': (dx, dy), 'area_frac': 0.94}]
rep["overflow"]     # 明显越出画布的元素，含 text / pt / side
```

判定分档：

- **重叠面积 ≥ 较小包围盒的 50%** → `FIX BEFORE DELIVERY`，`save()` 拒绝保存
- **有重叠，或元素越出画布超过 12 磅** → `REVIEW REQUIRED`，发警告
- **其余** → `OK`

12 磅这个阈值是有意设的：刻度标签探出画布边缘几个磅是常态，保存时 `bbox_inches='tight'` 会把它收进来，不算问题；但整块图例探出去几十磅就说明版面比声明的宽，插进论文会被整体缩小——那才值得提醒。

**不需要任何额外依赖**（不需要 PyMuPDF、不需要先导出 PDF），它直接读 matplotlib 的渲染结果。

这类问题的特点是**在缩略图上看不出来**：数值标注互相压住、曲线末端标注压住图例、刻度标签叠在一起——只有印到纸上才发现。所以值得自动做，而不是靠人眼过一遍。

`verify_style()` 用于检查样式文件本身是否合规，通常在自测里调用。

### 跑自测

```bash
python selftest_mmfig.py
```

会逐图校验：输出格式、非 2×2 布局、图内无标题、图例在右侧、图例未压住绘图区、图例未被裁切、颜色全部来自规范配色、PNG 四边无墨迹（未被裁切）、**文字无重叠无越界**，并逐字符校验中文是否有字形。当前为 **102 项全通过**。

## 一条纪律

**论文里的图片必须由代码生成、可复现。禁止手工拼图或截图。**

手工处理的图无法复现，也无法响应数据更新——结果一旦修正，就得重新拼一遍，而且很容易漏掉某张。绘图脚本应当从 `results/` 读取数据文件，而不是把数字重新硬编码一遍：硬编码等于制造了第二个数据源，两处迟早会不一致。

美赛的提交条款也要求论文中的每张图要么由参赛队创作、要么在对应位置给出具体引用，用代码生成是最省事的合规做法。
