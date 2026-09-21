# mcp-ollama-agent 项目调试总结

> 项目路径：`D:\programGithub\mcp-ollama-agent`  
> 主要环境：Windows + PyCharm + Python 3.13 + Ollama + Docker + Open WebUI + LangChain + MCP + ChromaDB  
> 本文按本次实际调试顺序整理。当前按要求暂不继续修改“第二组复杂任务”的 Router 边界问题，仅记录现状和待办。

---

## 1. PowerShell 无法激活虚拟环境

### 【问题概述】

在 PyCharm / PowerShell 中执行虚拟环境激活脚本时被执行策略拦截：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 【根因分析】

Windows PowerShell 默认安全策略可能禁止本地脚本运行，因此 `Activate.ps1` 被拦截。这不是 Python 或项目代码损坏。

### 【解决方法】

1. 在 PowerShell 中调整当前用户执行策略。
2. 重新打开终端。
3. 再激活虚拟环境。

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 【经验总结】

- Windows 上 venv 激活失败先查 PowerShell policy。
- 尽量只改 `CurrentUser`，不要无必要改系统全局策略。

---

## 2. Python 3.9 / 3.13 解释器混用

### 【问题概述】

本机存在多个 Python 版本，项目需要 Python 3.13，但 `python`、`py`、PyCharm Interpreter 可能指向不同版本。

### 【根因分析】

Windows 多版本 Python 环境中，不同入口命令可能对应不同解释器，进而造成依赖、语法和 venv 不一致。

### 【解决方法】

```powershell
py -3.13 --version
python --version
where python
```

必要时明确创建 3.13 venv：

```powershell
py -3.13 -m venv .venv
```

### 【经验总结】

- Windows 多 Python 环境不要只看一个 `python --version`。
- PyCharm Interpreter、Terminal Python、系统 PATH 要分别确认。

---

## 3. Ollama 安装与模型目录迁移到 D 盘

### 【问题概述】

需要本地运行 `qwen2.5:3b`、`nomic-embed-text` 等模型，同时不希望模型占用系统盘。

### 【根因分析】

Ollama 默认模型目录不一定符合本机磁盘规划；如果在项目代码里硬编码模型目录，又会破坏可移植性。

### 【解决方法】

通过 Windows 用户环境变量配置：

```text
OLLAMA_MODELS=D:\ollamaholder\Ollama\Models
```

项目 `.env` 只保存模型名：

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

- 机器相关绝对路径放系统环境变量，不硬编码进仓库。
- 修改环境变量后需要重新打开终端 / PyCharm 才能继承。

---

## 4. Python / LangChain 调 Ollama 出现 502

### 【问题概述】

Ollama 服务本身正常，但 Python SDK / LangChain 请求 `127.0.0.1:11434` 时出现 502。

### 【根因分析】

Python HTTP 客户端继承了系统代理，本地请求也被送进代理。问题不在 Ollama，而在代理环境。

### 【解决方法】

先用：

```python
httpx.Client(trust_env=False)
```

验证本地 Ollama 可用。随后永久配置：

```text
NO_PROXY=localhost,127.0.0.1
```

重启 PyCharm / Terminal。

### 【经验总结】

- “浏览器可访问、本地 SDK 502”时优先检查代理。
- 本地服务应加入 `NO_PROXY`。

---

## 5. Open WebUI Docker 端口确认

### 【问题概述】

Open WebUI 容器内部端口与宿主机访问端口容易混淆。

### 【根因分析】

容器内部监听 8080，宿主机映射到 3000。

### 【解决方法】

浏览器使用：

```text
http://127.0.0.1:3000
```

### 【经验总结】

- Docker 排错必须区分 host port 和 container port。
- 未检查 compose 文件前，不要假设所有容器都由 compose 管理。

---

## 6. MCP 多参数 StructuredTool 与 ReAct 不稳定

### 【问题概述】

原 MCP Adapter 将多个 Tool 参数直接暴露给 LangChain `StructuredTool`，ReAct 在小模型下容易生成错误参数结构。

### 【根因分析】

文本式 ReAct 更适合单字符串 `Action Input`。多字段 schema 会增加小模型格式错误概率。

### 【解决方法】

统一所有 MCP Tool 为一个字符串参数 `input`，内部再 JSON decode：

```python
class ToolInput(BaseModel):
    input: str

async def _call(input: str):
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

- 小模型 + ReAct 下，统一单 JSON 字符串输入比多参数 StructuredTool 更稳。
- 协议适配应放在 Adapter 层完成。

---

## 7. GitHub RAG ingest 遇到匿名 API 403

### 【问题概述】

批量抓 GitHub 仓库时出现匿名 API rate limit / 403。

### 【根因分析】

匿名 GitHub API 配额过低，不适合一次抓多个 repo 和大量文件。

### 【解决方法】

`.env`：

```env
GITHUB_TOKEN=真实 token
```

`.env.example`：

```env
GITHUB_TOKEN=
```

请求时加入：

```python
headers["Authorization"] = f"Bearer {token}"
```

并增加：

- User-Agent
- timeout
- 429 / 5xx retry
- 指数退避
- 文件间短暂 sleep

最终 ingest 成功：

```text
5898 chunks from 207 files across 13 repos
```

### 【经验总结】

- 批量 GitHub 抓取不要依赖匿名额度。
- Token 必须放 `.env`，不要提交 Git。
- 网络采集要默认具备 retry/backoff。

---

## 8. Chroma reset 没有真正清空旧 collection

### 【问题概述】

重新 ingest 前调用 reset，但旧向量库不一定真正被删除。

### 【根因分析】

如果 cached vectorstore 尚未实例化，reset 可能只清 Python 引用，没有删除持久化 collection。

### 【解决方法】

1. 先实例化 / 获取 store。
2. 再删除 collection。
3. 最后清缓存变量。

### 【经验总结】

- 清 Python cache 不等于清持久化数据库。
- Vector DB reset 要显式确认 collection 是否真的删除。

---

## 9. `code_exec` 裸表达式没有 stdout

### 【问题概述】

执行：

```python
12345 * 6789
```

没有 stdout。

### 【根因分析】

Python 脚本模式不会像 REPL 那样自动打印裸表达式结果。

### 【解决方法】

在 `mcp_server/tools/code_exec.py` 中使用 AST；如果只有一个 expression，自动包装：

```python
tree = ast.parse(code)

if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
    expression = ast.unparse(tree.body[0].value)
    code = f"print(repr({expression}))"
```

最终得到：

```text
83810205
```

### 【经验总结】

- “执行成功”和“有 stdout”是两回事。
- Tool 返回契约要按 Agent 使用场景设计。

---

## 10. `code_exec` 成功后 ReAct 仍重复调用

### 【问题概述】

Tool 已返回正确计算结果，但 Qwen2.5 3B 没有稳定输出 `Final Answer:`，导致重复调用直到 max iterations。

### 【根因分析】

小模型对 ReAct 输出格式遵循不稳定；问题发生在 Tool 成功之后，而不是 Tool 本身。

### 【解决方法】

`mcp_adapter.py` 对成功 `code_exec` 返回纯 stdout：

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

- 精确结果 Tool 适合 `return_direct=True`。
- 遇到 Agent 循环不要先加 `max_iterations`，先判断循环发生在工具前还是工具后。

---

## 11. 修改 `code_exec` 返回契约后单元测试失败

### 【问题概述】

`pytest tests\test_mcp_adapter.py -v` 出现：

```text
1 failed, 7 passed
```

测试仍对 `result` 做 `json.loads()`，但新实现已经返回纯字符串 `hello`。

### 【根因分析】

实现契约已改变，测试仍验证旧行为。

### 【解决方法】

从：

```python
parsed_result = json.loads(result)
assert parsed_result["stdout"] == "hello\n"
```

改成：

```python
assert result == "hello"
assert tool.return_direct is True
```

同时继续断言请求 payload。

### 【经验总结】

- 接口契约改变后必须同步修改测试。
- 测试失败不一定说明实现错，也可能是测试仍基于旧设计。

---

## 12. Agent 没有正确保留多轮历史

### 【问题概述】

早期接口只取最后一条用户消息，多轮历史没有完整传入 Direct Chat / Agent。

### 【根因分析】

`agent/main.py` 没有把 OpenAI-compatible `messages` 完整拆分为当前 query 与历史。

### 【解决方法】

```python
query = req.messages[last_user_index].content
history_messages = req.messages[:last_user_index]
```

构建结构化历史：

```python
conversation_messages = [
    {
        "role": message.role,
        "content": message.content,
    }
    for message in history_messages
]
```

Direct Chat 使用原生 `SystemMessage / HumanMessage / AIMessage`。

### 【经验总结】

- 多轮聊天最好保留 role/content 结构，而不是全部拼成一段字符串。
- Direct Chat 与 ReAct 可分别保留适合自己的 history 格式。

---

## 13. 普通聊天也进入 ReAct，延迟和错误率过高

### 【问题概述】

普通问答也通过完整 ReAct Agent，导致 prompt 长、速度慢、小模型格式错误多。

### 【根因分析】

项目最初缺少 Tool Router。

### 【解决方法】

增加路由：

```text
普通聊天 → Direct Chat
明确工具意图 → Tool Agent
```

### 【经验总结】

- Agent 不应该等于“所有请求都走 ReAct”。
- Router 是降低延迟和提高稳定性的关键层。

---

## 14. Open WebUI 后台 title / follow-up / tags 误触发 Tool

### 【问题概述】

Open WebUI 会额外生成：

- title
- follow-up questions
- tags

这些请求内嵌聊天历史，导致 Router 看到历史里的“乘以”“搜索”等词后再次触发 Tool。

### 【根因分析】

Router 没有先识别 Open WebUI 内部任务。

### 【解决方法】

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

必须在 Tool Intent 判断之前：

```python
if _is_openwebui_internal_request(query):
    return direct_chat(...)
```

### 【经验总结】

- UI 会产生用户看不到的内部请求，Router 必须显式隔离。
- 不要把后台 prompt 内嵌的聊天历史当成当前用户意图。

---

## 15. 中文数学与常用中文 Tool 意图识别不足

### 【问题概述】

英文 `Use code_exec...` 能正常调用 Tool，但：

```text
777777乘以333等于多少
```

曾被 Direct Chat 错算；“调用计算器重算”也没有稳定映射到 `code_exec`。

### 【根因分析】

Router 主要围绕英文关键词设计，中文表达覆盖不足。

### 【解决方法】

统一 `_detect_tool_intent(query)`，中英文都映射到：

```text
code_exec
file_read
file_write
file_list
web_search
query_knowledge_base
```

示例：

```python
code_patterns = [
    r"\bcalculate\b",
    r"\bcompute\b",
    r"计算器",
    r"算一下",
    r"重新计算",
    r"\d+\s*乘以\s*\d+",
]
```

### 【经验总结】

- 多语言 Agent 不能只靠英文 tool name 驱动。
- Router、Tool retry 应共享同一套 intent detector。

---

## 16. Router 与 retry 使用不同意图规则

### 【问题概述】

可能出现：

```text
Router：知道要 code_exec
Retry：不知道用户明确要求了哪个 Tool
```

### 【根因分析】

`_should_use_tools()` 与 `_get_explicit_tool_request()` 分别维护规则。

### 【解决方法】

统一使用：

```python
detected = _detect_tool_intent(query)
```

例如：

```python
def _should_use_tools(query: str) -> bool:
    if _is_openwebui_internal_request(query):
        return False
    return _detect_tool_intent(query) is not None
```

### 【经验总结】

- 同一请求不要在多个函数里重复解析意图。
- Router、retry、policy 最好共享一个 canonical intent result。

---

## 17. “再乘以 11”等上下文 Tool 请求无法独立解析

### 【问题概述】

第二轮：

```text
再乘以11
```

缺少完整第一个操作数。

### 【根因分析】

基础 Router 只看当前 query，无法补全省略的上下文参数。

### 【解决方法】

新增：

```python
_detect_contextual_tool_intent(
    query,
    conversation_messages,
)
```

参数提取时从最近 assistant 结果找数字：

```python
numbers = re.findall(
    r"-?\d+(?:\.\d+)?",
    str(message.get("content", "")),
)
```

实际验证：

```text
66 × 99 = 6534
再乘以 11
→ 6534 * 11
→ 71874
```

### 【经验总结】

- Intent 识别和参数补全是两个层次。
- 多轮省略句需要上下文，但不应把无限历史全部送进 Router。

---

## 18. 简单确定性 Tool 请求仍经过完整 ReAct

### 【问题概述】

即使已经确定是 `file_read`、`file_list`、`code_exec`，仍要让模型生成 Thought / Action，导致慢且不稳定。

### 【根因分析】

架构只有：

```text
Direct Chat / ReAct
```

缺少 Fast Path。

### 【解决方法】

升级为：

```text
普通聊天 → Direct Chat
单 Tool + 参数明确 → Fast Path
复杂/模糊 → ReAct
```

增加：

```python
_build_fast_tool_call(...)
```

直接执行：

```python
observation = await tool.ainvoke({
    "input": json.dumps(
        arguments,
        ensure_ascii=False,
    )
})
```

### 【经验总结】

- Tool 与参数都已确定时，不需要让 LLM 再决定一次。
- Fast Path 能同时降低延迟、token 消耗和格式错误。

---

## 19. Fast Path 多轮 / 文件 / Web / RAG 全链路验证

### 【问题概述】

需要确认新 Fast Path 不只是单元测试通过，而是真实 Open WebUI → Agent → MCP 全链路正确。

### 【根因分析】

UI 答对并不能证明 Tool 真被调用，必须看后端日志。

### 【解决方法】

实际验证成功：

```text
Fast Path: code_exec
Fast Path: file_list
Fast Path: file_read
Fast Path: file_write
Fast Path: web_search
Fast Path: query_knowledge_base
```

### 【经验总结】

- Agent 修改必须做 runtime smoke test。
- 以服务端 `Tool call:` 为事实依据，不以模型口头声称为依据。

---

## 20. Web Search 检索正常，但 LLM synthesis 会加入工具结果没有的信息

### 【问题概述】

`web_search` 返回结果本身正常，但二次 LLM 总结偶尔会加入结果中没有明确支持的时间或细节。

### 【根因分析】

流程是：

```text
web_search → LLM synthesis
```

第二步仍可能 hallucinate。

### 【解决方法】

当前形成两类策略：

1. 真正需要自然语言回答：强化 synthesis 约束，只允许使用 Tool Result。
2. 只是保存搜索结果：完全跳过 LLM，用 Python 格式化原始结果。

### 【经验总结】

- Retrieval 正确不代表最终答案正确。
- Search/RAG 应分别评估 retrieval quality 与 synthesis faithfulness。

---

## 21. 明确的两工具任务仍交给 3B ReAct，导致重复搜索

### 【问题概述】

请求：

```text
上网查一下 Python 最新版本，然后把结果写入 python_version.md
```

虽然正确进入 multi-step ReAct，但 3B 连续多次调用相同 `web_search`，没有执行 `file_write`，最终出现：

```text
Invalid or incomplete response
```

### 【根因分析】

该任务虽然有两个 Tool，但执行图完全确定：

```text
web_search → file_write
```

让小模型自由规划属于过度使用 Agent。

### 【解决方法】

增加第四层：

```text
Deterministic Multi-Tool Workflow
```

识别：

```text
搜索 X → 写入 Y
```

返回结构：

```python
return {
    "kind": "web_search_to_file_write",
    "search_query": search_query,
    "path": path,
}
```

直接按固定顺序调用 Tool。

### 【经验总结】

- “多工具”不等于“一定需要 ReAct”。
- 固定 DAG 用代码编排比 LLM 编排可靠得多。

---

## 22. `web_search → file_write` Deterministic Workflow Fast Path

### 【问题概述】

需要确保新 workflow 真正做到：

```text
搜索一次 → 写一次 → 结束
```

### 【根因分析】

之前 ReAct 会重复搜索并陷入 parser / iteration 问题。

### 【解决方法】

新增 raw Tool helper：

```python
async def _call_tool_raw(
    tool_name: str,
    arguments: dict,
    agent_executor: AgentExecutor,
):
    ...
    return await tool.ainvoke({
        "input": json.dumps(
            arguments,
            ensure_ascii=False,
        )
    })
```

搜索结果用 Python 格式化：

```python
def _format_web_search_markdown(observation) -> str:
    ...
```

Workflow executor：

```python
async def _run_deterministic_workflow(...):
    search_result = await _call_tool_raw(...)
    content = _format_web_search_markdown(search_result)
    write_result = await _call_tool_raw(...)
```

最终日志验证成功：

```text
Routing deterministic workflow: web_search_to_file_write
Workflow step: web_search
Tool call: web_search
Workflow step: file_write
Tool call: file_write
```

### 【经验总结】

- 固定流程优先 Python orchestration。
- 保存搜索结果时保留 URL / snippet，避免 LLM 改写事实。
- 文件写入测试要用新文件名，防止旧文件掩盖失败。

---

## 23. DuckDuckGo 202 / Rate Limit

### 【问题概述】

搜索日志出现：

```text
202 Ratelimit
```

### 【根因分析】

DuckDuckGo 某个搜索 backend 触发速率限制。

### 【解决方法】

当前库能自动 fallback：

```text
html backend 202
→ lite backend 200
```

功能未阻断。

### 【经验总结】

- 搜索 provider rate limit 是正常外部依赖风险。
- 必须有 backend fallback。
- 后续可增加缓存、限速和 provider abstraction。

---

## 24. RAG 首次查询 embedding model 冷启动

### 【问题概述】

第一次 `query_knowledge_base` 时明显较慢，同时看到 Chroma 初始化和 `nomic-embed-text` 加载。

### 【根因分析】

当前采用 lazy initialization：

- 首次初始化 Chroma
- 首次加载 embedding model
- 首次启动 embedding runner

### 【解决方法】

当前功能正常，暂未修改。后续可考虑：

- Agent 启动预热 embedding
- 启动时初始化 Chroma
- health check 做轻量 warm-up

### 【经验总结】

- 首次请求慢和持续请求慢要分开分析。
- 对 UX 敏感时应主动预热。

---

## 25. `nomic-embed-text` context / option warning

### 【问题概述】

RAG 日志出现：

```text
requested context size too large for model
num_ctx=8192
n_ctx_train=2048
```

以及部分 invalid option warning。

### 【根因分析】

Embedding model 可能继承了不适合自己的 Chat Model options。

### 【解决方法】

当前 Ollama 自动降级到可用 context，因此功能未失败。后续检查：

- `agent/rag.py`
- embedding 初始化参数
- 全局 Ollama options

### 【经验总结】

- Chat model 与 embedding model 的 options 不应完全共用。
- Warning 不阻断功能，但稳定版前应清理。

---

## 26. Open WebUI 后台 metadata 仍会唤醒主 3B 模型

### 【问题概述】

虽然后台 title / tags / follow-up 已经不再误用 Tool，但它们仍然走 Direct Chat，因而继续占用 `qwen2.5:3b`。

### 【根因分析】

现在只做了：

```text
后台任务不进 Tool Agent
```

还没有做到：

```text
后台任务不用主模型
```

### 【解决方法】

当前未修改。后续可选：

- Open WebUI 关闭部分自动 metadata
- metadata 使用更小模型
- Agent API 单独识别 metadata 并路由轻量模型
- 部分 metadata 程序化生成

### 【经验总结】

- UI 后台请求也会消耗模型资源。
- 性能分析要区分用户主请求和 UI 内部请求。

---

## 27. 日志过长，难定位真正 Agent 行为

### 【问题概述】

大量 llama.cpp / Ollama `slot / prompt cache / sampler / timing` 日志淹没了真正有价值的：

```text
Routing ...
Fast Path ...
Tool call ...
```

### 【根因分析】

当前仍处于调试阶段，Agent verbose 与 Ollama 日志都较详细。

### 【解决方法】

目前先保留详细日志。稳定后再：

- 降低 Agent verbose
- 调整 Ollama log verbosity
- 分离 Agent / MCP / Ollama 日志
- 增加 request id

### 【经验总结】

- 调试期优先可观测性。
- 稳定期再做日志分层和降噪。

---

## 28. 当前暂不修改的第二组复杂任务 Router 边界

### 【问题概述】

请求：

```text
上网查一下 Python 3.14 的最新变化，
比较最重要的三项，
整理成中文总结后写入 python_changes.md
```

实际执行成功：

```text
web_search → file_write → Finished chain
```

但 Router 日志显示：

```text
Routing ambiguous tool request to ReAct agent: file_write
```

而不是更准确的：

```text
Routing multi-step request to ReAct agent
```

### 【根因分析】

`_is_multi_step_request()` 对“总结后写入”“比较...整理...”等中文表达覆盖还不完整。

### 【解决方法】

**按当前要求，本轮暂不继续修改。**

后续计划：

- 扩充 multi-step 检测
- 不仅依赖“然后 / 接着”
- 同时检测一句话中的多个 tool intent
- complex ReAct 不强制某一个 `requested_tool`

示意：

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

- 当前属于 Router 分类精度问题，不是主链路阻断问题。
- 已工作的复杂执行链先保持稳定，再单独修边界规则。

---

# 当前整体架构

项目已经从最初的：

```text
User
  ↓
ReAct Agent
  ↓
Tool
```

演化为：

```text
Open WebUI Background
        ↓
   Direct Chat

User Request
    ↓
Intent / Context Router
    ↓
┌──────────────────────────────────────────────┐
│ 1. 普通聊天                                  │
│    → Direct Chat                             │
│                                              │
│ 2. 单工具 + 参数明确                         │
│    → Single-Tool Fast Path                   │
│                                              │
│ 3. 多工具 + 执行图明确                       │
│    → Deterministic Workflow Fast Path        │
│                                              │
│ 4. 参数模糊 / 动态推理 / 比较 / 分析 / 规划   │
│    → ReAct Agent                             │
└──────────────────────────────────────────────┘
```

---

# 当前主要验证通过能力

```text
Python 3.13 环境                       ✅
Ollama 本地模型                       ✅
Ollama D 盘模型目录                   ✅
NO_PROXY 本地调用                     ✅
Open WebUI                            ✅
MCP Server                            ✅
6 个 MCP Tools 加载                   ✅
GitHub RAG ingestion                  ✅
ChromaDB                              ✅
code_exec 裸表达式                    ✅
code_exec return_direct               ✅
Direct Chat                           ✅
多轮 conversation history             ✅
Open WebUI 后台 Tool 隔离             ✅
中文常用 Tool Intent                  ✅
Context-aware Router                  ✅
Single-Tool Fast Path                 ✅
多轮数学 Fast Path                    ✅
file_list / read / write Fast Path    ✅
web_search Fast Path                  ✅
RAG Fast Path                         ✅
web_search → file_write Workflow      ✅
复杂 ReAct web_search → file_write    ✅
```

---

# 当前仍建议后续处理的问题

1. 复杂 multi-step Router 边界（当前暂不修改）
2. Web / RAG synthesis faithfulness
3. Open WebUI title / tags / follow-up 仍使用主 3B 模型
4. Embedding context warning
5. DuckDuckGo rate limit 的缓存 / provider 抽象
6. 日志降噪
7. 清理旧 Router/helper 与未使用 import
8. 建立 Agent Eval 自动测试集

建议 Eval 指标：

```text
Routing Accuracy
Fast Path Hit Rate
Tool Call Count
Task Success Rate
Multi-turn Success Rate
Faithfulness / Hallucination Rate
```

---

# 可复用避坑原则

1. 先判断问题在哪一层：UI / Router / Agent / Adapter / MCP Tool / External API / Ollama runtime。
2. 不要把所有请求都交给 ReAct。
3. Tool success、parser success、final answer success 是三个不同阶段。
4. 计算、文件操作、数据搬运、固定 workflow 尽量 deterministic。
5. 小模型最怕复杂格式约束；减少 StructuredTool 参数复杂度和 ReAct round-trip。
6. GitHub、DuckDuckGo、代理等外部依赖默认考虑 retry / fallback。
7. Router 修改一定做端到端日志验证，不只看 UI。
8. 文件写入测试使用新文件名，避免旧文件掩盖失败。
9. 修改返回契约时同步更新测试。
10. 不要用增大 `max_iterations` 掩盖 Agent 设计问题。

---

# 推荐后续调试顺序

```text
① 暂保留当前复杂任务逻辑
        ↓
② 修 Web/RAG synthesis faithfulness
        ↓
③ 优化 Open WebUI metadata model
        ↓
④ 修 embedding context warning
        ↓
⑤ 日志降噪
        ↓
⑥ 清理旧 Router/helper
        ↓
⑦ 建 Agent Eval 自动测试集
```

