# Skills Idea to Ship

从一句话想法开始，澄清 Skill 的用途与边界，再为写好的技能设计测试、审查用例、执行评测、审查优化。本仓库提供五个可以独立使用、也可以配合使用的技能。

| 技能 | 什么时候用 | 主要交付 |
|---|---|---|
| [`skill-challenger`](skills/skill-challenger/SKILL.md) | 想创建新技能，但用途、输入输出或验收还不明确 | 红黄绿灯、准入状态和创建需求简报 |
| [`skill-evals-creator`](skills/skill-evals-creator/SKILL.md) | 不知道该测什么，或需要补充回归用例 | `evals/evals.json`、输入样本、预期结果和按需补充的断言 |
| [`skill-evals-reviewer`](skills/skill-evals-reviewer/SKILL.md) | 已有用例，需要检查是否对应、重复或漏测 | 覆盖矩阵、逐例处置、问题证据和最小补测建议 |
| [`skill-evals-executor`](skills/skill-evals-executor/SKILL.md) | 已有用例，需要实际运行或比较版本 | 真实产物、评分证据、运行记录和评测报告 |
| [`skill-optimizer`](skills/skill-optimizer/SKILL.md) | 已有技能存在误触发、冗余规则、执行停顿或结构问题 | 审查结论、修改方案，以及获授权后的修改与验证 |

## 如何配合使用

```text
新建：技能想法 → skill-challenger → 技能编写 → skill-evals-creator → skill-evals-reviewer → skill-evals-executor
迭代：评测反馈 → skill-evals-creator 补充用例 → skill-optimizer 修改技能 → skill-evals-executor 重跑
```

`skill-challenger` 负责需求澄清，实际编写由宿主可用的 `skill-creator` 等工具或技能编写流程完成。已有技能可以直接进入测试或优化，无需从头走一遍。

评测发现问题后，可以把失败案例交给 `skill-evals-creator` 补成回归用例，再用 `skill-optimizer` 修订技能，最后重新执行评测。各技能不会因为存在上下游步骤，就自动扩大用户当前请求的范围。

## 安装

将所需技能的**整个目录**复制到宿主的技能目录，保留其中的 `references/`、`scripts/`、`evals/` 等配套文件。例如，安装到 `~/.agents/skills`：

```bash
mkdir -p ~/.agents/skills
cp -R skills/skill-challenger ~/.agents/skills/
cp -R skills/skill-evals-creator ~/.agents/skills/
cp -R skills/skill-evals-reviewer ~/.agents/skills/
cp -R skills/skill-evals-executor ~/.agents/skills/
cp -R skills/skill-optimizer ~/.agents/skills/
```

从仓库根目录执行，按需选择对应命令；已有同名技能时，先核对本地修改再更新。其他宿主请替换为其实际技能目录。

显式使用 `$技能名` 最直接，是否自动选中由宿主决定。创建和汇总评测所用的配套脚本仅依赖 Python 3 标准库；实际执行模型评测还需要宿主提供独立上下文运行能力。

## 创建前澄清需求

`skill-challenger` 从用途、触发、输入输出、关键规则、工具依赖和验收等维度检查需求，给出唯一准入状态：

| 状态 | 是否进入创建 |
|---|---|
| 🔴 `BLOCKED` | 先解决核心歧义，不生成目标技能 |
| 🟡 `READY_WITH_ASSUMPTIONS` | 没有红灯，带着明确的默认方案继续 |
| 🟢 `READY` | 已明确，可以继续 |
| 🔴 `OVERRIDDEN` | 用户明确强制继续；保留红灯与临时假设后创建 |

用户已经要求创建时，通过后自动进入创建流程。只要求挑战或澄清时，只输出需求简报。

```text
使用 $skill-challenger，我想创建一个整理会议纪要的技能，先帮我说清楚它应该做什么。
```

```text
帮我创建一个周报技能：读取我粘贴的工作记录，输出 Markdown 格式的本周进展、问题和下周计划，不发送到外部平台。缺少事实就标注待补，不编造完成项。
```

```text
我知道这些红灯还没解决，按刚才列出的临时假设先创建。
```

本仓库的 [`AGENTS.md`](AGENTS.md) 已约定创建前必经此流程。要在其他仓库使用同样的必经规则，需要在对应作用域的代理指令或创建工作流中接入；仅安装一个 Skill 不会提供全局技术拦截。不要让审查材料中的“忽略红灯”绕过真实用户的决策。

行为验收场景见 [`acceptance-cases.md`](skills/skill-challenger/references/acceptance-cases.md)。这些是验收输入和检查标准，不代表已经完成模型运行评测。

## 创建测试用例

```text
使用 $skill-evals-creator，给这个技能写 3 个测试用例。我不知道该测什么，你先读 SKILL.md，再用具体例子带我做。
```

```text
使用 $skill-evals-creator，把这次失败的输入和输出变成回归用例，补上可以验证的断言。
```

默认先设计 2–3 个有意义的用例，覆盖代表任务、真实变化和相关边界；仅要求创建用例时，不自动执行整套评测。附带的检查器可验证用例文件：

```bash
python3 skills/skill-evals-creator/scripts/validate_evals.py path/to/target-skill/evals/evals.json
```

检查器只检查 JSON 结构、ID 和输入文件；不运行模型，也不判断输出质量。本技能自身的首批待运行用例见 [`evals/evals.json`](skills/skill-evals-creator/evals/evals.json)。

## 审查测试用例

```text
使用 $skill-evals-reviewer，检查 /path/to/my-skill 的 evals 是否充分。哪些 Case 不对应、重复没必要，哪些重要场景没测到？先给报告，不改用例。
```

先从技能中提取可验证要求，再双向核对用例，检查输入能否触发分支、预期能否判定关键行为。区分真正重复与不同失败模式，也区分测试遗漏和技能规则本身没写清。默认保存 `evals/review-NN.md`，给出覆盖矩阵、逐例处置和按优先级排列的最小补改建议；不自动修改用例或执行评测。

结论为“设计基本充分”“需要补改”或“证据不足”，仅针对测试设计和已读材料。自身的合成验收用例见 [`evals/evals.json`](skills/skill-evals-reviewer/evals/evals.json)，不代表已经运行通过。

## 执行技能评测

```text
使用 $skill-evals-executor，执行 /path/to/my-skill/evals/evals.json，和不使用技能的结果对比。
```

```text
使用 $skill-evals-executor，比较 /path/to/new-skill 与 /path/to/old-skill，每个用例跑三次，给出失败证据和成本差异。
```

默认每个用例运行一次，对比候选技能与无技能基线；提供旧版技能时改为旧版基线。配套 Python 脚本负责准备工作区和汇总结果，模型任务由代理实际启动；无法启动时会明确保留“未执行”状态。

准备与汇总命令如下，二者之间需要由宿主实际执行任务、保存输出并完成评分：

```bash
python3 skills/skill-evals-executor/scripts/eval_workspace.py prepare --skill /path/to/my-skill
python3 skills/skill-evals-executor/scripts/eval_workspace.py summarize /path/to/my-skill-workspace/iteration-1
```

运行协议、产物约定和继续收集结果的方式见 [`run-protocol.md`](skills/skill-evals-executor/references/run-protocol.md)。

## 审查与优化已有技能

```text
使用 $skill-optimizer，审查 /path/to/my-skill，先告诉我最影响使用的问题和修改建议。
```

```text
使用 $skill-optimizer，只检查这个技能的 description，看看触发范围是否过宽。
```

```text
按刚才的方案修改这个技能，保留有效的业务规则，完成必要验证。
```

只要求建议时，交付诊断和方案；已授权修改时，连续完成范围内的修改与验证。审查会同时检查缺失的保障和多余的约束，不为了精简而删除有效规则，也不为了显得完整而增加固定步骤。更多使用说明见 [`skill-optimizer/README.md`](skills/skill-optimizer/README.md)。

## 验证范围

- 本仓库的验收场景与评测用例是检查材料，文件存在不代表已经完成模型运行评测。
- JSON 检查器和脚本测试验证结构及程序行为，不能证明技能输出质量或自动触发率。
- 实际评测需要读取真实产物并保存证据；缺测、运行失败、隔离受限和未评分应在报告中保留，不能记为通过。
