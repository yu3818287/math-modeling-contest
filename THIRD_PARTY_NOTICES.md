# 第三方来源与致谢

本技能在绘图部分参考了开源项目 **nature-figure** 的设计思路。按 Apache-2.0 的要求，这里说明参考了什么、以及我们做了哪些改动。

## 参考来源

| 项目 | 地址 | 许可 | 作者 |
|---|---|---|---|
| nature-skills | <https://github.com/Yuan1z0825/nature-skills> | Apache License 2.0 | Yuan1z0825 |

本项目中的子技能 `skills/nature-figure` 面向 **Nature 等期刊投稿**的科研配图。它设计得相当扎实，尤其在这几点上：

1. **图契约（figure contract）**——动笔写绘图代码之前，先写清楚"这张图要证明什么结论、证据链是什么"，再决定画什么。它坚持"the chart serves the scientific logic"，美观服从于把核心结论讲清楚。
2. **碰撞审查（collision audit）**——导出后对成品做几何检测，找出文字元素互相压住的地方，并区分 `FIX BEFORE DELIVERY` / `REVIEW REQUIRED` / `NOT AUDITABLE` 三档结论。
3. **在最终物理尺寸下检查**——不看缩略图，按图在版面里的实际大小逐块过一遍。
4. **克制的配色**与"一个主面板"的构图原则。

## 我们做了什么

`nature-figure` 面向期刊投稿，与本项目的场景（数学建模竞赛）有几处**直接冲突**，因此**没有整包引入**，只吸收了可适用的思路并做了适配：

### 吸收并重写的

| 能力 | 我们的实现 | 与 nature-figure 的差异 |
|---|---|---|
| 碰撞检测 | `mmfig.detect_collisions()` | **完全重写**。它用 PyMuPDF 解析导出的 PDF；我们直接取 matplotlib 渲染器里的文字包围盒，**不引入任何额外依赖**。判据与阈值也是自己定的（重叠面积占较小包围盒的比例）。 |
| 图契约 | `references/figures.md` 的"画图之前先写图契约"一节 | 按其思路重写为竞赛语境（这张图要回答题目的哪一问、支撑什么结论）。 |
| 最终尺寸检查 | 写入 `references/figures.md` 与 `save()` 的提示语 | 同上。 |

**没有复制任何源代码或文档文本。** `detect_collisions()` 是独立实现，用的是 matplotlib 自身的 API。

### 明确没有引入的

| nature-figure 的做法 | 不引入的原因 |
|---|---|
| 鼓励多面板（multi-panel）构图、面板承担不同推断角色 | **与竞赛规则冲突**。国赛明令禁止 2×2 拼图，也不要把 4 张图拼成 1 张。两套构图哲学放在一起会让模型无所适从。 |
| Python / R 双后端门禁 | 竞赛场景只用 Python（支撑材料里附录的代码需要统一可复跑）。 |
| 用 OpenRouter 等图像生成 API 画示意图 | ⚠️ **在竞赛里有实质风险**。国赛《AI 工具使用规定（2026 年试行）》要求 AI 使用必须声明，且"将未经必要人工审查与核实的 AI 生成内容直接作为核心建模与分析成果提交"会被取消评奖资格。把这条搬进来等于给使用者埋雷。`mmfig.flow_diagram()` / `derivation_diagram()` 用 matplotlib 原生绘制，不需要图像生成 API。 |
| Nature / Nature Machine Intelligence 的投稿页数与图注字数限制 | 与竞赛评审无关。竞赛的页数与摘要要求见 `references/cumcm.md` 与 `references/mcm.md`。 |
| 庞大的 manifest / 路由分层结构 | 我们只有一份竞赛技能，分层反而增加加载成本。 |

### 附带修掉的一个真实缺陷

加入碰撞检测后，第一次跑自测就发现 `flow_diagram()` 的图例挂在坐标轴外侧却没有预留宽度，实测挤出画布约 **45 磅**——保存出来的图比声明的宽，插进论文会被整体缩小。已修复（`legend_right(..., reserve=True)`）。这个问题在加入检测之前一直存在，靠肉眼看缩略图发现不了。

## 如果你需要期刊级配图

本技能的目标是**竞赛论文配图**：图形要讲清结论、格式要合规、数据要能追溯。

如果你要做的是**期刊投稿**的图（多面板证据架构、期刊具体格式要求、图注字数限制等），建议直接安装原项目：

```bash
npx bzskills add Yuan1z0825/nature-skills --skill nature-figure
```

或者克隆 <https://github.com/Yuan1z0825/nature-skills>。它在这方面的覆盖远比我们完整。

## 许可

本项目整体采用 MIT 许可（见 `LICENSE`）。

上述参考仅涉及**设计思路**，未包含来自 nature-skills 的代码或文本，因此本项目的 MIT 许可以及 Apache-2.0 之间不存在许可冲突。此处保留来源说明是出于学术诚信与致谢，而非许可义务。
