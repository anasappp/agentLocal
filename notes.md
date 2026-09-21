# mcp-ollama-agent 本地运行与排错备忘

> 项目路径：`D:\programGithub\mcp-ollama-agent`  
> 环境：Windows + PyCharm + PowerShell + Python 3.13 + Ollama + Docker  
> 目的：记录首次跑通项目时遇到的问题、定位过程、解决办法，以及后续重新启动项目时的注意事项。

---

## 一、最终可用环境

首次跑通时确认可用的关键环境：

- Python：`3.13.9`
- 虚拟环境：`D:\programGithub\mcp-ollama-agent\.venv`
- Ollama：已安装并可正常访问 `http://127.0.0.1:11434`
- 模型：`qwen2.5:3b`
- Embedding 模型：`nomic-embed-text`
- MCP Server：`http://127.0.0.1:8001`
- Agent API：`http://127.0.0.1:8000`
- 项目根目录：`D:\programGithub\mcp-ollama-agent`

---

## 二、首次运行时遇到的问题

## 1. Python 3.13 已安装，但 `python` 命令仍然指向 Python 3.9

### 现象

执行：

```powershell
python --version
```

得到：

```text
Python 3.9.7
```

但执行：

```powershell
py -0p
```

可以看到：

```text
-V:3.13 *    D:\app\python\python.exe
-V:3.9       D:\app\python3_9\python.exe
```

说明 Python 3.13 实际已经安装，只是系统中的 `python` 命令仍优先指向 Python 3.9。

### 如何定位

`py -0p` 是 Windows Python Launcher 提供的版本列表。  
它证明问题不是“Python 3.13 没装”，而是“命令解析到了旧版本”。

项目的 `scripts\start.ps1` 在不存在 `.venv` 时会执行：

```powershell
python -m venv .venv
```

如果直接运行脚本，就可能用 Python 3.9 创建虚拟环境。

### 解决办法

手动指定 Python 3.13 创建虚拟环境：

```powershell
cd D:\programGithub\mcp-ollama-agent
py -3.13 -m venv .venv
```

然后激活后确认：

```powershell
python --version
```

应显示：

```text
Python 3.13.9
```

### 结论

不要因为 `python --version` 显示旧版本就重装 Python。  
先用：

```powershell
py -0p
```

确认机器中到底安装了哪些 Python。

---

## 2. PowerShell 禁止运行 `Activate.ps1`

### 现象

执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

报错：

```text
因为在此系统上禁止运行脚本
SecurityError
UnauthorizedAccess
```

### 如何定位

报错中明确出现：

```text
about_Execution_Policies
```

说明不是 Python 或 venv 创建失败，而是 PowerShell Execution Policy 阻止执行 `.ps1`。

### 解决办法

只对当前 PowerShell 窗口临时放开限制：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

然后重新执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

成功后命令行前面会出现：

```text
(.venv)
```

### 注意

使用 `-Scope Process` 只影响当前 PowerShell 会话，关闭窗口后失效，比修改全局策略更安全。

---

## 3. Ollama 未安装

### 现象

执行：

```powershell
ollama --version
```

提示：

```text
无法将“ollama”项识别为 cmdlet、函数、脚本文件或可运行程序
```

### 如何定位

这是典型的 CommandNotFound，不是项目代码报错。

### 解决办法

Windows 可以使用：

```powershell
winget install Ollama.Ollama
```

安装后重新打开 PowerShell，再确认：

```powershell
ollama --version
```

### 注意

Ollama 安装包较大，而且 `winget` 最终可能从 GitHub Release 下载，因此第一次安装可能很慢。

---

## 4. `.env` 不存在，而且仓库默认模型配置不一致

### 现象

项目中存在：

```text
.env.example
```

但首次 clone 后没有 `.env`。

同时仓库中存在一个容易踩坑的不一致：

- `.env.example` / `start.ps1` 使用 `qwen2.5:1.5b`
- `agent/config.py` 中代码默认值是 `qwen2.5:3b`

如果没有 `.env`，Agent 可能读取到代码默认值，而启动脚本却只下载了 1.5B 模型。

### 如何定位

检查：

```powershell
Get-Content .env
```

以及查看：

```text
agent/config.py
scripts/start.ps1
.env.example
```

发现模型名并不完全一致。

### 解决办法

先创建 `.env`：

```powershell
Copy-Item .env.example .env
```

最终建议明确写成：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text

MCP_SERVER_URL=http://127.0.0.1:8001
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8001

AGENT_API_HOST=0.0.0.0
AGENT_API_PORT=8000

CHROMA_PERSIST_DIR=.chroma
FILE_OPS_ROOT=./workspace

LOG_LEVEL=INFO
```

### 注意

修改 `.env` 后必须重启 Agent 服务，否则旧进程不会重新读取配置。

---

## 5. PowerShell 中直接使用 `curl -d` 发送 JSON 时解析失败

### 现象

调用：

```text
POST /v1/chat/completions
```

时出现：

```text
JSON decode error
Could not resolve host: is
Could not resolve host: plus
unmatched close brace/bracket
```

### 如何定位

这些错误同时出现，说明并不是 Agent 本身报错，而是 PowerShell/curl 对 JSON 字符串的引号和转义处理出了问题。

尤其是在 PowerShell 单引号字符串中继续使用：

```text
\"
```

会导致传入 curl 的内容和预期不一致。

### 解决办法

Windows PowerShell 下建议直接使用 `Invoke-RestMethod`，避免复杂转义。

示例：

```powershell
$body = @{
    model = "local-agent"
    messages = @(
        @{
            role = "user"
            content = "What is 12 plus 25?"
        }
    )
    stream = $false
} | ConvertTo-Json -Depth 5
```

然后：

```powershell
$response = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/v1/chat/completions" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

查看结果：

```powershell
$response.choices[0].message.content
```

---

## 6. Agent API 返回 `502`，但 Ollama CLI 可以正常回答

### 现象

以下命令成功：

```powershell
ollama run qwen2.5:1.5b "What is 12 plus 25?"
```

能够正常回答：

```text
37
```

同时：

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

也能正常返回模型列表。

但是调用以下内容：

```powershell
$body = @{
>>     model = "local-agent"                                                                        
>>     messages = @(                                                                                
>>         @{                                                                                       
>>             role = "user"                                                                        
>>             content = "What is 12 plus 25?"                                                      
>>         }                                                                                        
>>     )                                                                                            
>>     stream = $false                                                                              
>> } | ConvertTo-Json -Depth 5                                                                      
(.venv) PS D:\programGithub\mcp-ollama-agent> $response = Invoke-RestMethod `
>>     -Uri "http://localhost:8000/v1/chat/completions" `                                           
>>     -Method Post `                                                                               
>>     -ContentType "application/json" `                                                            
>>     -Body $body                                                                                  
(.venv) PS D:\programGithub\mcp-ollama-agent> $response = Invoke-RestMethod `
>>     -Uri "http://localhost:8000/v1/chat/completions" `                                           
>>     -Method Post `                                                                               
>>     -ContentType "application/json" `                                                            
>>     -Body $body                                                                                  
(.venv) PS D:\programGithub\mcp-ollama-agent> $response.choices[0].message.content
Error:  (status code: 502)
```

却返回：

```text
ollama._types.ResponseError: (status code: 502)
```

Agent API 最终也表现为：

```text
Error: (status code: 502)
```

### 如何定位

这个现象非常关键：

1. Ollama CLI 正常  
2. Ollama HTTP 服务正常  
3. 模型已经加载  
4. 但 Python SDK 请求失败  

因此可以排除：

- 模型没下载
- Ollama 没启动
- Agent API 没启动
- MCP Server 没启动

问题集中到：

```text
Python/httpx → Ollama
```

这一层。

结合 Windows 环境下 Python HTTP 客户端可能继承系统代理，最终判断本地请求可能被代理转发，从而出现 502。

### 解决办法

首先避免 `localhost`，改用：

```text
127.0.0.1
```

`.env` 改为：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
MCP_SERVER_URL=http://127.0.0.1:8001
```

在启动服务的 PowerShell 窗口中设置：

```powershell
$env:NO_PROXY="localhost,127.0.0.1"
```

必要时也可以单独测试 Ollama Python Client 是否绕过系统代理：

```powershell
python -c "import ollama; c=ollama.Client(host='http://127.0.0.1:11434', trust_env=False); r=c.chat(model='qwen2.5:1.5b', messages=[{'role':'user','content':'What is 12 plus 25?'}]); print(r['message']['content'])"
```

修改后重启：

```powershell
.\scripts\start.ps1
```

之后 502 消失。

### 排错思路总结

这类问题不要一看到 502 就改 LangChain 版本。

应该分层测试：

```text
Ollama CLI
    ↓
Ollama HTTP API
    ↓
Ollama Python SDK
    ↓
LangChain ChatOllama
    ↓
Agent
```

从最底层逐层排除，比直接修改项目代码更可靠。

---

## 7. 502 解决后，Agent 出现 `iteration limit or time limit`

### 现象

Agent 不再返回 502，而是：

```text
Agent stopped due to iteration limit or time limit.
```

### 如何定位

这个报错的性质已经完全不同。

它说明以下链路实际上已经通了：

```text
FastAPI
  ↓
LangChain Agent
  ↓
Ollama
  ↓
LLM
```

项目 `agent/agent.py` 中配置了：

```python
max_iterations=8
handle_parsing_errors=True
```

Agent 能开始执行，但没有在 8 次 ReAct 循环内正确结束。

此时网络、API、模型加载都已经不是主要问题。

### 原因判断

当时使用的是：

```text
qwen2.5:1.5b
```

该模型本身可以做普通问答，但对项目要求的严格 ReAct 输出格式、工具选择和终止判断不够稳定。

项目的 ReAct Prompt 要求模型持续生成类似：

```text
Thought:
Action:
Action Input:
Observation:
...
Final Answer:
```

1.5B 模型容易在格式解析或循环终止上失误。

### 错误解决思路

一开始不应该直接把：

```python
max_iterations=8
```

改成更大。

因为如果模型根本没有稳定遵循 ReAct 协议，提高 iteration 数只会让错误循环更久。

更合理的方法是提高 Agent 模型能力。

### 解决办法

下载 3B：

```powershell
ollama pull qwen2.5:3b
```

修改 `.env`：

```env
OLLAMA_MODEL=qwen2.5:3b
```

重启：

```powershell
.\scripts\start.ps1
```

重新测试：

```powershell
$response.choices[0].message.content
```

最终 Agent 正常返回答案，项目成功跑通。

---

# 三、整个问题链路如何一步步缩小范围

这次排错最重要的经验不是某一条命令，而是按层排查。

完整链路：

```text
用户请求
  ↓
Open WebUI / PowerShell
  ↓
FastAPI Agent API :8000
  ↓
LangChain ReAct Agent
  ↓
Ollama Python Client / ChatOllama
  ↓
Ollama Server :11434
  ↓
qwen2.5
  ↓
MCP Adapter
  ↓
MCP Server :8001
  ↓
Tools
```

遇到问题时不要一次怀疑所有组件，而要从下往上验证。

### 推荐排错顺序

#### 1. Python

```powershell
py -0p
python --version
```

#### 2. Ollama 是否安装

```powershell
ollama --version
```

#### 3. 模型是否存在

```powershell
ollama list
```

#### 4. 模型能否独立运行

```powershell
ollama run qwen2.5:3b "What is 12 plus 25?"
```

#### 5. Ollama HTTP 服务

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

#### 6. MCP Server

浏览器：

```text
http://127.0.0.1:8001/health
```

#### 7. Agent API

浏览器：

```text
http://127.0.0.1:8000/health
```

理想结果：

```json
{
  "status": "ok",
  "agent": true
}
```

#### 8. Agent 模型列表

```powershell
curl.exe http://127.0.0.1:8000/v1/models
```

应出现：

```text
local-agent
```

#### 9. 最终 Agent 对话

使用 `Invoke-RestMethod` 测试。

---

# 四、以后重新启动项目的推荐流程

## 1. 打开 Docker Desktop

如果暂时不需要 Open WebUI，可以晚一点再启动 Docker。

---

## 2. 打开 PyCharm

打开项目：

```text
D:\programGithub\mcp-ollama-agent
```

确认 Interpreter 为：

```text
D:\programGithub\mcp-ollama-agent\.venv\Scripts\python.exe
```

---

## 3. 打开 PyCharm Terminal

如果没有自动进入虚拟环境：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

然后设置本地地址不走代理：

```powershell
$env:NO_PROXY="localhost,127.0.0.1"
```

---

## 4. 启动核心服务

```powershell
.\scripts\start.ps1
```

保持这个 Terminal 不要关闭。

---

## 5. 检查服务

浏览器：

```text
http://127.0.0.1:8001/health
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

---

## 6. 如果需要 Open WebUI

另外新建一个 PyCharm Terminal：

```powershell
docker compose up -d
```

检查：

```powershell
docker ps
```

浏览器：

```text
http://localhost:3000
```

选择：

```text
local-agent
```

而不是直接选择普通 Ollama 模型。

---

# 五、几个重要注意事项

## 1. `.env` 改完一定要重启

Agent 在启动时读取配置。修改：

```text
OLLAMA_MODEL
OLLAMA_BASE_URL
MCP_SERVER_URL
```

后，如果不重启进程，修改不会作用到已经运行的 Agent。

---

## 2. 本机服务优先使用 `127.0.0.1`

本项目建议：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
MCP_SERVER_URL=http://127.0.0.1:8001
```

可以减少 `localhost` 被代理、DNS 或系统网络配置干扰的可能性。

---

## 3. Agent 模型目前使用 3B

当前验证跑通的模型：

```text
qwen2.5:3b
```

1.5B 可以进行普通对话，但在本项目 ReAct Agent 中出现过无法正确终止、达到 iteration limit 的情况。

---

## 4. 不要用简单数学问题判断 MCP Tool 是否工作

类似：

```text
What is 12 plus 25?
```

只证明 Agent 和模型能回答，不代表 MCP Tool 已调用。

真正测试 Tool Use，可以使用：

```text
Use Python to calculate 12345 * 6789.
```

并观察运行 Agent 的 Terminal 中是否出现 `code_exec` Tool Call。

---

## 5. README 与当前 Windows 启动脚本存在少量不一致

需要特别留意：

- README 描述的默认模型与部分代码/脚本配置并非完全一致。
- `start.ps1` 主要启动 MCP Server 和 Agent API。
- Open WebUI 如未自动启动，可以手动执行：

```powershell
docker compose up -d
```

因此以后遇到“README 说应该启动了，但端口没有”的情况，优先检查真实脚本，而不是只看 README。

---

# 六、最终验证标准

以下全部成功，才算核心链路真正跑通：

```text
[✓] Python 虚拟环境正常
[✓] requirements 安装完成
[✓] Ollama Server 正常
[✓] qwen2.5:3b 可直接运行
[✓] MCP Server :8001 正常
[✓] Agent API :8000 正常
[✓] /v1/models 能看到 local-agent
[✓] Agent 能正常返回 Final Answer
[✓] 不再出现 502
[✓] 不再出现 iteration limit
```

之后再继续验证：

```text
[ ] MCP code_exec
[ ] MCP web_search
[ ] file_read / file_write / file_list
[ ] RAG / ChromaDB
[ ] Open WebUI
```

---

# 七、复盘

本次主要经历了三类问题：

```text
环境问题
Python 版本 / PowerShell Execution Policy / Ollama 安装
        ↓
通信问题
PowerShell JSON 转义 / Python 请求本地 Ollama 时的代理问题
        ↓
Agent 能力问题
qwen2.5:1.5b 无法稳定完成 ReAct 循环
```

最终分别通过：

```text
显式使用 Python 3.13 创建 venv
        +
使用 Process Scope 放开 PowerShell 脚本
        +
创建并明确配置 .env
        +
使用 127.0.0.1 + NO_PROXY
        +
使用 Invoke-RestMethod 测试 API
        +
将 Agent 模型升级到 qwen2.5:3b
```

完成了项目本地跑通。

---

> 后续如果继续改造成自己的 Agent 项目，建议保留这份文档，并在每次新增依赖、修改模型、修改 MCP Tool、修改 Agent Prompt 后补充对应的运行与排错记录。
