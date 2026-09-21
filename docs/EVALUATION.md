# Evaluation

## Router Regression

```text
21 / 21 passed
```

覆盖：

- Direct
- Fast Path
- Workflow
- ReAct
- 中文 / 英文
- 多轮上下文
- Open WebUI background task

## Live Agent Evaluation

```text
10 / 10 core cases passed
```

当前本地测试：

| Metric | Result |
| --- | ---: |
| P50 Latency | 429.25 ms |
| Average Latency | 1526.11 ms |
| P95 Latency | 7139.41 ms |

当前样本量较小，因此该数据主要用于项目回归，而不是通用 Agent Benchmark。

## Repository Debugging

| Architecture | Result | Latency |
| --- | ---: | ---: |
| Free-form ReAct | FAIL | ~21.8 s |
| Semi-deterministic Workflow | PASS | ~5.9 s |

受控 Repo Debug Case 中约提升：

```text
3.69×
```

同时验证：

- 正确 Root Cause；
- 真实 Test Evidence；
- 报告真实落盘；
- 源码未被修改。