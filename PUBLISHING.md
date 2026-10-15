# 发布清单

这份文档列出**把本仓库发布到 GitHub 之前还需要你做的事**。技能本身（SKILL.md、references、scripts、assets、evals）已经完整，下面是剩下的。

## 一、必填项（不填会出问题）

> **状态：三项均已完成。** 记录在这里是为了让 fork 或改名的人知道要改哪些地方。

### 1. LICENSE 的版权署名 ✅

MIT 协议要求版权声明完整，占位符留在公开仓库里等于没有有效授权。当前为：

```
Copyright (c) 2026 yu3818287
```

如果你 fork 后要改成自己的名字，改 `LICENSE` 第 3 行。

### 2. 仓库名与地址 ✅

`README.md` 里的克隆地址与 CI 徽章已指向 `https://github.com/yu3818287/math-modeling-contest`。

仓库名建议保持 `math-modeling-contest`（与 `SKILL.md` 的 `name` 字段一致）。如果改名，**必须同步修改 `SKILL.md` frontmatter 里的 `name` 字段**——该字段是技能的标识符，和目录名不一致会导致加载异常。

### 3. 隐私扫描 ✅

已跑过，无真实校名、姓名、队号或本机路径。

改动仓库内容后建议重跑一遍：

```bash
# 用校验器扫文本里的学校名与本机路径
python scripts/check_paper.py --help

# 或直接全文搜（Windows Git Bash / WSL 下）
git grep -n -i -E "大学|学院|学号|队号|赛区|C:\\\\Users"

# PowerShell 下
Get-ChildItem . -Recurse -File | Select-String -Pattern 'C:\\Users|大学|学院|学号|队号|赛区'
```

```

注意：`tests/fixtures/` 里的样例是刻意构造的（含"某大学""XX 大学"），那是测试数据，不是你的信息，可以保留——但要看一眼确认里面没有混进真实校名。

## 二、需要你决定的

### 4. 是否保留国赛与美赛之外的赛事

目前支持国赛（CUMCM）与美赛（MCM/ICM）两套口径。如果你还参加过华为杯研赛、亚太赛、电工杯等，可以按同样的方式加 `references/<赛事>.md`，并在两处登记：

- `scripts/check_paper.py` 的 `RULESETS` 字典里加一项
- `SKILL.md` 的参考资料路由表里加一行

加的时候记得在文件开头写明依据的是哪一年的哪份官方文件。

### 5. 是否提供英文版 SKILL.md

目前正文是中文，README 末尾有英文摘要。如果你的目标受众包含美赛的国际参赛者，可以考虑再补一份英文 reference，但**不建议**直接机器翻译——赛事术语（如 Summary Sheet、Report on Use of AI）翻错比不翻更糟。

### 6. 是否附上你自己的参赛经历

README 里如果有"这个技能来自我参加 XX 比赛时的实践"这类说明，会显著提升可信度和 star 数。但如果要写，**不要透露具体是哪一年哪道题、也不能贴出你的论文原文**——美赛规则明确禁止在竞赛期间分享赛题与成果，往届论文的公开则需要看赛事的具体规定。

## 三、建议补充（不阻塞发布）

### 7. 演示动图

README 目前是纯文字。加一张校验器输出的截图或 GIF，转化率会明显不同。最容易做的一张：

```bash
python scripts/check_paper.py tests/fixtures/bad_paper/main.tex \
  --ruleset cumcm --numbers tests/fixtures/bad_paper/numbers.json
```

把这段输出截图贴进 README 的"校验器能查出什么"一节。

### 8. 持续集成

仓库已经带了回归测试。可以加一个 GitHub Actions 工作流，每次 push 自动跑：

```yaml
# .github/workflows/test.yml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pypdf
      - run: python tests/run_tests.py
```

注意 `--compile` 那部分需要 XeLaTeX 与中文字体，CI 上配置成本较高，默认不跑。

### 9. 已知局限写进 README

诚实地把局限写出来，比被使用者发现要好：

- 校验器只覆盖**可机器判定**的项目（A 类），题意理解、逻辑因果、模型选型这些判不了
- 页数统计需要先编译出 PDF，且依赖 `pypdf`（未安装时降级为对象计数估算，可能有偏差）
- 赛事规范每年修订，仓库里的口径是**快照**，必须核对当年官方通知
- 中文 LaTeX 模板依赖 XeLaTeX 与系统中文字体，纯 pdfLaTeX 环境无法编译

### 10. 首条提交信息

建议按 Conventional Commits 写，方便以后维护：

```
feat: 数学建模竞赛全流程 skill 首发

- SKILL.md：三条纪律 + 六步工作流 + 输出目录契约
- references/：国赛与美赛官方口径、论文结构、文风、绘图、反幻觉、校验三分类
- scripts/check_paper.py：11 项提交前硬校验，支持双赛事口径
- scripts/mmfig.py + assets/mm.mplstyle：符合竞赛绘图规范的出图工具
- assets/latex/：国赛与美赛论文模板（均已编译验证）
- tests/：校验器回归测试（正例、反例、口径区分）
```

## 四、发布前最后一遍

```bash
# 1. 回归测试必须全绿
python tests/run_tests.py --compile

# 2. 技能结构必须通过官方校验
python -X utf8 <skill-creator>/scripts/quick_validate.py .

# 3. 隐私扫描
git grep -n -i -E "大学|学院|学号|队号|赛区|C:\\\\Users"

# 4. 确认没有编译产物被提交
git status --short

# 5. 初始化并推送
git init
git add -A
git commit -m "feat: 数学建模竞赛全流程 skill 首发"
git branch -M main
git remote add origin https://github.com/<your-name>/math-modeling-contest.git
git push -u origin main
```

`.gitignore` 已经覆盖了 LaTeX 编译产物、Python 缓存与常见的编辑器目录。

## 五、发布后：竞赛期间请留意 issue 与 discussion

这个仓库本身不含任何赛题内容，发布它没有问题。但**使用者**在竞赛期间的行为受规则约束，而规则**明确点名了 GitHub**。

国赛《参赛规则（2026 年修订稿）》第 5 条：

> 竞赛期间，参赛队员不得在任何交流平台（包括但不仅限于"贴吧"、QQ 群、微信群、网络直播间、知乎、小红书、CSDN、**GitHub** 等）浏览、发布或讨论与赛题相关的内容，否则一律视为严重违反竞赛纪律。严重违纪的参赛队将被**无条件取消评奖资格**。

美赛 COMAP 规则第 6 条同样禁止在竞赛期间分享赛题或成果，违规可判 Disqualified - Web。

实务上的建议：

1. **README 顶部保留提醒**（已写好），说清本仓库提供的是方法与模板，竞赛期间不要在这里贴赛题。
2. **每年竞赛窗口期临时关闭 issue 与 discussion**。国赛通常在 9 月上旬，美赛在 1 月末至 2 月初（以当年通知为准）。这是最省事的做法——使用者无意中粘贴赛题内容，往往不是恶意的，但后果由他们承担。
3. **不要建"赛题讨论"类的 issue 模板或讨论区**，哪怕初衷是帮助别人。
4. 如果你的仓库被大量使用，可以在竞赛期间把 README 顶部换成一条醒目的窗口期提示。

顺带一提：第 5 条禁止的不只是"发布"，**"浏览"同样违纪**——所以也不要引导使用者去别处检索题解。

## 六、发布前最后再确认一次三份国赛文件

国赛的规则由**三份并列文件**构成，缺任何一份都可能踩坑：

| 文件 | 管什么 | 本仓库对应章节 |
|---|---|---|
| 论文格式规范（2026 修订稿） | 排版、页数、提交 | `references/cumcm.md` 第一节、第三节 |
| **参赛规则（2026 修订稿）** | **竞赛纪律、违纪情形** | `references/cumcm.md` 第二节 |
| 人工智能工具使用规定（2026 试行） | AI 声明与留痕 | `references/cumcm.md` 第四节 |

第二份最容易漏——它不讲排版，但处罚最重（多处写明"无条件取消评奖资格"）。发布前请确认 `cumcm.md` 第二节还在，并且 `SKILL.md` 里那条 GitHub 禁令没有被删掉。
