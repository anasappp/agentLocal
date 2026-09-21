# LocalAgent Runtime Architecture

## 设计目标

项目主要解决小参数本地模型在 Tool Calling 场景中的三个问题：

1. 简单任务使用 ReAct 导致额外延迟；
2. 多 Tool 场景中自由规划容易产生无效调用；
3. LLM 声称任务完成不等于真实环境状态完成。

## 执行分层

```text
User Request
    │
    ▼
Intent / Context Router
    │
    ├── Direct Chat
    │
    ├── Fast Path
    │
    ├── Deterministic Workflow
    │
    └── ReAct
```

### Direct Chat

不需要 Tool 的普通问答直接调用 LLM。

### Fast Path

Tool 和参数可以确定时，Runtime 直接执行 MCP Tool。

### Deterministic Workflow

多 Tool 但执行图固定时，由 Runtime 编排执行顺序。

### ReAct

仅用于无法提前确定执行图的开放式任务。

## Semi-deterministic Repo Debug Workflow

```text
Runtime
├── file_list
├── file_read
├── code_exec
│
▼
LLM Root Cause Reasoning
│
▼
Runtime
└── file_write
```

核心原则：

> 确定性执行交给 Runtime，不确定性推理交给 LLM。