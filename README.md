# Skills Idea to Ship

从一句话想法开始，澄清 Skill 的用途与边界，再为写好的技能设计测试、审查用例、执行评测、审查优化。本仓库提供三个可以独立使用、也可以配合使用的技能。

| 技能 | 什么时候用 | 主要交付 |
|---|---|---|
| [`skill-challenger`](skills/skill-challenger/SKILL.md) | 想创建新技能，但用途、输入输出或验收还不明确 | 红黄绿灯、准入状态和创建需求简报 |
| [`skill-evals`](skills/skill-evals/SKILL.md) | 创建、自审、执行或修复技能测试 | 用例、覆盖矩阵、修改记录、实际输出与测试报告 |
| [`skill-optimizer`](skills/skill-optimizer/SKILL.md) | 已有技能存在误触发、冗余规则、执行停顿或结构问题 | 审查结论、修改方案，以及获授权后的修改与验证 |

## 如何配合使用

```text
新建：技能想法 → skill-challenger → 技能编写 → skill-evals（创建 → 自审 → 执行 → 修复重跑）
迭代：已有技能与用例 → skill-evals（自审 → 执行 → 问题分流 → 修改后重跑）
优化：skill-optimizer（审查 → 方案 → 授权后修改）→ skill-evals 回归重跑
```

`skill-challenger` 负责需求澄清，实际编写由宿主可用的 `skill-creator` 等工具或技能编写流程完成。已有技能可以直接进入测试或优化，无需从头走一遍。

`skill-evals` 已合并原用例创建、审查和执行能力，原三个独立入口不再保留。创建后自行审查准确性与完整性，充分后自动执行；明确的用例错误或有依据的漏测自动修复，业务歧义先给具体建议并确认。需要修改被测 Skill 或其实现时，先给原因与计划，用户确认后实施。每批修改后重新自审并重跑，保留前后记录。只需整体优化技能时仍可单独使用 `skill-optimizer`。

修改技能的边界：`skill-evals` 做的是测试驱动的定点修复——评测暴露具体失败用例后，定位到具体指令并修改，再用重跑验证。失败分流时，若根因不是单点错误，而是触发边界过宽、规则冗余或整体结构问题，转交 `skill-optimizer` 做整体审查与方案，不在用例上逐个打补丁。`skill-optimizer` 完成修改后，用 `skill-evals` 的既有用例回归重跑：静态审查不能证明行为没有退化。

## 安装

将所需技能的**整个目录**复制到宿主的技能目录，保留其中的 `references/`、`scripts/`、`evals/` 等配套文件。例如，安装到 `~/.agents/skills`：

```bash
mkdir -p ~/.agents/skills
cp -R skills/skill-challenger ~/.agents/skills/
cp -R skills/skill-evals ~/.agents/skills/
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

## Skill 测试

```text
使用 $skill-evals，给这个技能创建测试用例，自审准确性与完整性，充分后自动跑一轮并给报告。
```

默认从 2–3 个用例起步，数量不作为完整性的上限。自审生成覆盖矩阵，检查输入能否触发分支、预期是否准确、核心要求与重要边界是否有效覆盖。明确错误自动修复；需要业务判断时先给建议和补改方案，确认后继续。被测技能修改始终先给计划与原因，确认后实施并重跑。所有修改在新 iteration 中验证，不能引用修改前的通过结果作为验证。

按任务选择判定方式：确定性任务继续用通过／不通过；适合质量分级的任务可以推荐评分项、权重和判分标准，用户确认后才启用。报告展示各用例分项与加权总分，硬性断言单列，缺评分证据不记零分。具体约定见 [可选质量评分](skills/skill-evals/references/scoring.md)。

也可以限定范围：

```text
使用 $skill-evals，只审查 /path/to/my-skill 的用例，给出覆盖矩阵和最小补改建议，不修改或执行。
使用 $skill-evals，只设计用例，不要运行。
使用 $skill-evals，执行 /path/to/my-skill 的现有用例，和不使用技能的结果对比。
使用 $skill-evals，比较 /path/to/new-skill 与 /path/to/old-skill，每例重复三次。
```

默认每例一次、只跑候选技能；显式要求比较时才添加无技能或旧版基线。结构检查、准备工作区和汇总脚本仅依赖 Python 3，实际模型任务需要宿主提供独立上下文运行能力。下面的默认命令必须带 `--candidate-only`；裸 `prepare` 命令保留无技能对照能力：

```bash
python3 skills/skill-evals/scripts/validate_evals.py /path/to/my-skill/evals/evals.json
python3 skills/skill-evals/scripts/eval_workspace.py prepare --skill /path/to/my-skill --candidate-only
# 此处由代理实际执行各 task.json、保存真实产物并评分。
python3 skills/skill-evals/scripts/eval_workspace.py summarize /path/to/my-skill-workspace/iteration-1
```

自审流程见 [review.md](skills/skill-evals/references/review.md)，实际执行与证据契约见 [execution.md](skills/skill-evals/references/execution.md) 和 [run-protocol.md](skills/skill-evals/references/run-protocol.md)。自身行为用例见 [evals.json](skills/skill-evals/evals/evals.json)，脚本测试运行方式：

```bash
python3 -m unittest discover -s skills/skill-evals/tests -v
```

用例或报告文件存在不等于已执行。运行失败、缺权限、环境阻断与未评分会分别记录；没有实际输出不报告通过率。同一问题连续两轮修复重跑仍失败时停止自动循环，交付证据和待决策项。

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

## 进阶推荐

如果想进一步进阶，推荐了解微软的 [SkillOpt](https://github.com/microsoft/skillopt)。

## 验证范围

- 本仓库的验收场景与评测用例是检查材料，文件存在不代表已经完成模型运行评测。
- JSON 检查器和脚本测试验证结构及程序行为，不能证明技能输出质量或自动触发率。
- 实际评测需要读取真实产物并保存证据；缺测、运行失败、隔离受限和未评分应在报告中保留，不能记为通过。
