# 美赛（MCM/ICM）格式与合规口径

> **依据版本**：COMAP 官方竞赛规则与说明页 *MCM/ICM Contest Rules, Registration and Instructions*（2027 赛季版本）。
>
> **重要**：COMAP 明确表示规则会随技术发展调整，且"COMAP is the final arbiter of all rules and policies"。本文件是核对过的版本快照。使用前必须提醒用户核对 COMAP 官网当年发布的最新 instructions。

## 一、25 页上限：范围比多数人以为的大得多

2027 赛季起，COMAP 把 25 页限制的适用范围写得很明确：

> The 25 page limit applies to the entire submission including the Summary Sheet, Solution, Reference List, Table of Contents, Notes, **Appendices, Code** and any problem specific requirements.

也就是说，下面这些**全部**计入 25 页：

- Summary Sheet（摘要页，第 1 页）
- 正文 Solution
- Table of Contents
- Reference List / Bibliography
- Notes
- **Appendices（附录）**
- **Code（代码）**

这是最容易无意中超页的地方。很多队伍的代码附录动辄十几页，直接导致总页数爆掉。**唯一不计入 25 页的是 `Report on Use of AI` 一节**，它附在 25 页之后，本身没有页数限制。

实践建议：正文写完先数一次页数，再决定附录能放多少。不要先写完附录再发现正文放不下。代码如果需要提交，考虑只放关键片段，并在正文中说明完整代码的获取方式——但注意 COMAP 官方同时规定**不要把程序、数据等额外文件随论文发送**，所以"另行提交完整代码"这条路在美赛是走不通的，只能在 25 页内取舍。

## 二、页面格式

- 论文必须是 **Adobe PDF** 电子文件，**英文**撰写。
- 字体**不小于 12 磅**（a readable font of at least 12-point type）。
- **每一页顶部**必须包含队伍控制号和页码。官方给的示例格式是：
  ```
  Team # 0000000, Page 6 of 25
  ```
  用 LaTeX 实现时通常靠 `fancyhdr` 加 `lastpage` 宏包。
- 第 1 页是 Summary Sheet。
- **学生姓名、指导教师姓名、学校名称不得出现在任何一页上**。除队伍控制号外，不得含任何身份信息。

## 三、Summary Sheet（摘要页）

COMAP 对摘要的重视程度远高于多数人的预期。官方原文的几处表述：

> The summary is an essential part of your MCM/ICM paper and should appear as the first page of your solution report. **The judges place considerable weight on the summary, and winning papers are often distinguished from other papers based on the quality of the summary.**

写作要点（官方给的三条）：

1. 想象读者要靠摘要决定是否继续读正文。摘要要能**激发读者去了解细节**。
2. **摘要最后写**。它应当清晰描述你的建模路径，并突出最重要的结论。要留出专门的时间写摘要。
3. **只复述赛题、或从引言里剪切粘贴套话的摘要，会被判为 weak。**

第三点尤其重要——不要用"本文针对 XX 问题，建立了 XX 模型，得出了 XX 结论"这种模板句式堆满一页。摘要要具体到位：你做了什么、发现了什么、数字是多少。

## 四、正文应包含的内容

官方建议的结构要点（不是强制章节名，但内容要覆盖）：

- 问题的澄清或重述
- 所有变量与假设的清晰说明
- 陈述并**论证**合理的假设
- 对问题的分析，说明为什么选用该模型（motivating or justifying the model）
- 推导、计算、说明性算例放在正文，冗长的推导与计算放附录
- 模型设计，并讨论如何检验模型：**误差分析、灵敏度、稳定性**
- 讨论模型或方法的明显优缺点
- 给出结论并**明确报告结果**
- 记录资源与参考文献

注意最后一条要"explicitly report results"——结论要给具体数值和方案，不要停在定性描述。

## 五、AI 工具政策

COMAP 的 AI policy 适用于学生工作的所有方面，**从模型的研发（包括代码编写）到书面报告**。核心要求：

1. **在报告中清楚标明 AI 工具的使用**，包括用了哪个模型、用于什么目的。使用**内联引用**并在**参考文献**中列出。
2. **核实准确性、有效性与适当性**——特别是语言模型生成的引用，必须逐条检查，改正错误与不一致。
3. 提供规范的引用与参考文献，**双重检查引用是否准确**。
4. 注意**抄袭风险**——LLM 可能复现其他来源的大量文本，要回查原始出处。

并在正文末尾附加一节 **Report on Use of AI**，附在 25 页正文之后，该节无页数限制、不计入 25 页。

COMAP 的态度是"允许且有条件鼓励"，但明确提示在这些环节要谨慎：模型选择与构建、协助创建代码、解释数据与模型结果、得出科学结论。官方原文：

> There are many tasks in model development where human creativity and teamwork is essential, and where a reliance on AI tools introduces risks.

## 六、提交要求

- 通过 COMAP 的在线提交页提交，提交时需要队伍控制号、指导教师 ID、选题号。
- PDF 文件名用队伍控制号，例如 `0000000.pdf`。
- 附件必须小于 **25MB**。
- PDF 第 1 页是 summary，之后是 solution、references、appendices。
- **不要**随论文发送程序、软件、数据库或其他文件——评委不会使用它们。
- 提交后不得再修改。
- 提交即表示同意：作品及出版权利归 COMAP 所有；论文中的全部图片、表格、绘图要么由队伍自己创作，要么在对应位置给出具体引用。

最后这一条值得留意：**从网上找的图直接放进论文而不标注出处，属于违规**。能用代码自己生成的图就自己生成。

## 七、评分等级

从低到高：Unsuccessful Participant → Successful Participant → Honorable Mention → Meritorious → Finalist → Outstanding Winner。

被标记为 Disqualified 的典型原因：

- **Plagiarism**：引用来源未记录、逐字照搬、或与他队论文高度相似（COMAP 会用成对比较软件查重）。
- **Web**：在竞赛期间把题目、自己的解法或部分成果发布或分享到任何地方；或获取他人的解法。
- **Unsuccessful - Web**：队员访问了公开讨论赛题的网站或社交媒体。

注意 **Disqualified - Web** 这一条对使用本技能有直接影响：竞赛期间把赛题内容、自己的建模过程发到网上求助属于违规。技能生成的内容只能在队伍内部使用，**不要在竞赛窗口期内把赛题或成果发到公开平台**。这一点要在使用技能时提醒用户。

## 八、出处

- COMAP, *MCM/ICM Contest Rules, Registration and Instructions*：<https://www.contest.comap.com/undergraduate/contests/mcm/instructions.html>
- COMAP, *Use of AI Tools in COMAP Contests*：<https://www.contest.comap.com/undergraduate/contests/mcm/flyer/Contest_AI_Policy.pdf>

国赛与美赛的逐项对照见 `cumcm.md` 第五节的对照表。
