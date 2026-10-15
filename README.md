# math-modeling-contest

[![tests](https://github.com/yu3818287/math-modeling-contest/actions/workflows/test.yml/badge.svg)](https://github.com/yu3818287/math-modeling-contest/actions/workflows/test.yml)

一个面向**数学建模竞赛**的 Agent Skill：从赛题与附件数据出发，完成读题分析、建模求解、绘图、LaTeX 论文撰写，以及提交前的自动校验。同时覆盖**国赛（CUMCM）**与**美赛（MCM/ICM）**两套规则口径。

它和"在网上找一段建模 prompt 复制粘贴"的区别，主要在于三件事：

1. **规则是有出处的，而且区分赛事。** 国赛 **和** 美赛 **在页数、目录、附录、页码、AI 声明上的要求**方向相反**，混用会直接出问题。仓库里记录的是核对过官方原文的版本快照，并标注了出处与版本号。
2. **论文里的每个数字都能追溯。** 建 `results/numbers.json` 作为唯一事实源，`check_paper.py` 会扫描论文里每个数值，报出无法追溯的那些。这条直接对应国赛官方"运行结果与论文不符可能被取消评奖资格"的条款。
3. **校验是可执行的。** 常见做法是列一张二十多条"自动核查 XX 真实性"的清单，但其中大部分没有可执行判据，实际一条也不会落实。这里把它拆成了**脚本硬校验 / 半自动 / 人工自查**三类，每类都有明确的执行方式和责任人。

## 重要：使用前请先读这一节

**两个赛事都对 AI 工具的使用有明确规定，不遵守会被取消评奖资格。**

- 国赛自 2026 年 9 月 1 日起试行《人工智能工具使用规定（2026 年试行）》：须在**论文参考文献之前**设置"AI 工具使用声明"，措辞为规定文本二选一；使用了 AI 的，支撑材料中附《AI 工具使用详情.pdf》。该规定明确把"故意隐瞒 AI 使用""作出虚假声明""将未经必要人工审查与核实的 AI 生成内容直接作为核心建模与分析成果提交"列为取消评奖资格的情形。**适用范围包含"AI 智能体"——本技能正属于这一范畴，所以用它就必须声明。**
- 美赛要求正文内联引用 + 参考文献列出 AI 工具，并在 25 页正文后附 `Report on Use of AI`。

注意两个赛事的声明位置**方向相反**：国赛在参考文献**之前**，美赛在正文**之后**。


国赛《参赛规则（2026 年修订稿）》第 5 条**明确点名了 GitHub**：

> 竞赛期间，参赛队员不得在任何交流平台（包括但不仅限于"贴吧"、QQ 群、微信群、网络直播间、知乎、小红书、CSDN、**GitHub** 等）浏览、发布或讨论与赛题相关的内容，否则一律视为严重违反竞赛纪律。严重违纪的参赛队将被**无条件取消评奖资格**。

两个容易踩的点：**"浏览"同样违纪**——去搜别人发的题解，即使只是看，也算；处罚是无条件取消评奖资格。

**这个仓库提供的是方法与模板，不含任何赛题内容**，赛前学习和赛后复盘都可以正常使用。但如果你正在比赛中：

- 不要在 issue、discussion、commit 或 PR 里粘贴赛题原文、附件数据、你的建模过程或论文片段
- 不要用 GitHub 检索本题的相关讨论
- 维护者如果要在竞赛期间关闭 issue 与 discussion，是合理的做法

美赛也有同样的禁令（COMAP 规则第 6 条，违规可判 Disqualified - Web）。

本技能会在工作过程中产出 `AI_USAGE.md`，用于生成上述声明材料。具体条款与出处见 [`references/cumcm.md`](references/cumcm.md) 与 [`references/mcm.md`](references/mcm.md)。

> 赛事规范每年修订（例如国赛正文上限 2025 年是 20 页、2026 年改为 30 页；美赛 2027 起 25 页上限把代码和附录都算了进去）。仓库里记录的是核对时的版本，**使用前请以当年官方通知为准**。

## 安装

这是一个标准的 Agent Skill（`SKILL.md` + `references/` + `scripts/` + `assets/`）。

**Claude Code / 支持 skills 的 Agent**：把整个仓库目录放进 skills 目录即可。

```bash
# 用户级（对所有项目生效）
git clone https://github.com/yu3818287/math-modeling-contest.git \
  ~/.claude/skills/math-modeling-contest

# 或项目级
git clone https://github.com/yu3818287/math-modeling-contest.git \
  .claude/skills/math-modeling-contest
```

**Claude.ai / 其他支持上传 skill 的平台**：把仓库目录打包成 zip 上传。

**只想用校验器和绘图工具**：`scripts/` 和 `assets/` 里的东西不依赖 Agent，可以直接复制到你的论文项目里用。校验器只需要 Python 3.9+，页数统计建议装 `pypdf`（没装也能降级估算）。

```bash
python scripts/check_paper.py paper/main.tex \
  --ruleset cumcm \
  --numbers results/numbers.json \
  --pdf paper/main.pdf
```

## 包含什么

```
math-modeling-contest/
├── SKILL.md                     # 入口：三条纪律 + 六步工作流 + 输出目录契约
├── references/
│   ├── cumcm.md                 # 国赛三份官方文件：格式规范 + 参赛规则 + AI 使用规定
│   ├── mcm.md                   # 美赛规则 + 25 页上限范围 + AI 政策
│   ├── paper-structure.md       # 论文章节结构与各章写法
│   ├── writing-style.md         # 文风硬要求 + AI 腔套话对照表
│   ├── figures.md               # 图片硬要求、图契约与落地方式
│   ├── anti-hallucination.md    # numbers.json 登记格式与反幻觉纪律
│   └── verification.md          # 校验项三分类：脚本硬校验 / 半自动 / 人工自查
├── scripts/
│   ├── check_paper.py           # 提交前硬校验（12 项，可独立使用）
│   └── mmfig.py                 # 绘图工具：样式、色板、常用图型、碰撞检测
├── assets/
│   ├── mm.mplstyle              # matplotlib 样式：配色、字号、图例位置、导出格式
│   └── latex/
│       ├── cumcm/main.tex       # 国赛模板
│       └── mcm/main.tex         # 美赛模板
├── THIRD_PARTY_NOTICES.md       # 第三方来源与致谢
└── tests/fixtures/              # 校验器的测试样例（含正例与反例）
```

## 绘图：不只看图好不好看，也管排版有没有塌

`scripts/mmfig.py` 除了提供 13 个论文常用图型，还做两件"自动化检查"的事：

- **碰撞检测**：用 matplotlib 渲染器实测的包围盒，逐对比对文字是否互相压住——数值标注互相叠住、末端标注压住图例、刻度标签挤在一起。这些问题**在缩略图上看不出来，印到纸上才发现**。真的压住时 `save()` 直接拒绝保存，不给"先存一张回头再看"的机会。
- **格式拦截**：2×2 拼图（竞赛明令禁止）、图内标题（应由 LaTeX 的 `\caption` 负责）都会被拦下。

不需要任何额外依赖——不装 PyMuPDF，也不用先导出 PDF。

绘图前还有一步**图契约**：先写清楚"这张图要证明什么结论、数值来自哪个文件"，再决定画什么图型。想不清楚就不该画这张图。详见 [`references/figures.md`](references/figures.md)。

> 碰撞检测的思路参考了开源项目 [nature-figure](https://github.com/Yuan1z0825/nature-skills)（Apache-2.0），但为独立实现，并针对竞赛场景做了取舍。哪些吸收了、哪些刻意没引入、为什么，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 校验器能查出什么

`check_paper.py` 覆盖 12 项可机器判定的检查：

| 编号 | 检查项 |
|---|---|
| A1 | 论文中每个数值能否追溯到 `numbers.json` |
| A2 | 页数是否超出赛事上限 |
| A3 | 目录与摘要页是否符合赛事要求 |
| A4 | 12 个必备模块是否齐全 |
| A5 | 误差分析 / 灵敏度分析 / 稳健性分析是否都有 |
| A5b | AI 使用声明是否存在 |
| A6 | 图表标题、标签、正文引用是否完整（孤儿图表检测） |
| A7 | 公式编号规范，是否用"上式/下式"代替编号引用 |
| A8 | 三线表合规（竖线、`\hline` 混用检测） |
| A9 | 身份信息泄露（校名、署名、本机路径） |
| A10 | `\includegraphics` 引用的图片文件是否真的存在 |
| B1 | 参考文献"引用了但没列"与"列了但没引" |

试一下：

```bash
# 反例：故意包含各类问题的样例
python scripts/check_paper.py tests/fixtures/bad_paper/main.tex \
  --ruleset cumcm --numbers tests/fixtures/bad_paper/numbers.json

# 正例：合规样例，应全部通过（退出码 0）
python scripts/check_paper.py tests/fixtures/good_paper/main.tex \
  --ruleset cumcm --numbers tests/fixtures/good_paper/numbers.json
```

脚本只覆盖能机器判定的部分。题意理解、逻辑因果、模型选型、结果常识合理性、写作同质化这些必须人工核查，清单见 [`references/verification.md`](references/verification.md)。

## 国赛与美赛的关键差异

这张表是本仓库最实用的部分之一——两个赛事的规则在多个点上方向相反：

| 项目 | 国赛 CUMCM | 美赛 MCM/ICM |
|---|---|---|
| 语言 | 中文 | 英文 |
| 页数上限 | 正文不超过 30 页（2026 修订稿） | 全文件不超过 25 页 |
| 页数范围 | 仅正文，附录不限 | 含摘要页、目录、参考文献、附录、**代码** |
| 目录 | **不要目录** | **鼓励放目录**，且计入 25 页 |
| 页码 | 从摘要页起算为 1，页脚中部 | 每页顶部，`Team # 编号, Page X of 25` |
| 身份信息 | 摘要页、正文、附录均不得出现 | 任何页不得出现，仅可留控制号 |
| 附录 | 必须含完整可运行源代码，不限页数 | 计入 25 页，需精简 |
| AI 声明 | **参考文献之前**设"AI 工具使用声明"（规定措辞二选一）+ 支撑材料附《AI 工具使用详情.pdf》 | 正文后附 `Report on Use of AI`（不计页数） |
| 提交大小 | 论文 20MB；支撑材料 20MB | 单个 PDF 小于 25MB |

完整对照与条款原文见 [`references/cumcm.md`](references/cumcm.md)。

## 引用与出处

仓库中赛事规则的依据：

- 《全国大学生数学建模竞赛论文格式规范（2026 年修订稿）》，全国大学生数学建模竞赛组委会
- 《全国大学生数学建模竞赛参赛规则（2026 年修订稿）》，同上
- 《全国大学生数学建模竞赛人工智能工具使用规定（2026 年试行）》，同上
- COMAP, *MCM/ICM Contest Rules, Registration and Instructions*
- COMAP, *Use of AI Tools in COMAP Contests*

具体链接见各 reference 文件末尾的"出处"一节。

## 贡献

欢迎补充其他赛事口径（华为杯研赛、亚太赛、电工杯等）、补充图型函数、报告校验器误报漏报。

提交校验器改动时，请同时更新 `tests/fixtures/` 里的样例，并确认正例仍然全部通过、反例仍能报出问题：

```bash
python tests/run_tests.py --compile
```

## License

MIT，见 [LICENSE](LICENSE)。

---

## English summary

An agent skill for mathematical modeling contests (CUMCM and MCM/ICM): problem analysis, modeling, solving, figure generation, LaTeX paper writing, and pre-submission checking.

Three things set it apart from a copy-pasted prompt:

1. **Rules are sourced and per-contest.** CUMCM and MCM/ICM differ in *opposite* directions on page limits, table of contents, appendices, page numbering, and AI disclosure.
2. **Every number in the paper is traceable** to `results/numbers.json`, enforced by `scripts/check_paper.py`.
3. **Checks are executable** — split into script-verifiable, semi-automatic, and human-review categories, each with concrete criteria.

**Important:** both contests mandate disclosure of AI tool usage, and non-compliance can lead to disqualification. See `references/cumcm.md` and `references/mcm.md`.

Contest rules are revised annually. Always verify against the current official notice for your contest year.
