# 运行协议

## 工作区与冻结

`prepare` 默认在目标技能同级的 `<skill-name>-workspace/iteration-N/` 下生成：

```text
evals.json                 冻结用例；仅协调者/评分者读取
manifest.json              运行清单、快照哈希和断言
snapshots/with_skill/      候选技能快照
snapshots/old_skill/       可选旧版快照
eval-1/with_skill/run-1/
  inputs/                 每次运行自己的附件副本
  outputs/
  task.json               交给执行者的最小任务
  run.json                状态及实际环境记录
eval-1/without_skill/run-1/
benchmark.json            summarize 生成
report.md                 summarize 生成
feedback.json             真实人工评审后由协调者记录
```

脚本不会覆盖已有 iteration。用例 ID 为正整数或只含字母、数字、连字符、下划线的字符串，且字符串化后不能重复。附件路径默认相对目标技能根目录（即便 `--evals` 在别处），必须是目录内存在的文件；外部绝对路径、越界路径或越界链接要求先显式导入技能内 fixture 并调整用例副本，不静默猜路径。

`prompt` 中的附件别名不必等于 `files` 中的路径。任务中同时提供原文与 `input_map`；例如唯一 CSV 可以清楚对应。多个附件无法对应时先澄清或补映射，不能自己选一个。两组都保留原 prompt，通过同一规则解析附件副本。

快照仅复制技能内部内容（省略 `.git` 和 `__pycache__`），不跟随符号链接；遇到链接明确报错以避免漏复制或越界。需要链接资源时先将所需真实内容整理成独立测试副本。哈希用于追溯本轮读取的内容，不宣称文件系统已做不可变保护；运行后若快照变更，本轮应标为不可比。

## 调用执行者

读取 `task.json`，用宿主的实际运行能力执行其中的原始任务。`skill_path` 为 `null` 时不用目标技能；否则读取指定快照中的 SKILL.md 并按需使用资源。只能往该运行目录输出，附件副本允许修改，技能快照只读。执行日志中记录实际输出路径。协调者应核实产物存在，而不只接受“我做完了”的回复。

独立上下文运行的启动方式由宿主决定，以下只是传入内容形状，不是某个 API：

```json
{
  "prompt": "统计销售额并生成图表",
  "skill_path": "/workspace/iteration-1/snapshots/with_skill",
  "input_map": {"evals/files/sales.csv": "/workspace/iteration-1/eval-1/with_skill/run-1/inputs/evals/files/sales.csv"},
  "output_dir": "/workspace/iteration-1/eval-1/with_skill/run-1/outputs"
}
```

评分材料不能传给执行者。技能快照本身可能包含 evals：运行器应限制读取评测材料，执行者不得访问它们。若宿主不能限制并且轨迹不能排除读取，标记受限；不要通过要求执行者“不要看”便声称达到了强沙箱隔离。

## 保存完成状态

初始 `run.json` 为 `pending`。实际执行后由协调者核实并更新，例如：

```json
{
  "status": "completed",
  "environment": {
    "model": "实际模型标识",
    "settings": "实际推理/预算配置",
    "tools": ["实际工具集合"],
    "isolation": "verified",
    "isolation_evidence": "独立会话标识、加载检查和访问限制的实际证据",
    "comparison_key": "同模型、配置、工具、预算及输入策略的稳定标识"
  },
  "limitations": [],
  "error": null
}
```

`isolation` 只用 `verified` / `limited` / `unknown`；没有证据不得填 verified。`comparison_key` 需由实际环境产生，不能为了得到 delta 强行填相同值；汇总器还会比较两组 model/settings/tools。网络变化、跨组污染或无法冻结的输入会影响对比时，把原因放入 `limitations`，本脚本保守排除该配对。非可比性相关备注放执行日志。

`timing.json` 示例：`{"total_tokens": null, "duration_ms": 1200, "source": "宿主返回的耗时；token 未提供"}`。数值必须是非负实数（tokens 为整数），缺失用 null。计时口径两组一致；排队时间与模型执行时间不要混算。

`grading.json`：

```json
{
  "assertion_results": [
    {"text": "生成合法 JSON", "passed": true, "evidence": "outputs/result.json 通过 json.load 解析"},
    {"text": "图表包含轴标签", "passed": null, "evidence": "当前无法打开图片，待视觉复核"}
  ]
}
```

每条冻结断言按原顺序出现且只能出现一次。不采信自行填写的 summary，汇总器重新计数。`passed=null` 或无断言时不输出总体通过率；用已判定的少量结果充当满覆盖分数会误导比较。失败运行保留诊断但不拿部分产物计算成功率。

## 汇总口径

- 所有计划运行均计数。已完成但缺少评分的记入 ungraded；损坏 JSON 或结构错误进入 errors，不能默默跳过后宣布全量成功。
- 每组展示可完整评分的断言 passed/total 和通过率；这只是该组可评分样本的描述，不能和另一组不同覆盖的分数直接相减。
- delta 仅使用相同 case/repeat、两组 completed、断言完整、隔离 verified 且有证据、环境一致且无可比性限制的配对。先合计各组这些配对的 passed/total，再算候选减基线。报告配对数量。
- token/耗时的 delta 只使用指标两侧均存在的可比配对，并分别记录样本数，不能让缺测两侧错位。
- 每个 case/config 的运行通过率样本达到两个才计算样本标准差，不把不同任务混在一起计算“稳定性”。

恢复时读取 manifest 和现有 run 状态，只执行 pending；blocked 在前提解决后才续跑。已失败需重试时新建 iteration。不要覆盖已有成功产物。汇总可重复生成，修改之前保留用户手写的报告批注到单独反馈文件。
