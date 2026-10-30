# 合成目标：word-contract

全部内容均为合成测试材料，不是本轮实测。两个规范来源均随目标提供，无法确定谁具有优先效力；没有用户确认记录。

## 目标 SKILL.md（来源 A）

```markdown
---
name: word-contract
description: 将一个非空小写英文单词转换为大写。
---

有效小写英文单词只输出对应的大写裸字符串；其他输入只输出 INVALID。不得输出 JSON。不需要外部工具。
```

## 关联 references/output-contract.md（来源 B）

文件日期晚于来源 A，标题为“当前输出约定”：相同输入须只输出 JSON，例如 apple 输出 {"value":"APPLE"}，非法输入输出 {"error":"INVALID"}。该材料没有声明替代来源 A，也无适用版本、审批或优先级记录。

## 现有 evals/evals.json

```json
{
  "skill_name": "word-contract",
  "evals": [
    {
      "id": 51,
      "prompt": "apple",
      "expected_output": "只输出 APPLE。",
      "files": [],
      "assertions": ["只输出裸字符串 APPLE。"],
      "user_tag": "normal-word"
    }
  ]
}
```

合成历史观察：输出为 {"value":"APPLE"}，与既有断言不一致。这一观察不能证明来源 B 已生效，也不能证明既有用例有 BUG。

本轮范围仅为 Case 51；其他分支不在本轮审查范围。可以保留本地副本及待决策报告，不应先替用户选择规范。
