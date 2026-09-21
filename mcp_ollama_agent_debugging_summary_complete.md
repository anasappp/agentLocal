# mcp-ollama-agent 项目调试问题总结

> 项目：`D:\programGithub\mcp-ollama-agent`  
> 环境：Windows + PyCharm + Python 3.13 + Ollama + Docker + Open WebUI + LangChain + MCP + ChromaDB  
> 当前主模型：`qwen2.5:3b`  
> 当前 Embedding：`nomic-embed-text`  
> 说明：本文仅记录本次调试中真实遇到、验证过的问题；尚未真正落地的方案会明确标注“待处理”。

---

## 1. PowerShell 无法激活 `.venv`

### 【问题概述】
执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

时被 PowerShell 执行策略拦截。

### 【根因分析】
不是虚拟环境损坏，而是 Windows PowerShell 默认策略可能禁止本地 `.ps1` 脚本运行。

### 【解决思路】
1. 仅调整当前用户执行策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

2. 重新打开 Terminal。
3. 再执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 【经验总结】
- Windows 下 venv 激活失败先查执行策略。
- 不要第一时间重建虚拟环境。
- 优先修改 `CurrentUser`，避免无必要影响全局。

---

## 2. Python 多版本混用

### 【问题概述】
本机存在多个 Python，`python`、`py`、PyCharm Interpreter 可能指向不同版本。

### 【根因分析】
Windows 下多个解释器可同时存在，项目实际要求 Python 3.13，但命令可能落到其他版本。

### 【解决思路】

```powershell
py -3.13 --version
python --version
where python
```

必要时：

```powershell
py -3.13 -m venv .venv
```

### 【经验总结】
- venv 创建版本、PyCharm Interpreter、Terminal Python 要统一确认。
- Windows 上指定版本时优先使用 `py -3.13`。

---

## 3. Ollama 模型默认占用系统盘

### 【问题概述】
需要把模型放到 D 盘，同时避免把本机绝对路径写进项目。

### 【根因分析】
模型存储位置属于机器环境配置，不适合硬编码到 Git 仓库。

### 【解决思路】

Windows 用户环境变量：

```text
OLLAMA_MODELS=D:\ollamaholder\Ollama\Models
```

项目 `.env` 仅保留模型名：

```env
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

确认：

```powershell
$env:OLLAMA_MODELS
ollama list
```

### 【经验总结】
- 机器路径放系统环境变量。
- 项目仓库保存逻辑配置，不保存个人绝对路径。

---

## 4. Python / LangChain 调 Ollama 返回 502

### 【问题概述】
Ollama 本身能访问，但 Python SDK 调：

```text
http://127.0.0.1:11434
```

出现 502。

### 【根因分析】
Python HTTP 客户端继承了系统代理，导致本地地址也被代理。

### 【解决思路】

临时验证：

```python
httpx.Client(trust_env=False)
```

长期配置：

```text
NO_PROXY=localhost,127.0.0.1
```

### 【经验总结】
- 本地服务 502 时先查代理。
- “浏览器正常、SDK 异常”很像代理继承问题。

---

## 5. Open WebUI Docker 端口混淆

### 【问题概述】
浏览器访问 `3000`，容器内部监听 `8080`。

### 【根因分析】
Docker 的 host port 与 container port 不是同一概念。

### 【解决思路】

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

确认：

```text
0.0.0.0:3000->8080/tcp
```

浏览器：

```text
http://127.0.0.1:3000
```

### 【经验总结】
排 Docker 问题时始终区分宿主机端口与容器端口。

---

## 6. MCP 多参数 StructuredTool 与小模型 ReAct 不稳定

### 【问题概述】
多个 MCP 参数直接暴露给 LangChain 后，Qwen2.5 3B 容易生成错误 JSON、错误字段或额外包裹层。

### 【根因分析】
文本式 ReAct 对小模型已经有格式要求，再叠加复杂 Tool schema 容易出错。

### 【解决思路】
把 MCP Adapter 统一为单字符串输入：

```python
class ToolInput(BaseModel):
    input: str
```

Adapter 再转换：

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

### 【经验总结】
- 小模型 Tool schema 越简单越稳定。
- 协议复杂度尽量下沉到 Adapter 层。

---

## 7. GitHub RAG ingest 触发匿名 API 403

### 【问题概述】
`scripts/ingest.py` 批量抓 GitHub 仓库时出现 403。

### 【根因分析】
匿名 GitHub API 配额不足，批量多仓库抓取很快触发 rate limit。

### 【解决思路】

`.env`：

```env
GITHUB_TOKEN=实际 token
```

`.env.example`：

```env
GITHUB_TOKEN=
```

请求头：

```python
headers["Authorization"] = f"Bearer {token}"
```

同时加入：
- timeout
- User-Agent
- 429 / 5xx retry
- exponential backoff

### 【经验总结】
- 批量 GitHub ingest 不应长期依赖匿名 API。
- Token 不能提交 Git。
- 外部采集必须设计 retry/backoff。

---

## 8. Chroma reset 没真正删除 collection

### 【问题概述】
重新 ingest 前清理旧向量库时，旧 collection 可能仍保留。

### 【根因分析】
仅清 Python 对象缓存，不等于删除持久化 collection。

### 【解决思路】
正确顺序：

```text
获取/初始化 vectorstore
→ 删除 collection
→ 清 Python 缓存引用
```

最终全量 ingest 已成功：

```text
5898 chunks
207 files
13 repos
```

### 【经验总结】
持久化向量数据与进程内缓存是两层状态，reset 要分别处理。

---

## 9. `code_exec` 执行裸表达式没有 stdout

### 【问题概述】

```python
12345 * 6789
```

脚本执行成功但没有输出。

### 【根因分析】
Python 脚本模式不会像 REPL 自动打印裸表达式结果。

### 【解决思路】

```python
tree = ast.parse(code)

if (
    len(tree.body) == 1
    and isinstance(tree.body[0], ast.Expr)
):
    expression = ast.unparse(tree.body[0].value)
    code = f"print(repr({expression}))"
```

### 【经验总结】
Tool 的“执行成功”与“有可消费结果”不同。计算类工具应保证 stdout。

---

## 10. `code_exec` 已成功但 ReAct 重复调用

### 【问题概述】
Tool 已返回正确结果，但小模型没有稳定输出 `Final Answer`，导致重复执行。

### 【根因分析】
问题在 ReAct 收尾 / parser，而不是计算本身。

### 【解决思路】

成功时直接返回 stdout：

```python
if name == "code_exec" and isinstance(data, dict):
    if data.get("returncode") == 0:
        stdout = str(data.get("stdout", "")).strip()
        if stdout:
            return stdout
```

并设置：

```python
return_direct=(name == "code_exec")
```

### 【经验总结】
- 精确最终结果 Tool 适合 `return_direct=True`。
- 遇到循环不要先加 `max_iterations`。

---

## 11. Tool 返回契约变化后测试仍按旧契约断言

### 【问题概述】
`code_exec` 改成纯 stdout 后，旧测试仍执行 `json.loads(result)`。

### 【根因分析】
实现已经变了，测试还在验证旧行为。

### 【解决思路】

```python
assert result == "hello"
assert tool.return_direct is True
```

并继续检查发送给 MCP 的 payload。

### 【经验总结】
接口契约一旦改变，实现和测试必须同步演进。

---

## 12. 多轮聊天历史没有传给 Agent

### 【问题概述】
早期 `/v1/chat/completions` 只保留当前最后一条 user message。

### 【根因分析】
完整 `messages` 收到了，但没有正确拆分当前 query 与历史。

### 【解决思路】

```python
query = req.messages[last_user_index].content
history_messages = req.messages[:last_user_index]
```

构建：

```python
conversation_messages = [
    {
        "role": message.role,
        "content": message.content,
    }
    for message in history_messages
]
```

### 【经验总结】
- 多轮历史应在 API 入口层保证完整。
- Direct Chat 最好保留原生 role/content。

---

## 13. 普通聊天也全部进入 ReAct

### 【问题概述】
问候、解释等无需 Tool 的请求也跑完整 Agent 链，导致慢且易出格式错误。

### 【根因分析】
初始架构只有：

```text
User → ReAct
```

没有 Router。

### 【解决思路】

```text
普通聊天 → Direct Chat
工具任务 → Tool 路径
```

### 【经验总结】
Agent 不等于所有消息都要 Agent 化。Direct Chat 是稳定性和延迟的重要优化。

---

## 14. Open WebUI 后台 title / follow-up / tags 误调用 Tool

### 【问题概述】
Open WebUI 会自动生成标题、追问、标签，其 prompt 内嵌聊天历史，曾把历史中的算术等内容再次识别为 Tool 请求。

### 【根因分析】
Router 没有先识别 Open WebUI 内部任务。

### 【解决思路】

```python
def _is_openwebui_internal_request(query: str) -> bool:
    q = query.lstrip().lower()

    if not q.startswith("### task:"):
        return False

    internal_tasks = [
        "generate a concise title",
        "suggest 3-5 relevant follow-up questions",
        "generate 1-3 broad tags",
    ]

    return any(task in q for task in internal_tasks)
```

最先路由：

```python
if _is_openwebui_internal_request(query):
    return await _run_direct_chat(...)
```

### 【经验总结】
UI 内部请求必须在业务 Router 之前隔离，否则聊天历史会造成假 Tool 调用。

---

## 15. 中文算术没有调用计算器

### 【问题概述】
英文 Tool 请求正常，但：

```text
777777乘以333等于多少
```

曾由模型直接心算并给错答案。

### 【根因分析】
Router 规则偏英文，中文工具表达覆盖不足。

### 【解决思路】

高精度中文规则：

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
中文自然语言要作为正式 Router 测试集，而不是英文逻辑的附属补丁。

---

## 16. `r"计算"` 误伤“计算机视觉 / 计算复杂度”

### 【问题概述】

```text
解释一下计算机视觉是什么
```

曾被判定为 `code_exec`。

### 【根因分析】
过宽规则：

```python
r"计算",
```

会命中大量非计算任务。

### 【解决思路】
删除裸 `r"计算"`，保留：
- `计算器`
- `算一下`
- `重新计算`
- 明确算术表达式

并做负样本：

```text
计算机视觉 → Direct
计算复杂度 → Direct
```

### 【经验总结】
Router 正则应优先精度；每个正样本规则都应配负样本。

---

## 17. 推断 Tool 被错误当成“用户显式要求 Tool”

### 【问题概述】
Router 推断了 `code_exec` 后，retry 逻辑把它当成用户明确要求，最终出现：

```text
requested tool code_exec was not executed
```

### 【根因分析】

```python
requested_tool = detected_tool
```

混淆了：
- inferred intent
- explicit request

### 【解决思路】

单独实现：

```python
def _get_explicit_tool_request(
    query: str,
    tool_names: list[str],
) -> str | None:
    ...
```

仅识别：
- `Use code_exec`
- `调用 code_exec`
- `用计算器`

然后：

```python
requested_tool = _get_explicit_tool_request(
    query,
    tool_names,
)
```

### 【经验总结】
Router 预测不能自动升级成用户硬约束，否则一次误判会被 retry 放大。

---

## 18. 多轮“再乘以11”缺少参数

### 【问题概述】

```text
66×99
再乘以11
```

第二句缺少第一个操作数。

### 【根因分析】
只看当前 query 无法恢复省略参数。

### 【解决思路】
从最近 assistant message 提取前一轮结果：

```python
numbers = re.findall(
    r"-?\d+(?:\.\d+)?",
    str(message.get("content", "")),
)
```

### 【经验总结】
多轮 Tool 要分清：
- intent recovery
- argument recovery

确定性上下文优先程序化恢复。

---

## 19. 简单确定 Tool 请求仍进入 ReAct，耗时过长

### 【问题概述】
即便已经知道 `code_exec / file_read / file_list`，仍让模型生成 Thought/Action。

### 【根因分析】
架构只有 Direct 与 ReAct，缺少确定性中间层。

### 【解决思路】
新增 Single-Tool Fast Path：

```python
_build_fast_tool_call(...)
```

直接：

```python
observation = await tool.ainvoke({
    "input": json.dumps(
        arguments,
        ensure_ascii=False,
    )
})
```

### 【经验总结】
已知 Tool + 已知参数时，不需要 LLM 再做一次决策。

---

## 20. 固定多 Tool 流程被交给 ReAct 后重复搜索

### 【问题概述】

```text
搜索 Python 最新版本
→ 把结果写进文件
```

小模型曾连续调用多次 `web_search`，没有继续 `file_write`。

### 【根因分析】
虽然是多 Tool，但执行图其实固定：

```text
web_search → file_write
```

无需模型规划。

### 【解决思路】
新增 Deterministic Workflow：

```python
_build_deterministic_workflow(query)
```

再直接：

```python
search_result = await _call_tool_raw(...)
content = _format_web_search_markdown(search_result)
write_result = await _call_tool_raw(...)
```

### 【经验总结】
“多 Tool”不等于“一定需要 Agent”。固定 DAG 应由代码编排。

---

## 21. 复杂 Multi-step Router 边界仍不完美

### 【问题概述】

```text
搜索 → 比较 → 总结 → 写文件
```

部分表达仍会被记成 `ambiguous file_write` 而不是明确 multi-step。

### 【根因分析】
`_is_multi_step_request()` 对“总结后写入”等中文表达覆盖不足。

### 【解决思路】
**当前暂未修改。**

后续可根据同时存在的工具意图判断：

```python
tool_intent_count = sum([
    has_web,
    has_write,
    has_read,
    has_rag,
])

return tool_intent_count >= 2
```

### 【经验总结】
这是分类精度问题，不是当前主链功能阻断问题，优先级应低于真实失败。

---

## 22. Web→Write 中搜索失败却仍继续写文件

### 【问题概述】
DuckDuckGo 返回：

```text
202 Ratelimit
```

但 Workflow 仍写入只有标题的空 Markdown，并告诉用户成功。

### 【根因分析】
程序只看 MCP HTTP 200，没有判断 Tool payload：

```json
{"error": "..."}
```

### 【解决思路】

```python
def _decode_tool_payload(observation):
    ...

def _tool_error_message(observation):
    payload = _decode_tool_payload(observation)

    if not payload:
        return None

    error = payload.get("error")

    if error:
        return str(error).strip()

    return None
```

Workflow 每一步都检查：

```python
search_error = _tool_error_message(search_result)

if search_error:
    return {
        "output": (
            "Web search failed, so the output "
            "file was not written."
        )
    }
```

### 【经验总结】
HTTP 成功不代表业务 Tool 成功；Workflow 每一步都要检查业务状态。

---

## 23. Web Fast Path 搜索失败后，LLM 仍编造答案

### 【问题概述】
`web_search` 已返回 error，但错误 JSON 仍被送入 Qwen 总结，模型曾生成不存在的 Python 版本。

### 【根因分析】
LLM synthesis 前缺少 error guard。

### 【解决思路】

```python
error = _tool_error_message(observation)

if error:
    return {
        "output": (
            f"Tool `{tool_name}` failed: {error}"
        )
    }
```

并检查：

```python
_web_search_has_results(observation)
```

### 【经验总结】
没有证据时应返回失败，不能把 error payload 当成知识交给模型。

---

## 24. DuckDuckGo `202 Ratelimit`

### 【问题概述】
当前搜索 Provider 有时：

```text
html backend → 202
lite backend → 202
```

### 【根因分析】
公共 DuckDuckGo backend 稳定性有限，存在限流。

### 【解决思路】
**错误传播已修复，但 Provider 稳定性仍待处理。**

后续应先检查当前 `duckduckgo_search` 版本实际支持的 API，再考虑：
- retry
- exponential backoff
- backend fallback
- 备用 Provider
- cache

### 【经验总结】
外部免费搜索源不能当成强 SLA 服务；先保证正确失败，再设计重试。

---

## 25. 中文“再读取刚才那个文件”没有重新调用 `file_read`

### 【问题概述】
第一轮读取成功，第二轮：

```text
再读取刚才那个文件
```

曾掉入 Direct Chat。

### 【根因分析】
旧 contextual Router 依赖历史里包含“文件”等字样，不能可靠恢复具体 path。

### 【解决思路】

```python
def _find_recent_file_path(
    conversation_messages,
) -> str | None:
    ...
```

原则：
- 最近相关消息只有一个文件名 → 返回
- 同时出现多个文件名 → `None`，不猜

### 【经验总结】
“那个文件”是参数共指，不应完全交给 LLM 推理。

---

## 26. 英文 `Read restart_test.md` 没识别为 file_read

### 【问题概述】
中文显式读取正常，英文显式文件名读取曾走 Direct Chat。

### 【根因分析】
英文 regex 只覆盖 `read file`，没有覆盖 `read + filename`。

### 【解决思路】

```python
r"\b(?:read|open|show)\s+"
r"(?:the\s+)?"
r"(?:(?:contents?|content)\s+of\s+)?"
r"(?:file\s+)?"
r"[\w./\\-]+\."
r"(?:txt|md|json|ya?ml|csv|log|py|toml|ini)\b"
```

### 【经验总结】
文件意图测试要覆盖：
- read file
- read filename
- discuss filename（负样本）

---

## 27. “刚才的文件内容是什么”没有识别为读取

### 【问题概述】
Workflow 已写文件，但：

```text
刚才的文件内容是什么
```

曾走 Direct Chat。

### 【根因分析】
只覆盖“读取 / 打开”命令型表达，没有覆盖“内容是什么”问句型表达。

### 【解决思路】

中文增加：

```python
r"刚才的文件内容"
r"刚才那个文件.*内容"
r"那个文件.*内容"
r"刚才保存的文件"
r"刚才写入的文件"
```

英文增加：

```python
r"\bwhat(?:'s| is| was) in that file\b"
r"\bshow (?:me )?that file(?:'s)? contents?\b"
```

### 【经验总结】
意图识别不能只测祈使句，还要测试自然问句。

---

## 28. PowerShell 中文测试变成 `????`

### 【问题概述】
在 PowerShell here-string 中传中文给 `python -`，测试结果出现乱码。

### 【根因分析】
Windows PowerShell → stdin → Python 的编码链不稳定。

### 【解决思路】
改用 ASCII-only + Unicode escape：

```python
query = "\u521a\u624d\u7684\u6587\u4ef6..."
```

并：

```powershell
python -X utf8 -
```

### 【经验总结】
只要输入已经变成 `????`，Router 的 True/False 测试就没有可信度。

---

## 29. Retrieval Query 混入“回答格式要求”

### 【问题概述】

```text
上网查 Python 最新稳定版本，
只根据搜索结果回答，
不要补充……
```

曾被整体塞给搜索 Tool。

RAG 同样出现：

```text
解释一下 GGUF，只使用检索结果……
```

### 【根因分析】
“检索主题”和“回答约束”没有分离。

### 【解决思路】

```python
def _clean_retrieval_query(
    query: str,
    tool_name: str,
) -> str:
    ...
```

目标：

```text
根据知识库解释一下 GGUF，只使用检索结果……
→ GGUF
```

```text
上网查一下 Python 最新稳定版本，只根据结果……
→ Python 最新稳定版本
```

### 【经验总结】
Retrieval Query 不等于 User Prompt。搜索主题与回答要求应拆开。

---

## 30. RAG 直接查询 `GGUF` 召回质量差

### 【问题概述】
`GGUF` 的 top results 大多只是“提到 GGUF”，例如：
- Copy GGUF
- codec GGUF
- Pre-converted GGUF
- Create GGUF

而不是“GGUF 是什么”。

### 【根因分析】
单词级缩写 query 太短，向量检索更容易召回“出现过该词”的 chunk，而不是定义型 chunk。

### 【解决思路】
做对照实验：

```text
GGUF
GGUF model format
GGUF model format llama.cpp
```

结果证明：
- `GGUF model format` 已能召回“GGUF 是现代格式、GGML 是旧格式”
- `GGUF model format llama.cpp` 第一条直接命中 llama.cpp 的 GGUF 模型文档

### 【经验总结】
短缩写 query 应先测试 query expansion，再考虑换 embedding、BM25、Hybrid Retrieval。

---

## 31. RAG Query Expansion

### 【问题概述】
知识库里有正确资料，但 `GGUF` 本身检索表达太弱。

### 【根因分析】
问题主要是 query 表达，而不是数据完全缺失。

### 【解决思路】

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
        "gguf": "GGUF model format llama.cpp",
        "gguf 是什么": "GGUF model format llama.cpp",
        "what is gguf": "GGUF model format llama.cpp",
        "what's gguf": "GGUF model format llama.cpp",
        "explain gguf": "GGUF model format llama.cpp",
    }

    return expansions.get(normalized, q)
```

接入：

```python
cleaned = _clean_retrieval_query(...)
expanded = _expand_rag_query(cleaned)
```

日志已验证：

```text
cleaned='GGUF'
expanded='GGUF model format llama.cpp'
```

### 【经验总结】
对已验证的缩写 / 专有名词，可以使用 deterministic expansion，不必额外调用 LLM 做 query rewrite。

---

## 32. RAG 回答明显改善，但仍缺可追踪 Grounding

### 【问题概述】
Query Expansion 后，GGUF 回答已从错误的“OpenVINO 预转换格式”改善为：
- 模型文件格式
- llama.cpp 使用
- `convert_*.py` 可转换

但最终 UI 仍没有：
- `[1][2]` 证据编号
- source/url 列表
- claim 到 source 的机械对应

### 【根因分析】
当前仍是：

```text
RAG JSON → 3B 普通总结
```

Prompt 说“不要编造”并不能提供严格可审计 grounding。

### 【解决思路】
**当前尚未落地，按本轮要求先不修改。**

建议下一步：

```text
RAG Result
→ 编号 Evidence
→ Grounded Synthesis
→ 每条事实引用 [n]
→ Sources 列 source + URL
→ 证据不足时明确说不足
```

建议 Evidence：

```text
[1]
Source: github/ggerganov/llama.cpp/docs/models.md
URL: ...
Content: ...

[2]
Source: ...
URL: ...
Content: ...
```

### 【经验总结】
RAG 必须分开评估：
- Retrieval relevance
- Synthesis faithfulness

“答案看起来正确”仍不等于可追踪、可验证。

---

## 33. Embedding context / options warning

### 【问题概述】
RAG 首次运行曾出现：

```text
num_ctx=8192
n_ctx_train=2048
```

以及部分无效 option warning。

### 【根因分析】
Embedding 模型可能继承了 chat model 的部分 options。

### 【解决思路】
**当前未处理。**

后续检查：
- `agent/rag.py`
- embedding 初始化参数
- Ollama options

### 【经验总结】
Chat Model 与 Embedding Model 的 generation/context 参数不应完全共用。

---

## 34. RAG 第一次查询冷启动慢

### 【问题概述】
第一次知识库请求明显比后续慢。

### 【根因分析】

```text
首次请求
→ 初始化 Chroma
→ 加载 nomic-embed-text
```

属于 lazy initialization。

### 【解决思路】
**当前未处理。**

后续可：
- Agent 启动时初始化 Chroma
- warm-up embedding model

### 【经验总结】
性能分析应区分 cold start 与 warm request。

---

## 35. Open WebUI 元数据任务仍占用主 3B 模型

### 【问题概述】
title / tags / follow-up 已不会误调 Tool，但仍会调用 `qwen2.5:3b`。

### 【根因分析】
当前只是：

```text
后台任务 → Direct Chat
```

并非：

```text
后台任务 → 小模型/程序逻辑
```

### 【解决思路】
**当前未处理。**

可考虑：
- 关闭部分 Open WebUI 自动元数据
- 使用更小模型
- 程序化生成简单元数据

### 【经验总结】
用户主请求已经 Fast Path，不代表整体 UX 不受 UI 后台模型调用影响。

---

## 36. 日志过长，关键 Agent 行为难定位

### 【问题概述】
Ollama/llama.cpp 的 slot、cache、sampler、timing 日志很多，容易淹没 Router 和 Tool 日志。

### 【根因分析】
当前仍处于调试阶段，日志级别较高。

### 【解决思路】
**稳定后处理。**

后续：
- 降低 Agent verbose
- 分离 Agent / MCP / Ollama 日志
- 增加 request id
- 降低底层模型 runtime 日志

### 【经验总结】
调试阶段先保留可观测性；稳定后再降噪。

---

# 当前架构

```text
Open WebUI Background Task
        ↓
    Direct Chat
    （禁止 Tool）

普通 User Request
        ↓
Intent / Context Router
        ↓
┌────────────────────────────────────────────┐
│ 普通聊天                                   │
│ → Direct Chat                              │
│                                            │
│ 单 Tool + 参数明确                         │
│ → Single-Tool Fast Path                    │
│                                            │
│ 多 Tool + 固定执行图                       │
│ → Deterministic Workflow Fast Path         │
│                                            │
│ 参数模糊 / 动态推理 / 分析规划              │
│ → ReAct                                    │
└────────────────────────────────────────────┘
```

当前 RAG：

```text
User Query
↓
Query Cleaner
↓
Deterministic Query Expansion
↓
Chroma Retrieval
↓
LLM Synthesis
```

---

# 已验证通过的主要能力

```text
Python 3.13 环境                        ✅
Ollama 本地模型                        ✅
D 盘模型目录                           ✅
NO_PROXY                               ✅
Open WebUI                             ✅
MCP Server                             ✅
GitHub RAG ingest                      ✅
ChromaDB                               ✅
code_exec 裸表达式                     ✅
code_exec return_direct                ✅
Direct Chat                            ✅
多轮 conversation history              ✅
Open WebUI 后台 Tool 隔离              ✅
中文常用 Tool Intent                  ✅
“计算机视觉” false positive 修复       ✅
Explicit Tool ≠ Inferred Tool          ✅
上下文数学 Fast Path                   ✅
file_list Fast Path                    ✅
file_read 中文/英文                    ✅
文件上下文指代恢复                     ✅
file_write Fast Path                   ✅
Web Fast Path error guard              ✅
固定 Web→Write Workflow                ✅
Workflow error guard                   ✅
Retrieval Query Cleaner                ✅
GGUF Query Expansion                   ✅
GGUF Retrieval 质量明显改善            ✅
```

---

# 当前尚未完全处理的问题

## P1
### Web Search Provider 稳定性
DuckDuckGo 仍会随机 `202 Ratelimit`。

## P1
### RAG Grounded Synthesis
检索已改善，但还缺 `[n]` 引用、source/url 和严格 evidence-only 生成。

## P2
### 复杂 Multi-step Router 边界
“比较 → 总结 → 写文件”等中文复杂表达分类仍可继续优化。

## P2
### Embedding 参数 warning
`num_ctx` / generation options 仍需清理。

## P2
### Open WebUI metadata 继续占主 3B 模型
功能正确，但会影响 GPU 与延迟。

## P3
### 日志降噪
稳定后再做。

---

# 可复用经验 / 避坑要点

1. **先定位是哪一层的问题**：UI、Router、Fast Path、Workflow、ReAct、Adapter、MCP Tool、Provider、RAG Retrieval、RAG Synthesis。
2. **确定性任务优先代码执行，不优先 Agent**。
3. **多 Tool 不等于一定需要 ReAct**；固定 DAG 用 deterministic workflow。
4. **HTTP 200 不等于 Tool 成功**；一定检查业务 payload。
5. **Error payload 不能送给 LLM 当资料总结**。
6. **Router 应优先高精度规则，避免裸词根正则**。
7. **Explicit request 与 inferred intent 必须分开**。
8. **多轮 Tool 的关键是参数共指解析**。
9. **Retrieval Query 与 Answer Instruction 必须拆开**。
10. **先检查 Retrieval，再判断是不是 LLM hallucination**。
11. **短缩写 query 先试 deterministic expansion，再考虑大改 RAG 基础设施**。
12. **Windows 中文测试必须排除 stdin 编码问题**。
13. **测试写文件时使用新文件名，避免旧状态掩盖失败**。
14. **不要用提高 `max_iterations` 掩盖 Agent 设计问题**。
15. **修改返回契约时同步修改测试**。
16. **UI 后台请求也要进入性能与路由测试范围**。

---

# 推荐后续调试顺序

```text
1. RAG Grounded Synthesis
↓
2. DuckDuckGo / Web Provider 稳定性
↓
3. Web Search Grounded Synthesis
↓
4. Multi-step Router 边界
↓
5. Embedding options / context warning
↓
6. Open WebUI metadata 轻量化
↓
7. 日志降噪
↓
8. 建立自动 Agent Eval
```

建议最终 Eval 指标：

```text
Routing Accuracy
Fast-Path Hit Rate
Workflow Hit Rate
Tool Call Count
Task Success Rate
Multi-turn Success Rate
Retrieval Relevance
Synthesis Faithfulness
Unsupported-Claim Rate
Latency
```
