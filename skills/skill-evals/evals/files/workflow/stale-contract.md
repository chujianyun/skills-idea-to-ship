# 合成目标：word-envelope v2

全部内容均为合成测试材料，不是本轮实测。请在获准的输出目录建立目标副本；不要修改此附件。

## 目标 SKILL.md（现行契约 v2）

```markdown
---
name: word-envelope
description: 将 JSON 中的小写英文单词转换为大写 JSON 结果。
---

只处理一个 JSON 对象。其 word 字段须为非空、仅含小写英文字母的字符串；有效时只输出 {"value":"对应大写单词"}，否则只输出 {"error":"INVALID"}。不添加 Markdown 或解释。不需要文件、网络或其他工具。

版本约定：v2 已生效并替代 v1。v1 的 text 输入字段改名为 word，含义不变；v1 的裸字符串结果已废弃，改为上述 JSON。text 不再作为 word 的别名。原正常转换与非法字符分支的业务含义不变。
```

## 现有 evals/evals.json（从 v1 沿用）

```json
{
  "skill_name": "word-envelope",
  "evals": [
    {
      "id": 41,
      "prompt": "{\"text\":\"apple\"}",
      "expected_output": "只输出 APPLE。",
      "files": [],
      "assertions": ["输出为裸字符串 APPLE，不使用 JSON。"],
      "user_tag": "normal-word"
    },
    {
      "id": 42,
      "prompt": "{\"text\":\"123\"}",
      "expected_output": "只输出 INVALID。",
      "files": [],
      "assertions": ["输出为裸字符串 INVALID，不使用 JSON。"],
      "user_tag": "invalid-characters"
    }
  ]
}
```

## 合成历史失败

旧轮次的 Case 41 输入为 {"text":"apple"}，观察输出为 {"error":"INVALID"}，裸字符串 APPLE 断言失败。Case 42 输出同为 {"error":"INVALID"}，裸字符串 INVALID 断言失败。

这是提供给诊断的历史观察，不是本轮运行日志。修复后的真实重跑不得冒称这些观察是本轮实测。

本轮只回归上述正常单词与非法字符两个分支，不新增用例；其他输入分支不在本轮审查范围。
