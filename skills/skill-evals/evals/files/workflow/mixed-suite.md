# 合成目标：word-batch

全部内容均为合成材料，不是本轮实测。请在获准的输出目录建立目标副本，不修改本附件。

## 目标 SKILL.md

```markdown
---
name: word-batch
description: 将小写英文单词转换为大写，批量输入的处理方式尚未确定。
---

单个非空小写英文单词仅输出对应的大写形式，不添加解释或格式。无输入或输入不合法时只输出 INVALID。不需要文件、网络或其他工具。

一个请求含多个合法单词时，业务尚未决定逐个转换、只取第一个或拒绝；不能依据普通非法字符规则推断这个分支。
```

## 现有 evals/evals.json

```json
{
  "skill_name": "word-batch",
  "evals": [
    {
      "id": 61,
      "prompt": "apple",
      "expected_output": "只输出 apple。",
      "files": [],
      "assertions": ["只输出 apple。"],
      "user_tag": "normal-word"
    },
    {
      "id": 62,
      "prompt": "apple banana",
      "expected_output": "只输出 APPLE。",
      "files": [],
      "assertions": ["只输出第一个单词的大写 APPLE。"],
      "user_tag": "undecided-multiple-words"
    }
  ]
}
```

本轮范围仅为这两例，不扩展其他分支；用户尚未决定多个单词的处理方式。Case 61 的判断不依赖这项决定。请保留待确认用例的原输入、预期和断言，单列其待运行状态。
