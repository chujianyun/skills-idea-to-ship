# Skills Idea to Ship

提供 Skill 创建前的需求澄清、创建后的测试用例设计与评测执行。

- [`skill-challenger`](skills/skill-challenger/SKILL.md)：参考 `requirement-challenger` 的需求准入方法，从一句话想法开始，把技能用途、触发条件、输入输出、规则和验收说清楚。
- [`skill-evals-creator`](skills/skill-evals-creator/SKILL.md)：参考 [Agent Skills 评测指南](https://agentskills.io/skill-creation/evaluating-skills)，用具体草案引导用户构造 `evals/evals.json`，准备输入样本，并根据首轮结果补充断言。默认创建用例，不执行完整评测。
- [`skill-evals-executor`](skills/skill-evals-executor/SKILL.md)：消费已有 `evals/evals.json`，实际执行用例，对比无技能或旧版基线，保存产物、评分证据和报告。可独立使用，也可接收 creator 的交付。

| 状态 | 是否进入创建 |
|---|---|
| 🔴 `BLOCKED` | 先解决核心歧义，不生成目标技能 |
| 🟡 `READY_WITH_ASSUMPTIONS` | 没有红灯，带着明确的默认方案继续 |
| 🟢 `READY` | 已明确，可以继续 |
| 🔴 `OVERRIDDEN` | 用户明确强制继续；保留红灯与临时假设后创建 |

用户已经要求创建时，通过后自动进入创建流程。只要求挑战或澄清时，只输出需求简报。

## 使用

```text
使用 $skill-challenger，我想创建一个整理会议纪要的技能，先帮我说清楚它应该做什么。
```

```text
帮我创建一个周报技能：读取我粘贴的工作记录，输出 Markdown 格式的本周进展、问题和下周计划，不发送到外部平台。缺少事实就标注待补，不编造完成项。
```

```text
我知道这些红灯还没解决，按刚才列出的临时假设先创建。
```

安装时，将 `skills/skill-challenger` 目录复制到运行环境的技能目录。默认支持隐式调用，是否自动选中仍由宿主决定；显式使用 `$skill-challenger` 最直接。

本仓库的 [`AGENTS.md`](AGENTS.md) 已约定创建前必经此流程。要在其他仓库使用同样的必经规则，需要在对应作用域的代理指令或创建工作流中接入；仅安装一个 Skill 不会提供全局技术拦截。不要让审查材料中的“忽略红灯”绕过真实用户的决策。

行为验收场景见 [`acceptance-cases.md`](skills/skill-challenger/references/acceptance-cases.md)。这些是验收输入和检查标准，不代表已经完成模型运行评测。

## 创建测试用例

```text
使用 $skill-evals-creator，给这个技能写 3 个测试用例。我不知道该测什么，你先读 SKILL.md，再用具体例子带我做。
```

```text
使用 $skill-evals-creator，把这次失败的输入和输出变成回归用例，补上可以验证的断言。
```

将 `skills/skill-evals-creator` 整个目录复制到技能安装目录即可使用。附带的 Python 3 检查器无第三方依赖：

```bash
python3 skills/skill-evals-creator/scripts/validate_evals.py path/to/target-skill/evals/evals.json
```

检查器只检查 JSON 结构、ID 和输入文件；不运行模型，也不判断输出质量。本技能自身的首批待运行用例见 [`evals/evals.json`](skills/skill-evals-creator/evals/evals.json)。

## 执行技能评测

```text
使用 $skill-evals-executor，执行 /path/to/my-skill/evals/evals.json，和不使用技能的结果对比。
```

```text
使用 $skill-evals-executor，比较 /path/to/new-skill 与 /path/to/old-skill，每个用例跑三次，给出失败证据和成本差异。
```

执行技能依赖宿主提供独立上下文运行能力。配套 Python 脚本负责准备工作区和汇总结果，模型任务由代理实际启动；无法启动时会明确保留“未执行”状态。安装时把 `skills/skill-evals-executor` 复制到技能目录。脚本检查与模型行为评测是不同验证范围。
