# mcp-ollama-agent 全量调试问题与解决方案复盘

> 项目路径：`D:\programGithub\mcp-ollama-agent`  
> 主要环境：Windows、PyCharm、Python 3.13、Ollama、Docker、Open WebUI、LangChain、MCP、ChromaDB  
> 当前核心模型：`qwen2.5:3b`  
> Embedding：`nomic-embed-text`  
> 当前架构：Direct Chat / Fast Path / Deterministic Workflow / ReAct + MCP Tools + RAG + Eval  
> 文档目标：复盘本项目从首次运行到秋招项目化过程中真实遇到的问题、旧实现思路、实际采用的修复办法，以及可复用经验。  
>
> **说明**：本文只记录本项目实际遇到、实际分析过或实际落地过的问题与方案。没有把未实施的设想写成“已解决事实”；仍未彻底处理的内容会明确标注。

---

# 一、环境与基础运行问题

## 1. PowerShell 无法激活 Python 虚拟环境

### 【问题概述】

项目初次运行时，在 Windows PowerShell 中执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

可能被 PowerShell 的执行策略拦截，导致虚拟环境无法正常激活。

这会进一步引发 Python 版本、依赖位置和 PyCharm Interpreter 不一致的问题。

### 【根因分析】

问题不是 `.venv` 本身损坏，而是 Windows PowerShell 默认可能禁止执行本地 `.ps1` 脚本。

未解决前的思路是直接执行虚拟环境激活脚本，但忽略了 Windows 的执行策略限制。

### 【解决思路】

实际采用的处理步骤：

1. 仅修改当前 Windows 用户的执行策略，而不是全局策略。

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

2. 重新打开 Terminal。
3. 再激活虚拟环境。

```powershell
.\.venv\Scripts\Activate.ps1
```

4. 确认 Terminal 前出现：

```text
(.venv)
```

### 【经验总结】

- Windows 上虚拟环境激活失败时，先查执行策略，不要第一时间删除 `.venv` 重建。
- 优先修改 `CurrentUser` 级别，避免不必要的系统级影响。
- 后续所有调试命令都应先确认 Terminal 已处于正确虚拟环境。

---

## 2. Python 多版本混用

### 【问题概述】

本机存在多个 Python，出现过：

- `python`
- `py`
- PyCharm Interpreter
- `.venv`

可能不是同一 Python 版本的情况。

项目最终稳定在 Python 3.13。

### 【根因分析】

Windows 可以同时安装多个解释器。旧思路是默认认为：

```powershell
python
```

一定指向项目想要的版本，但实际可能落到其他 Python。

### 【解决思路】

使用以下命令确认解释器：

```powershell
python --version
py -3.13 --version
where python
```

必要时显式创建：

```powershell
py -3.13 -m venv .venv
```

并在 PyCharm 中选择项目 `.venv` 解释器。

### 【经验总结】

一个 Python 项目至少要统一三处：

1. venv 创建版本；
2. PyCharm Interpreter；
3. Terminal 中实际执行的 Python。

不要只看其中一个。

---

## 3. Ollama 模型默认占用系统盘

### 【问题概述】

Ollama 默认模型目录会占用系统盘，但项目需要把大模型放到 D 盘，同时又不希望在仓库中写死本机绝对路径。

### 【根因分析】

旧思路容易把：

```text
D:\ollamaholder\Ollama\Models
```

直接放进项目配置。

这样虽然当前机器能运行，但会污染仓库，使项目无法在别人的机器上直接复用。

### 【解决思路】

把模型目录配置为 Windows 用户环境变量：

```text
OLLAMA_MODELS=D:\ollamaholder\Ollama\Models
```

项目 `.env` 只保存逻辑模型名：

```env
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

验证：

```powershell
$env:OLLAMA_MODELS
ollama list
```

### 【经验总结】

- 机器相关路径属于环境配置，不属于项目逻辑。
- Git 仓库中应保存“模型叫什么”，而不是“某个人电脑上模型放在哪里”。

---

## 4. Python / LangChain 调 Ollama 返回 502

### 【问题概述】

Ollama 服务本身可以访问，但 Python SDK 或 LangChain 调用：

```text
http://127.0.0.1:11434
```

出现 502。

### 【根因分析】

实际原因是 Python HTTP 客户端继承了系统代理设置，本地 `127.0.0.1` 请求也被送到了代理。

旧代码默认使用环境代理，没有显式排除 localhost。

### 【解决思路】

临时验证时可使用：

```python
httpx.Client(trust_env=False)
```

长期方案是设置：

```text
NO_PROXY=localhost,127.0.0.1
```

项目最终使用 Windows 用户级 `NO_PROXY`。

### 【经验总结】

当出现：

```text
浏览器 / curl 本地访问正常
Python SDK 访问本地服务异常
```

时，应优先检查代理，而不是怀疑 Ollama 模型损坏。

---

## 5. Open WebUI Docker 端口混淆

### 【问题概述】

Open WebUI 容器内部监听 8080，但浏览器访问 3000。

### 【根因分析】

旧排查时容易把：

```text
host port
```

和：

```text
container port
```

混为一谈。

### 【解决思路】

通过：

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

确认类似：

```text
0.0.0.0:3000->8080/tcp
```

浏览器访问：

```text
http://127.0.0.1:3000
```

### 【经验总结】

Docker 网络问题排查时始终区分：

```text
宿主机端口 → 容器内部端口
```

浏览器访问的是宿主机映射端口。

---

# 二、MCP Tool 与代码执行问题

## 6. MCP 多参数 StructuredTool 对 3B 小模型不稳定

### 【问题概述】

MCP Tool 原始参数较多，直接映射为复杂 StructuredTool 后，Qwen2.5 3B 在 ReAct 中容易：

- 输出错误 JSON；
- 参数字段名错误；
- 多包一层对象；
- Tool parser 失败。

### 【根因分析】

旧思路是：

```text
MCP Tool schema
→ 直接完整暴露给 LangChain / LLM
```

但小模型既要遵守 ReAct 文本协议，又要生成复杂参数结构，负担过高。

### 【解决思路】

实际采用了“单字符串 Tool Input”策略：

```python
class ToolInput(BaseModel):
    input: str
```

在 MCP Adapter 内再做：

```python
arguments = json.loads(input)

response = await client.post(
    "/call",
    json={
        "tool": name,
        "arguments": arguments,
    },
)
```

把协议复杂度放到 Adapter，而不是交给 3B 模型。

### 【经验总结】

小模型 Agent 的 Tool schema：

```text
越简单 → 越稳定
```

协议适配应该尽量下沉到代码层。

---

## 7. GitHub RAG ingest 触发 403

### 【问题概述】

`scripts/ingest.py` 批量读取 GitHub 仓库时触发匿名 API 限流，出现 403。

### 【根因分析】

旧实现依赖匿名 GitHub API，批量读取多个仓库和文件后很快达到匿名额度。

### 【解决思路】

`.env` 使用：

```env
GITHUB_TOKEN=真实 token
```

`.env.example` 保持：

```env
GITHUB_TOKEN=
```

请求中加入：

```python
headers["Authorization"] = f"Bearer {token}"
```

同时为外部请求加入：

- timeout；
- User-Agent；
- retry；
- exponential backoff。

最终全量 ingest 成功：

```text
5898 chunks
207 files
13 repos
```

### 【经验总结】

- 批量数据采集不能依赖匿名 API。
- Token 必须只放 `.env`，不能提交 Git。
- 外部 API 从一开始就应该有 retry / timeout / backoff。

---

## 8. Chroma reset 没有真正清空旧 collection

### 【问题概述】

重新构建知识库前，旧向量数据可能仍残留。

### 【根因分析】

旧实现只清理 Python 内存对象或缓存引用，但没有真正删除 Chroma 持久化 collection。

### 【解决思路】

实际调整为：

```text
获取 / 初始化 vectorstore
→ 删除 collection
→ 清理 Python 引用
→ 再 ingest
```

### 【经验总结】

持久化向量数据库至少包含两层状态：

```text
磁盘 / collection
+
Python 进程内对象
```

reset 必须同时考虑两层。

---

## 9. `code_exec` 执行裸表达式没有输出

### 【问题概述】

执行：

```python
12345 * 6789
```

返回成功，但 stdout 为空。

### 【根因分析】

旧代码按普通 Python 脚本执行。

脚本模式与 REPL 不同：

```python
12345 * 6789
```

只计算，不自动打印。

### 【解决思路】

对“单个裸表达式”做 AST 检查，并自动包装：

```python
tree = ast.parse(code)

if (
    len(tree.body) == 1
    and isinstance(tree.body[0], ast.Expr)
):
    expression = ast.unparse(
        tree.body[0].value
    )

    code = (
        f"print(repr({expression}))"
    )
```

最终验证：

```text
12345 * 6789
= 83810205
```

### 【经验总结】

Tool 的：

```text
执行成功
```

不等于：

```text
有可消费结果
```

计算类 Tool 必须保证最终结果进入 stdout。

---

## 10. `code_exec` 成功后 ReAct 重复调用 / 无法正确收尾

### 【问题概述】

早期 Tool 已经算出正确答案，但 3B 模型可能继续 Thought/Action，甚至重复调用 `code_exec`。

### 【根因分析】

旧架构是：

```text
所有 Tool 请求
→ ReAct
```

即使 Tool 已经返回精确最终答案，仍要求小模型自己生成 Final Answer。

小模型在 ReAct 收尾阶段容易 parser 失败或重复动作。

### 【解决思路】

第一阶段曾采用：

```python
return_direct=(name == "code_exec")
```

并且成功执行时 Adapter 直接返回 stdout。

这在当时有效解决了：

```text
精确计算
→ 重复 Tool Call
```

问题。

后续随着 Fast Path 出现，`return_direct` 又产生了新的多步任务冲突，见后文第 42 条。

### 【经验总结】

阶段性架构优化可能随着系统演进变成新的约束。

必须记录：

```text
这个设计当初解决了什么
现在为什么不再合适
```

而不是简单认为“旧代码错了”。

---

## 11. Tool 返回契约变化后测试仍验证旧行为

### 【问题概述】

`code_exec` 从完整 JSON payload 调整为成功时直接返回 stdout 后，旧测试仍：

```python
json.loads(result)
```

导致测试失败。

### 【根因分析】

实现契约已经变化，但测试没有同步更新。

### 【解决思路】

测试改为直接验证：

```python
assert result == "hello"
```

当时还检查了：

```python
assert tool.return_direct is True
```

后续架构再次调整为 `False` 时，又同步修改对应测试。

### 【经验总结】

测试不是永远不变的。

如果产品契约有意发生变化：

```text
实现
+
测试
+
文档
```

必须一起更新。

---

# 三、聊天历史、路由与 Fast Path

## 12. 多轮聊天历史没有正确传给 Agent

### 【问题概述】

早期 `/v1/chat/completions` 收到完整 `messages`，但 Agent 实际只使用最后一个 user query。

这导致：

- “再乘以 11”不知道前一轮结果；
- “再读刚才那个文件”不知道文件；
- 普通多轮聊天上下文丢失。

### 【根因分析】

旧实现相当于：

```text
messages
→ 只取最后一个 user
→ Agent
```

没有明确区分：

```text
current query
conversation history
```

### 【解决思路】

调整 API 入口：

```python
query = req.messages[
    last_user_index
].content

history_messages = (
    req.messages[:last_user_index]
)
```

再构建：

```python
conversation_messages = [
    {
        "role": message.role,
        "content": message.content,
    }
    for message in history_messages
]
```

Direct Chat 使用原始 role/content 历史。

### 【经验总结】

多轮上下文应该由 API 入口保证完整，不应该等 Tool 层再猜。

---

## 13. 所有请求都进入 ReAct，导致普通聊天慢且不稳定

### 【问题概述】

问候、解释概念等完全不需要 Tool 的请求，也进入 ReAct。

### 【根因分析】

旧架构只有：

```text
User → ReAct
```

没有 Router。

### 【解决思路】

新增 Direct Chat 分支：

```text
普通聊天
→ Direct Chat

工具请求
→ Tool 路径
```

后来继续演化为：

```text
Direct
Fast Path
Workflow
ReAct
```

四层执行架构。

### 【经验总结】

Agent 不意味着“每条消息都要 Agent 化”。

工具能力越多，越需要先判断：

```text
这条请求到底需不需要 Agent
```

---

## 14. Open WebUI 的 title / tags / follow-up 后台任务误触发 Tool

### 【问题概述】

Open WebUI 会额外发起：

- Generate title；
- Suggest follow-up questions；
- Generate tags。

这些 prompt 内嵌聊天历史，因此如果历史里有数学、文件名、GGUF 等词，Router 可能把后台任务误判成用户 Tool 请求。

### 【根因分析】

旧 Router 只看文本关键词，没有先判断请求是不是 Open WebUI internal task。

### 【解决思路】

增加优先级最高的后台任务检测：

```python
def _is_openwebui_internal_request(
    query: str,
) -> bool:
    q = query.lstrip().lower()

    if not q.startswith("### task:"):
        return False

    internal_tasks = [
        "generate a concise title",
        "suggest 3-5 relevant follow-up questions",
        "generate 1-3 broad tags",
    ]

    return any(
        task in q
        for task in internal_tasks
    )
```

最先路由：

```python
if _is_openwebui_internal_request(query):
    return await _run_direct_chat(...)
```

### 【经验总结】

UI 的“后台模型请求”和真实用户请求必须隔离。

否则历史文本会造成：

```text
假 Tool Call
```

---

## 15. 中文算术没有调用计算器

### 【问题概述】

英文显式 Tool 请求正常，但：

```text
777777乘以333等于多少
```

曾被模型直接心算，并给出错误结果。

### 【根因分析】

旧 Tool Router 偏英文。

中文自然表达没有覆盖：

- 乘以；
- 除以；
- 算一下；
- 重算；
- 计算器。

### 【解决思路】

补充高精度中文规则，例如：

```python
r"算一下"
r"算一算"
r"重新计算"
r"重算"
r"计算器"
r"\d+\s*乘以\s*\d+"
r"\d+\s*除以\s*\d+"
r"\d+\s*加上\s*\d+"
r"\d+\s*减去\s*\d+"
```

### 【经验总结】

中文不能只作为“英文 Router 的翻译补丁”。

中文真实表达应该是正式测试集的一部分。

---

## 16. `r"计算"` 误伤“计算机视觉 / 计算复杂度”

### 【问题概述】

增加中文 Tool Intent 后，过宽规则：

```python
r"计算"
```

让：

```text
解释一下计算机视觉是什么
计算复杂度是什么
```

也被误判为 `code_exec`。

### 【根因分析】

旧方案使用单个词根判断 intent，召回率高但精度很差。

### 【解决思路】

删除裸：

```python
r"计算"
```

保留：

```text
计算器
算一下
重新计算
明确数学表达式
```

同时加入负样本：

```text
计算机视觉 → Direct
计算复杂度 → Direct
```

### 【经验总结】

Router 的正则规则：

```text
优先精度
```

每加一个正样本规则，都应该考虑至少一个负样本。

---

## 17. 推断出的 Tool 被错误当成用户“显式要求 Tool”

### 【问题概述】

Router 只要推断出：

```text
code_exec
```

后续 retry 就认为用户明确要求 `code_exec`。

于是一次误分类可能被放大为：

```text
Error: requested tool code_exec was not executed.
```

### 【根因分析】

旧代码混淆了两种概念：

```text
inferred intent
explicit request
```

### 【解决思路】

单独实现：

```python
def _get_explicit_tool_request(
    query: str,
    tool_names: list[str],
) -> str | None:
    ...
```

只识别类似：

```text
Use code_exec
调用 code_exec
用计算器
```

而 Router 推断结果不再自动变成 hard constraint。

### 【经验总结】

推断和用户显式指令的语义强度不同。

不能把：

```text
“模型猜是”
```

升级为：

```text
“用户明确要求”
```

---

## 18. 多轮“再乘以 11”缺少第一个操作数

### 【问题概述】

对话：

```text
66 × 99
再乘以 11
```

第二句本身没有完整表达式。

### 【根因分析】

旧 Fast Path 只解析当前 query。

当前 query 中无法直接恢复：

```text
前一轮结果
```

### 【解决思路】

从最近 assistant message 提取可用数值：

```python
numbers = re.findall(
    r"-?\d+(?:\.\d+)?",
    str(
        message.get(
            "content",
            "",
        )
    ),
)
```

再结合当前操作构造完整参数。

### 【经验总结】

多轮 Tool 分成两个问题：

1. intent recovery；
2. argument recovery。

不要把它们混成一个“上下文理解问题”。

---

## 19. 简单、确定性的 Tool 仍走 ReAct，响应太慢

### 【问题概述】

即使 Router 已经明确：

```text
code_exec
file_read
file_list
```

仍然让 3B 生成：

```text
Thought
Action
Action Input
```

耗时高，而且增加 parser 风险。

### 【根因分析】

旧架构只有：

```text
Direct
ReAct
```

缺少中间的确定性执行层。

### 【解决思路】

新增 Single-Tool Fast Path：

```python
_build_fast_tool_call(...)
```

当：

```text
Tool 已知
+
参数可确定
```

时直接执行：

```python
observation = await tool.ainvoke({
    "input": json.dumps(
        arguments,
        ensure_ascii=False,
    )
})
```

### 【经验总结】

如果 Tool 和参数都已经确定：

```text
不要再用 LLM 做一次决策
```

这是降低 Agent 延迟最有效的方法之一。

---

## 20. 固定多 Tool 流程被交给 ReAct 后出现重复搜索

### 【问题概述】

任务：

```text
搜索 Python 最新版本
→ 把结果写入文件
```

自由 ReAct 会：

- 多次搜索；
- 忘记写文件；
- 重复 Thought。

### 【根因分析】

虽然这是多 Tool，但执行图完全确定：

```text
web_search
→ file_write
```

旧思路错误地认为：

```text
多 Tool = 必须 Agent 规划
```

### 【解决思路】

增加 Deterministic Workflow：

```python
_build_deterministic_workflow(query)
```

Runtime 按固定顺序执行：

```text
web_search
→ format
→ file_write
```

### 【经验总结】

多 Tool 不等于 Agent。

如果执行图固定，应该用：

```text
Workflow / DAG
```

而不是让模型自由规划。

---

## 21. 复杂 multi-step Router 边界仍不完全稳定

### 【问题概述】

类似：

```text
搜索 → 比较 → 总结 → 写文件
```

的复杂表达，部分情况下仍可能落入某个单 Tool intent，而不是稳定识别为开放多步任务。

### 【根因分析】

当前 `_is_multi_step_request()` 主要依赖规则匹配，对复杂中文组合表达覆盖有限。

### 【解决思路】

本项目中没有继续大规模扩正则。

原因是秋招项目后期决定：

```text
核心链路稳定优先
边缘表达不无限调参
```

对固定流程用 Workflow，对真正开放任务保留 ReAct。

### 【经验总结】

不要为了追求 100% 自然语言覆盖，把 Router 变成不可维护的正则集合。

边界 case 可以作为 Known Limitation。

---

# 四、文件、多轮上下文与结果传递问题

## 22. 中文“再读取刚才那个文件”无法恢复文件名

### 【问题概述】

第一轮已经读取某文件，第二轮说：

```text
再读取刚才那个文件
```

曾进入 Direct Chat 或无法构造 file_read 参数。

### 【根因分析】

旧 contextual Router 只判断：

```text
这句话像不像读文件
```

但没有解决：

```text
“那个文件”具体是哪一个
```

### 【解决思路】

实现最近文件路径恢复：

```python
_find_recent_file_path(
    conversation_messages
)
```

策略：

```text
最近上下文只有一个候选文件
→ 使用

有多个候选
→ 不猜
```

### 【经验总结】

“那个文件”是：

```text
参数共指问题
```

而不是单纯 Tool intent 问题。

---

## 23. 英文 `Read restart_test.md` 没识别为 file_read

### 【问题概述】

中文显式文件读取已经可以工作，但：

```text
Read restart_test.md
```

曾被 Direct Chat 处理。

### 【根因分析】

旧英文 regex 偏向：

```text
read file
```

没有覆盖：

```text
read + filename
```

### 【解决思路】

补充匹配：

```python
r"\b(?:read|open|show)\s+"
r"(?:the\s+)?"
r"(?:(?:contents?|content)\s+of\s+)?"
r"(?:file\s+)?"
r"[\w./\\-]+\."
r"(?:txt|md|json|ya?ml|csv|log|py|toml|ini)\b"
```

### 【经验总结】

文件意图测试至少要有：

```text
read file
read filename
read that file again
discuss filename（负样本）
```

---

## 24. “刚才的文件内容是什么”不是命令式表达，旧 Router 不识别

### 【问题概述】

类似：

```text
刚才那个文件里写了什么？
What was in that file?
```

并不是“读取文件”的命令形式。

### 【根因分析】

旧规则主要覆盖：

```text
读取
打开
read
open
```

没有覆盖问句型意图。

### 【解决思路】

加入：

```python
r"刚才的文件内容"
r"刚才那个文件.*内容"
r"那个文件.*内容"
r"刚才保存的文件"
```

英文：

```python
r"\bwhat(?:'s| is| was) in that file\b"
r"\bshow (?:me )?that file(?:'s)? contents?\b"
```

### 【经验总结】

Intent 测试不要只用祈使句。

真实用户会大量使用：

```text
疑问句
省略句
指代句
```

---

## 25. file_read 已调用成功，但 UI 曾显示上一轮 Web Search 内容

### 【问题概述】

一次多轮测试中，日志显示：

```text
Fast Path: file_read
Tool call: file_read
```

但 Open WebUI 显示的却是此前 Python Web Search Results。

### 【根因分析】

当时属于 Tool output、历史上下文和后处理之间的结果传递不稳定。

旧链路中仍有较多 LLM 后处理 / recovery 逻辑，因此成功 Tool Observation 可能没有被稳定映射成最终用户响应。

### 【解决思路】

后续项目逐步统一：

```text
确定性 Tool
→ Fast Path
→ Tool 结果直接形成响应
```

并加强文件 follow-up 的 path 恢复，使 file_read 不再依赖模型从历史中自由解释。

### 【经验总结】

日志里的：

```text
Tool 调用成功
```

与：

```text
最终用户看到正确结果
```

是两个不同验收点。

端到端 Eval 必须覆盖 UI/API 最终输出，而不只是后台 Tool 日志。

---

# 五、Web Search、Workflow 与错误传播

## 26. Web→Write 中搜索失败仍继续写空文件

### 【问题概述】

DuckDuckGo 返回：

```text
202 Ratelimit
```

但旧 Workflow 仍继续：

```text
file_write
```

写入只有：

```markdown
# Web Search Results
```

的空文件，并向用户说“已完成”。

### 【根因分析】

旧代码只检查 MCP HTTP 是否返回 200。

但 MCP 的业务错误是：

```json
{
  "error": "..."
}
```

HTTP 仍可能是 200。

### 【解决思路】

新增业务错误解析：

```python
def _tool_error_message(
    observation,
):
    payload = _decode_tool_payload(
        observation
    )

    if not payload:
        return None

    error = payload.get("error")

    if error:
        return str(error).strip()

    return None
```

Workflow 每一步检查：

```python
search_error = _tool_error_message(
    search_result
)

if search_error:
    return {
        "output": (
            "Web search failed, "
            "so the output file "
            "was not written."
        )
    }
```

### 【经验总结】

```text
HTTP 200
```

不等于：

```text
业务成功
```

Agent Workflow 必须检查 Tool payload 的业务状态。

---

## 27. Web Search 失败后 LLM 仍根据错误 payload 编答案

### 【问题概述】

搜索 Tool 返回 error 后，旧链路仍把 observation 交给模型总结。

模型可能根据旧知识或猜测输出：

```text
Python 最新版本是……
```

即使搜索根本没成功。

### 【根因分析】

旧思路是：

```text
Tool observation
→ 无论是什么都交给 LLM
```

没有 fail-closed。

### 【解决思路】

在 LLM synthesis 前增加：

```python
error = _tool_error_message(
    observation
)

if error:
    return {
        "output": (
            f"Tool `{tool_name}` failed: "
            f"{error}"
        )
    }
```

同时检查：

```python
_web_search_has_results(...)
```

### 【经验总结】

外部证据获取失败时：

```text
宁可明确失败
也不要让模型补全
```

尤其是“只根据搜索结果回答”的任务。

---

## 28. DuckDuckGo `202 Ratelimit`

### 【问题概述】

项目当前使用的 DuckDuckGo backend 偶发：

```text
html backend → 202
lite backend → 202
```

### 【根因分析】

这是外部 Provider 稳定性问题，不是 Agent 内部逻辑问题。

### 【解决思路】

项目已经完成两件事：

1. Tool error 正确传播；
2. 外部 Provider case 不再影响核心 Live Eval 指标。

Live Eval 中外部 case 使用：

```json
{
  "external": true
}
```

核心指标只统计内部可控任务。

Provider 本身的 retry / fallback 没有在本轮继续深改。

### 【经验总结】

免费搜索源不应视为强 SLA 服务。

评测时应分开：

```text
Agent 自身能力
外部 Provider 可用性
```

---

# 六、RAG 检索与答案可信度

## 29. Retrieval Query 混入大量“回答要求”

### 【问题概述】

例如：

```text
上网查一下 Python 最新稳定版本，
只根据搜索结果告诉我版本号和官方来源，
搜索结果里没有的信息不要补充。
```

旧代码可能把整句话作为 query。

RAG 同样出现：

```text
根据知识库解释一下 GGUF，只使用检索结果里明确出现的信息
```

### 【根因分析】

旧设计没有区分：

```text
Retrieval Query
Answer Instruction
```

### 【解决思路】

新增：

```python
_clean_retrieval_query(
    query,
    tool_name,
)
```

将：

```text
根据知识库解释一下 GGUF，只使用……
```

清洗为：

```text
GGUF
```

### 【经验总结】

用于搜索的 query 不应该等于用户完整 prompt。

应该拆成：

```text
找什么
+
怎么回答
```

---

## 30. 直接查询 `GGUF` 的 RAG 召回质量差

### 【问题概述】

最初知识库查询：

```text
GGUF
```

召回很多只是“出现 GGUF 这个词”的 chunk，例如：

- Copy resulting GGUF；
- codec GGUF；
- pre-converted GGUF。

最终回答曾错误地描述为：

```text
用于 OpenVINO 后端的预转换格式
```

### 【根因分析】

缩写 query 太短。

向量检索更容易找：

```text
包含这个 token
```

而不是：

```text
解释这个概念
```

### 【解决思路】

实际做了对照：

```text
GGUF
GGUF model format
GGUF model format llama.cpp
```

发现：

```text
GGUF model format llama.cpp
```

明显更容易召回定义型文档。

### 【经验总结】

短缩写的 Retrieval 问题，先检查：

```text
query 表达
```

不要马上归因于 Embedding 模型不够好。

---

## 31. 为 GGUF 增加 deterministic Query Expansion

### 【问题概述】

知识库本身有正确资料，但 query 太弱。

### 【根因分析】

旧 Retrieval 直接使用清洗后的：

```text
GGUF
```

没有扩展语义。

### 【解决思路】

加入：

```python
def _expand_rag_query(
    query: str,
) -> str:
    q = query.strip()

    normalized = re.sub(
        r"\s+",
        " ",
        q.lower(),
    ).strip(
        " \t\r\n?？。.!！"
    )

    expansions = {
        "gguf":
            "GGUF model format llama.cpp",

        "gguf 是什么":
            "GGUF model format llama.cpp",

        "what is gguf":
            "GGUF model format llama.cpp",

        "explain gguf":
            "GGUF model format llama.cpp",
    }

    return expansions.get(
        normalized,
        q,
    )
```

日志验证：

```text
cleaned='GGUF'
expanded='GGUF model format llama.cpp'
```

### 【经验总结】

对于已经验证过的缩写 / 专有名词：

```text
deterministic expansion
```

比额外调用一次 LLM rewrite 更轻、更稳定。

---

## 32. RAG 回答改善后仍缺严格可追踪 Grounding

### 【问题概述】

GGUF 回答从错误内容改善为：

- 模型文件格式；
- llama.cpp 使用；
- `convert_*.py` 可转换。

但最终 UI 仍没有严格做到：

```text
[n] 引用
claim → source
source/url 列表
```

### 【根因分析】

当前架构仍是：

```text
Retrieval JSON
→ 普通 LLM synthesis
```

Prompt 要求“不编造”并不能机械保证 grounding。

### 【解决思路】

本轮没有继续落地完整 citation pipeline，因为项目进入秋招收口阶段。

保留的后续方案是：

```text
Retrieval
→ Numbered Evidence
→ Grounded Synthesis
→ 每条 claim 引用 [n]
→ Sources
```

### 【经验总结】

RAG 应拆成两个指标：

```text
Retrieval relevance
Synthesis faithfulness
```

答案“看起来正确”不等于“证据可审计”。

---

## 33. Embedding 模型 context / options warning

### 【问题概述】

首次 RAG 运行曾出现类似：

```text
num_ctx=8192
n_ctx_train=2048
```

以及 Embedding 不适用的 options warning。

### 【根因分析】

Chat Model 与 Embedding Model 部分参数可能共用了同一套 options。

### 【解决思路】

本项目中没有继续深改，因为没有阻断主链路。

问题被记录为 Known Limitation。

### 【经验总结】

Chat 和 Embedding 即使都通过 Ollama，也不是同一种调用语义。

配置不应完全复用。

---

## 34. RAG 首次请求冷启动明显较慢

### 【问题概述】

第一次 RAG 请求比后续请求慢很多。

### 【根因分析】

首次调用同时发生：

```text
初始化 Chroma
加载 embedding model
首次 embed
```

属于 lazy initialization。

### 【解决思路】

本轮没有为了秋招继续做 warm-up 优化。

Live Eval 中保留真实延迟，并明确区分：

```text
warm / cold
```

的分析意识。

### 【经验总结】

性能分析不能只看一个平均数。

至少要问：

```text
冷启动还是热请求？
模型耗时还是工具耗时？
```

---

# 七、PowerShell 与测试环境问题

## 35. PowerShell 中文 here-string / stdin 变成 `????`

### 【问题概述】

用 PowerShell 给 Python 或 API 发中文测试时，日志出现：

```text
66??7????
```

Router 因此错误走 Direct Chat。

### 【根因分析】

问题不是 Router，而是：

```text
PowerShell
→ stdin / JSON
→ Python / HTTP
```

编码链不稳定。

### 【解决思路】

采用两种方式：

### 方法 A：PowerShell 显式 UTF-8 bytes

```powershell
$json = $payload |
    ConvertTo-Json -Depth 5 -Compress

$utf8Body = (
    [System.Text.Encoding]::UTF8
).GetBytes(
    $json
)

Invoke-RestMethod `
    -ContentType `
    "application/json; charset=utf-8" `
    -Body $utf8Body
```

### 方法 B：直接用 Python `httpx`

```python
response = httpx.post(
    "http://127.0.0.1:8000/v1/chat/completions",
    json=payload,
)
```

另外 CLI 测试使用：

```powershell
python -X utf8 -
```

### 【经验总结】

如果中文输入已经变成：

```text
????
```

后面的 Router True/False 都没有意义。

先修测试输入编码，再判断业务逻辑。

---

## 36. 底层日志过多，关键 Agent 行为难定位

### 【问题概述】

Ollama / llama.cpp 会输出大量：

- slot；
- cache；
- sampler；
- timing。

容易淹没真正有价值的：

```text
Routing
Tool call
Action
Observation
```

### 【根因分析】

项目处于调试期，日志级别较高。

### 【解决思路】

调试期间没有直接全部关闭，而是人工重点关注：

```text
agent.main
agent.agent
mcp_server.server
```

稳定后再考虑日志降噪。

### 【经验总结】

开发期日志应该“可观测优先”，正式展示时再“降噪优先”。

---

# 八、自动化 Eval 建设问题

## 37. `python eval/run_router_eval.py` 找不到 `agent`

### 【问题概述】

创建 Router Eval 后运行：

```powershell
python eval\run_router_eval.py
```

出现：

```text
ModuleNotFoundError:
No module named 'agent'
```

### 【根因分析】

直接执行文件时，Python 入口目录是：

```text
eval/
```

项目根目录未按 package 方式进入 module path。

### 【解决思路】

新增空文件：

```text
eval/__init__.py
```

以后使用：

```powershell
python -m eval.run_router_eval
```

验证：

```powershell
python -c "import agent; import eval; print('imports ok')"
```

### 【经验总结】

项目内脚本需要 import 同级 package 时，优先：

```text
package + python -m
```

不要到处 `sys.path.append(...)`。

---

## 38. Live Eval 文件名 `live_case.json` / `live_cases.json` 不一致

### 【问题概述】

Runner 读取：

```python
live_cases.json
```

但实际文件创建为：

```text
live_case.json
```

因此：

```text
FileNotFoundError
```

### 【根因分析】

单纯的文件命名不一致，不是 Eval 逻辑问题。

### 【解决思路】

统一重命名：

```powershell
Rename-Item `
    .\eval\live_case.json `
    live_cases.json
```

再验证：

```powershell
python -m json.tool `
    eval\live_cases.json `
    > $null
```

### 【经验总结】

测试框架应把：

```text
配置路径
fixture 名
输出名
```

统一约定，避免因为文件名浪费调试时间。

---

## 39. Router Eval 与 Live Eval 的指标语义容易被误解

### 【问题概述】

最终结果：

```text
Router Eval: 21/21
Live Core Eval: 10/10
```

如果直接写：

```text
Agent Accuracy 100%
```

会夸大结论。

### 【根因分析】

这两个 Eval 都是自建核心回归集，不是公开通用 Benchmark。

### 【解决思路】

最终统一为更准确的表述：

```text
21/21 routing regression cases
10/10 core end-to-end cases
```

Live Eval 同时统计：

```text
Average latency
P50
P95
Category Success
```

### 【经验总结】

评测数字必须附带：

```text
样本范围
指标定义
测试环境
```

不要把内部回归集通过率包装成通用模型能力。

---

## 40. `Tokens = 0` 容易被误认为“零 Token 成本”

### 【问题概述】

Live Eval 报告中的 Tokens 一列都是：

```text
0
```

### 【根因分析】

OpenAI-compatible API 当前没有返回有效 usage 统计，或 runner 没拿到真实 total_tokens。

这个 0 不是“模型没有消耗 Token”。

### 【解决思路】

没有把该数字作为项目指标。

Dashboard 主要展示：

```text
Task Success
P50 / P95
Latency
```

### 【经验总结】

监控系统中：

```text
缺失值
```

绝不能解释为：

```text
真实值为 0
```

---

## 41. 小样本下 P95 被单个 RAG case 主导

### 【问题概述】

Live Eval：

```text
10 cases
P95 = 7139 ms
```

而最慢的 RAG 正好约 7139 ms。

### 【根因分析】

样本只有 10 条时，P95 实际上几乎等于最大值。

### 【解决思路】

Dashboard 明确增加说明：

```text
Small benchmark;
interpret cautiously.
```

简历不把 P95 当核心卖点，而优先使用：

```text
P50 ≈ 429 ms
```

并保留测试范围说明。

### 【经验总结】

百分位指标在小样本中很容易失真。

指标必须结合样本量解释。

---

# 九、Dashboard 生成问题

## 42. `Start-Process dashboard.html` 报“系统找不到文件”

### 【问题概述】

首次尝试打开 Dashboard：

```powershell
Start-Process .\eval\reports\dashboard.html
```

报文件不存在。

### 【根因分析】

当时只写了：

```text
generate_dashboard.py
```

但没有真正执行：

```powershell
python -m eval.generate_dashboard
```

所以 HTML 尚未生成。

### 【解决思路】

先执行：

```powershell
python -m py_compile `
    eval\generate_dashboard.py

python -m eval.generate_dashboard
```

再确认：

```powershell
Test-Path `
    .\eval\reports\dashboard.html
```

必须：

```text
True
```

最后：

```powershell
$dashboard = (
    Resolve-Path `
    .\eval\reports\dashboard.html
).Path

Start-Process $dashboard
```

### 【经验总结】

生成器代码存在不等于产物存在。

任何 artifact 流程都应：

```text
build
→ verify
→ open
```

---

## 43. Dashboard 修改后页面仍没有 Repo Debug 对比

### 【问题概述】

期望 Dashboard 增加：

- Repo Debug Workflow；
- ReAct vs Semi-deterministic Workflow；
- speedup。

但最终 HTML 仍只有旧的：

- Router Accuracy；
- Core Task Success；
- P50；
- Average；
- P95。

### 【根因分析】

排查后发现，提供检查的“完整 Dashboard 代码”其实是：

```text
dashboard.html
```

而不是：

```text
generate_dashboard.py
```

生成结果本身当然不会改变生成逻辑。

同时旧 generator 并没有正确把 Hero JSON 纳入最终 HTML。

### 【解决思路】

最终采用“完整覆盖 generator”的方式：

```text
eval/generate_dashboard.py
```

统一读取：

```python
ROUTER_REPORT
LIVE_REPORT
REACT_HERO_CANDIDATES
WORKFLOW_HERO_CANDIDATES
```

使用 fallback：

```python
def load_first_json(
    candidates,
):
    ...
```

并新增：

```text
Repo Debug Workflow card
Architecture Comparison table
Workflow speedup
```

生成后先用：

```powershell
Select-String `
  -Path .\eval\reports\dashboard.html `
  -Pattern `
  "Repository Debugging Architecture Comparison|Repo Debug Workflow|Semi-deterministic Workflow|Free-form ReAct"
```

确认 HTML 真的包含新内容，再打开浏览器。

### 【经验总结】

调试“生成结果不对”时要先分清：

```text
generator source
generated artifact
```

不要在生成物上修生成逻辑。

---

# 十、Repo Engineering Hero Demo 问题

## 44. `code_exec` 工作目录假设错误

### 【问题概述】

最初认为 `code_exec` 在：

```text
workspace/
```

执行，因此测试：

```python
Path(
    "hero_repo/test_calculator.py"
).exists()
```

返回 False。

### 【根因分析】

实际运行结果证明：

```text
cwd =
D:\programGithub\mcp-ollama-agent
```

因此真正存在的是：

```text
workspace/hero_repo/test_calculator.py
```

### 【解决思路】

通过直接 MCP 诊断：

```python
import os
from pathlib import Path

print(
    "cwd =",
    os.getcwd(),
)

print(
    Path(
        "workspace/hero_repo/"
        "test_calculator.py"
    ).exists()
)
```

确认 Tool 的 execution boundary。

### 【经验总结】

不要猜 Tool 的 cwd。

涉及相对路径时，第一步应打印：

```python
os.getcwd()
```

---

## 45. `runpy.run_path()` 导致同目录模块无法 import

### 【问题概述】

尝试：

```python
runpy.run_path(
    "workspace/hero_repo/"
    "test_calculator.py",
    run_name="__main__",
)
```

后，测试文件内部：

```python
from calculator import add
```

出现：

```text
ModuleNotFoundError:
No module named 'calculator'
```

### 【根因分析】

旧思路是“找到脚本路径就直接 `runpy`”。

但这和真实：

```powershell
python test_calculator.py
```

的模块搜索语义不同。

`runpy.run_path()` 没有自动把 `hero_repo` 当作正常脚本 cwd。

### 【解决思路】

改为真实子进程：

```python
result = subprocess.run(
    [
        sys.executable,
        "test_calculator.py",
    ],
    cwd="workspace/hero_repo",
    capture_output=True,
    text=True,
    timeout=20,
)
```

这样：

```python
from calculator import add
```

可以正常解析。

### 【经验总结】

Repo-level 测试应该尽量模拟真实运行方式。

不要为了“都在 Python 里”强行使用 `runpy`。

---

## 46. `code_exec return_direct=True` 与多步 ReAct 任务冲突

### 【问题概述】

旧 Hero Demo：

```text
file_read
→ code_exec
```

获得真实测试结果后，Agent 直接结束，没有机会继续：

```text
file_write
```

### 【根因分析】

早期为了修复“简单计算重复 Tool Call”，MCP Adapter 将：

```python
return_direct=(
    name == "code_exec"
)
```

设为 True。

这在旧架构下是合理的：

```text
简单数学
→ code_exec
→ 直接返回
```

但 Fast Path 出现后：

```text
简单计算的终止
```

已经由 Runtime 自己控制。

此时 `return_direct=True` 会破坏复杂 ReAct：

```text
code_exec 只是中间步骤
```

### 【解决思路】

将 Tool 改为：

```python
return_direct=False
```

并保留：

```text
Fast Path
→ Runtime 自己直接返回结果
```

新的职责划分：

```text
Tool
→ 只执行

Runtime
→ 决定是否结束
```

修改后重新验证简单数学仍走：

```text
Fast Path: code_exec
```

### 【经验总结】

终止策略最好属于 Runtime，而不是具体 Tool。

否则同一个 Tool 无法同时用于：

```text
单步任务
+
多步任务
```

---

## 47. ReAct iteration budget 不足以完成 Repo Debug 链

### 【问题概述】

Hero Demo 需要大约：

```text
file_list
file_read × 3
code_exec
file_write
```

旧执行预算过小会在写报告前结束。

### 【根因分析】

项目早期的 ReAct 更偏短任务，因此 iteration budget 较小。

Repo-level Workflow 明显更长。

### 【解决思路】

将：

```python
max_iterations
```

调整为：

```python
max_iterations=8
```

保留有限上限，不无限放大。

### 【经验总结】

`max_iterations` 应服务于任务复杂度。

但不能用：

```text
把 5 改成 50
```

来掩盖错误规划。

如果模型在乱调用 Tool，提高 iteration 只会让它乱得更久。

---

## 48. Free-form ReAct 在 Repo Debug 中调用无关 Tool

### 【问题概述】

自由 ReAct Hero Demo 曾出现：

```text
query_knowledge_base
web_search
```

甚至把本地：

```text
hero_repo/README.md
```

当成 Web Search query。

### 【根因分析】

旧思路是：

```text
复杂任务
→ 把所有 Tool 全部交给 ReAct
→ 模型自己规划
```

3B 模型面对很多 Tool 时容易：

- 误选工具；
- 多走无效步骤；
- 增加延迟。

### 【解决思路】

没有继续无限调 Prompt。

而是把这个 Case 改为：

```text
Semi-deterministic Repo Debug Workflow
```

由 Runtime 控制确定性步骤。

### 【经验总结】

小模型 Agent 中：

```text
工具越多
≠
能力越强
```

如果任务图已知，让模型自由选择只会增加搜索空间。

---

## 49. Free-form ReAct 最终报告生成了，但 Root Cause 归因错误

### 【问题概述】

在提高 iteration budget 后，自由 ReAct 已经能：

- 执行真实测试；
- 调用 file_write；
- 生成报告。

但它把根因写成：

```text
test_calculator.py 中的 add 有 bug
```

实际 bug 明明在：

```text
calculator.py
return a - b
```

Eval 输出：

```text
report_exists = true
structure_ok = true
evidence_ok = true
source_unchanged = true
diagnosis_ok = false
```

### 【根因分析】

旧 ReAct 同时负责：

```text
规划
工具选择
证据收集
根因推理
写报告
```

任务太长，且前面混入无关 Tool Call。

最终虽然掌握了 evidence，但根因定位仍出现语义错误。

### 【解决思路】

保留 `diagnosis_ok` 的严格检查，没有为了“让 Demo PASS”放宽断言。

随后把任务拆成：

```text
Runtime:
list/read/test/write

LLM:
root-cause reasoning only
```

### 【经验总结】

Eval 的价值不是“证明项目永远成功”。

真正有价值的是：

```text
Eval 能抓到模型口头正确但任务语义错误
```

不要为了通过率降低验收标准。

---

## 50. Agent 口头说“报告已生成”，但实际文件不存在

### 【问题概述】

一次 Hero Demo 中，Agent 最终回答中声称：

```text
诊断报告已经生成
```

但：

```powershell
Test-Path `
    .\workspace\hero_debug_report.md
```

返回 False。

### 【根因分析】

旧验收只看：

```text
Agent final answer
```

而不是环境状态。

LLM 很容易“描述它应该做的事”，但并没有真正执行副作用操作。

### 【解决思路】

Hero Eval 明确检查：

```python
report_exists = (
    REPORT_PATH.exists()
)
```

并把：

```text
环境真实状态
```

作为成功条件，而不是相信模型声明。

### 【经验总结】

Agent 评测一定要区分：

```text
said it
did it
```

有副作用的任务必须检查真实系统状态。

---

# 十一、Semi-deterministic Repo Debug Workflow

## 51. 自由 ReAct 不稳定，改为 Runtime 编排 + LLM 单点推理

### 【问题概述】

自由 ReAct Hero Demo 的问题包括：

- 无关 Tool Call；
- 延迟高；
- 曾提前停止；
- 曾口头说写文件但实际没写；
- 即使写了报告，也可能错误归因。

### 【根因分析】

旧思路是：

```text
复杂任务
→ 让 3B 自由规划完整执行链
```

但 Repo Debug 中大量步骤本身其实是确定的：

```text
列文件
读文件
跑测试
写报告
```

真正需要智能的只是：

```text
根据源码 + 测试结果判断 root cause
```

### 【解决思路】

新增：

```text
agent/repo_debug_workflow.py
```

整体结构：

```text
Runtime
├─ file_list
├─ file_read
├─ code_exec
│
↓
LLM Diagnose
│
↓
Runtime
└─ file_write
```

关键 Tool 调用函数：

```python
async def _call_tool(
    client,
    tool,
    arguments,
):
    response = await client.post(
        MCP_CALL_URL,
        json={
            "tool": tool,
            "arguments": arguments,
        },
    )

    response.raise_for_status()

    data = response.json()

    if (
        isinstance(data, dict)
        and data.get("error")
    ):
        raise RuntimeError(
            f"{tool} failed: "
            f"{data['error']}"
        )

    return data
```

LLM 只接收：

```text
source files
+
actual test output
```

并要求 JSON：

```json
{
  "root_cause_file": "...",
  "root_cause": "...",
  "evidence": "...",
  "recommended_fix": "..."
}
```

同时验证：

```python
root_cause_file = Path(
    diagnosis[
        "root_cause_file"
    ]
).name

if root_cause_file not in allowed_names:
    raise RuntimeError(...)
```

### 【经验总结】

本项目最终形成了一个核心设计原则：

```text
确定性执行
→ Runtime

不确定推理
→ LLM
```

这比“所有复杂任务都交给 ReAct”更稳定、更可解释。

---

## 52. Repo Debug Workflow 报告写入必须由 Runtime 保证

### 【问题概述】

自由 ReAct 中：

```text
file_write
```

是否执行取决于模型下一步是否规划到它。

### 【根因分析】

旧架构把“写报告”也当成模型决策。

但用户任务明确要求：

```text
最终必须生成文件
```

这不是一个需要推理的步骤。

### 【解决思路】

Workflow 在 diagnosis 后强制：

```python
report = _build_report(
    test_result=test_result,
    diagnosis=diagnosis,
)

write_result = await _call_tool(
    client,
    "file_write",
    {
        "path": report_path,
        "content": report,
    },
)
```

最终返回：

```python
{
    "test_result": test_result,
    "diagnosis": diagnosis,
    "write_result": write_result,
    "report_path": report_path,
}
```

### 【经验总结】

任务明确要求产生的副作用：

```text
保存文件
写数据库
提交结果
```

如果执行条件确定，就应该由 Runtime 保证，而不是让模型“记得去做”。

---

## 53. Workflow Eval 需要同时验证正确性和“不修改源码”

### 【问题概述】

Repo Debug 任务要求：

```text
只诊断
不要修改 calculator.py
```

如果只检查报告正确，无法证明 Agent 遵守执行边界。

### 【根因分析】

旧 Demo 更关注“能不能找到 Bug”，没有把约束遵循作为正式成功条件。

### 【解决思路】

`eval/run_repo_debug_workflow.py` 同时检查：

```python
report_exists
structure_ok
diagnosis_ok
evidence_ok
source_unchanged
```

其中：

```python
source_unchanged = (
    "return a - b"
    in source_text
)
```

只有全部为 True：

```python
success = all([
    report_exists,
    structure_ok,
    diagnosis_ok,
    evidence_ok,
    source_unchanged,
])
```

最终 Workflow 成功：

```text
Repo Debug Workflow: PASS
Latency: 5926.55 ms
```

### 【经验总结】

Agent Safety 不一定都是复杂权限系统。

最基本的安全性之一就是：

```text
有没有遵守“不要修改”这种执行边界
```

并且必须程序化验证。

---

# 十二、Dashboard 与项目化展示

## 54. Dashboard 最终需要展示架构优化，而不只是单次成功率

### 【问题概述】

早期 Dashboard 只有：

- Router Accuracy；
- Task Success；
- P50 / P95；
- Category Success。

不能直观体现：

```text
为什么 Semi-deterministic Workflow 比自由 ReAct 更好
```

### 【根因分析】

旧 Dashboard 是“指标展示”，缺少“架构决策对比”。

### 【解决思路】

最终 generator 增加：

```text
Free-form ReAct
vs
Semi-deterministic Workflow
```

并自动加载：

```python
REACT_HERO_CANDIDATES
WORKFLOW_HERO_CANDIDATES
```

计算：

```python
hero_speedup = (
    react_latency
    / workflow_latency
)
```

最终受控 Repo Debug Case：

```text
Free-form ReAct
→ FAIL
→ 约 21.8 s

Semi-deterministic Workflow
→ PASS
→ 约 5.9 s
```

约：

```text
3.69×
```

但 Dashboard 明确限定：

```text
in this controlled
repository-debugging task
```

### 【经验总结】

一个好的工程项目 Dashboard 不只是证明“我做出来了”。

还应该回答：

```text
架构调整前后发生了什么变化？
为什么这样设计？
```

---

# 十三、最终稳定架构

经过以上调试后，项目不再是简单的：

```text
LangChain + Ollama + MCP Demo
```

而演化为：

```text
User Request
    │
    ▼
Open WebUI Background Filter
    │
    ▼
Intent / Context Router
    │
    ├──────────────► Direct Chat
    │
    ├──────────────► Single-Tool Fast Path
    │
    ├──────────────► Deterministic Workflow
    │
    └──────────────► ReAct
                         │
                         ▼
                     MCP Tools
```

其中：

```text
简单且确定
→ Fast Path

固定多步执行图
→ Deterministic Workflow

真正开放式规划
→ ReAct
```

Repo Debug 又进一步形成：

```text
Runtime
│
├─ file_list
├─ file_read
├─ code_exec
│
▼
LLM Reasoning Node
│
▼
Runtime
└─ file_write
```

---

# 十四、当前经过验证的结果

## Router Eval

```text
21 / 21
100%
```

覆盖：

- Direct；
- Fast Path；
- Workflow；
- ReAct；
- Background task；
- 中文 / 英文；
- 多轮 context。

## Core Live Eval

```text
10 / 10
100%
```

当前测试环境：

```text
Average Latency ≈ 1526 ms
P50 ≈ 429 ms
P95 ≈ 7139 ms
```

其中 RAG 是主要长尾。

## Repo Debug Hero Case

自由 ReAct：

```text
FAIL
≈ 21.8 s
```

Semi-deterministic Workflow：

```text
PASS
≈ 5.9 s
```

受控 Repo Debug Case 上大约：

```text
3.69× faster
```

且：

```text
正确定位 calculator.py
保留真实 test evidence
成功生成 Markdown 报告
源码保持未修改
```

---

# 十五、尚未彻底解决 / 明确暂缓的问题

这些不是遗漏，而是项目收口时有意停止继续投入。

## 1. DuckDuckGo Provider 稳定性

仍可能出现：

```text
202 Ratelimit
```

内部已经做到：

```text
正确报错
不继续写空文件
不让模型编答案
外部 case 不污染核心 Eval
```

但没有继续建设多 Provider fallback。

## 2. RAG citation / strict grounding

Query Cleaner 和 Query Expansion 已完成。

但最终回答仍未实现严格：

```text
[n] claim citation
source/url mapping
```

## 3. Embedding option warning

没有阻断功能，因此暂缓。

## 4. Open WebUI metadata 仍占用主 3B 模型

已经隔离 Tool，但 title/tags/follow-up 仍会调用主模型。

## 5. Token usage 没有可靠统计

Live Eval 的 `Tokens=0` 不作为真实成本指标。

## 6. Eval 样本仍是核心回归集而非公开通用 Benchmark

当前结果必须表述为：

```text
21/21 routing regression cases
10/10 core end-to-end cases
```

不能宣传为：

```text
通用 Agent 准确率 100%
```

---

# 十六、可复用经验 / 避坑要点

1. **先判断问题属于哪一层**  
   UI、Router、Fast Path、Workflow、ReAct、Adapter、MCP、Provider、Retrieval、Synthesis 不要混在一起排查。

2. **确定性任务不要默认走 Agent**  
   Tool 和参数都确定时直接执行。

3. **多 Tool 不等于一定需要 ReAct**  
   固定 DAG 应该 Runtime 编排。

4. **Tool 的职责是执行，Runtime 的职责是控制流程**  
   `return_direct` 这种终止语义不应轻易绑死在 Tool 层。

5. **HTTP 200 不等于业务成功**  
   永远检查 Tool payload。

6. **外部 Tool 失败时要 fail closed**  
   不要把 error payload 交给 LLM 继续“总结”。

7. **Router 优先高精度，不要贪召回率**  
   `r"计算"` 这种裸词根非常危险。

8. **Explicit Request 与 Inferred Intent 必须分开**  
   推断错误不能升级为用户硬约束。

9. **多轮 Tool 的真正难点常常是参数共指**  
   “那个文件”“再乘以 11”需要参数恢复。

10. **Retrieval Query 与 Answer Instruction 分离**  
    搜索主题越干净，召回通常越稳定。

11. **短缩写优先尝试 Query Expansion**  
    不要一遇到 RAG 不准就换模型、换数据库。

12. **先评 Retrieval，再评 Synthesis**  
    否则不知道 hallucination 来自哪一层。

13. **Windows 中文测试必须先排除编码污染**  
    `????` 状态下的业务测试没有意义。

14. **Agent 说“做完了”不等于真的做完了**  
    必须检查文件、数据库、外部系统的实际状态。

15. **Eval 不应该为了 PASS 而降低标准**  
    `diagnosis_ok=False` 正是 Eval 有价值的证据。

16. **测试失败要区分实现错误与 Eval assertion 错误**  
    不要看到红色就立刻改 Agent。

17. **小模型 Tool 越多，规划空间越大，错误率可能越高**  
    工具能力要通过 Runtime 组织，不是简单堆数量。

18. **Repo-level 任务尽量用真实运行语义**  
    `subprocess + cwd` 比 `runpy` 更接近真实工程测试。

19. **性能指标要结合样本量解释**  
    10 个 case 下的 P95 不能过度解读。

20. **外部 Provider 与核心 Agent 指标分开**  
    否则无法判断失败到底属于系统还是外部服务。

21. **生成器和生成物必须区分**  
    `generate_dashboard.py` 才是逻辑；`dashboard.html` 是产物。

22. **每次大改都保留回归资产**  
    Router Eval、Live Eval、Hero Eval 让架构修改不再靠感觉。

23. **性能优化最好有 Before / After**  
    本项目最终形成了自由 ReAct 与 Semi-deterministic Workflow 的真实对比。

24. **项目后期要停止无限 Debug**  
    核心链路稳定后，边缘 case 的收益远低于 README、架构图、Eval 和可展示 Demo。

---

# 十七、项目演进的核心脉络

本项目最重要的演进不是“加了多少 Tool”，而是执行控制权逐步从模型移回 Runtime：

```text
阶段 1
所有任务
→ ReAct

阶段 2
普通聊天
→ Direct
工具任务
→ ReAct

阶段 3
普通聊天
→ Direct
确定单 Tool
→ Fast Path
复杂任务
→ ReAct

阶段 4
普通聊天
→ Direct
单 Tool
→ Fast Path
固定多 Tool
→ Workflow
开放任务
→ ReAct

阶段 5
Repo Debug
→ Runtime 执行确定步骤
→ LLM 只负责 Root Cause Reasoning
→ Runtime 保证最终副作用
```

这也是本项目最终最值得复用的设计结论：

> **Agent 的价值不是让 LLM 控制一切，而是合理划分“确定性执行”与“智能推理”的边界。**
