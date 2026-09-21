"""LangChain ReAct agent wired to Ollama + MCP tools."""
import json
import logging
from functools import lru_cache

import re

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langchain_ollama import ChatOllama

from agent.config import settings
from agent.mcp_adapter import load_mcp_tools

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful local AI assistant with expertise in the local AI ecosystem. \
You are the model {ollama_model}, running locally via Ollama.
If anyone asks which model you are, what model is in use, or anything about your own identity, answer directly: you are {ollama_model}.

You have access to a knowledge base with documentation for these local AI tools:
Ollama, llama.cpp, LocalAI, Open WebUI, Jan, text-generation-webui, AnythingLLM, PrivateGPT, LiteLLM, GPT4All, Continue, Tabby.

Available tools (use ONLY when the question genuinely requires them):
{tools}

Rules:
- If the user explicitly asks you to use a specific available tool, you MUST call that tool before giving the Final Answer.
- For arithmetic, numerical calculation, or any computation where an exact result matters, use `code_exec` instead of calculating mentally.
- For greetings, conversational messages, or questions you can confidently answer from general knowledge, go DIRECTLY to Final Answer only when no tool is needed and the user has not requested one.
- Use `query_knowledge_base` when the user asks about any local AI tool, how to install/configure/use it, or compares tools. Prefer this over web_search for ecosystem topics.
- Use `web_search` for current events, recent releases, or topics outside the knowledge base.
- Use `file_read` / `file_write` / `file_list` for workspace file operations.
- Use `code_exec` to run Python code or verify computations.
- Only pass arguments that the tool explicitly accepts. Do not invent extra fields.
- When answering from knowledge base results, cite the source document.
- Use the conversation history only as context for the current question.
- The latest Question is the user's current request.
- Do not invent facts that are not present in the conversation history or tool results.

Tool argument rules:
- Tool arguments MUST be a flat JSON object using exactly the parameter names shown below.
- Never wrap the whole argument object inside another field.
- Never invent argument names such as `filename`, `text`, or `input` when the schema expects different names.
- Once a tool call succeeds, do not repeat the same tool with the same arguments unless the result contains an error or the user explicitly asks you to retry.

Exact examples:
- file_write:
  Action Input: {{"path": "test.txt", "content": "hello world"}}

- file_read:
  Action Input: {{"path": "test.txt"}}

- file_list:
  Action Input: {{"directory": "."}}

- code_exec:
  Action Input: {{"code": "print(12345 * 6789)"}}

- web_search:
  Action Input: {{"query": "latest Python release", "max_results": 5}}

- query_knowledge_base:
  Action Input: {{"query": "llama.cpp quantization", "k": 3}}

Use this exact format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action (JSON object with only valid fields)
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Conversation history:
{chat_history}

Question: {input}
Thought: {agent_scratchpad}"""


async def build_agent() -> AgentExecutor:
    tools = await load_mcp_tools()

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.1,
        timeout=120,  # model cold-start can take 20-30s on CPU
    )

    prompt = PromptTemplate.from_template(SYSTEM_PROMPT)

    agent = create_react_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=8,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )


def _is_openwebui_internal_request(query: str) -> bool:
    """Detect Open WebUI background metadata-generation requests."""

    q = query.lstrip().lower()

    if not q.startswith("### task:"):
        return False

    internal_tasks = [
        "generate a concise title",
        "suggest 3-5 relevant follow-up questions",
        "generate 1-3 broad tags",
    ]

    return any(task in q for task in internal_tasks)


def _matches_any(query: str, patterns: list[str]) -> bool:
    """Return True when query matches any regex pattern."""
    return any(
        re.search(pattern, query, re.IGNORECASE)
        for pattern in patterns
    )


def _detect_tool_intent(query: str) -> str | None:
    """
    Detect common Chinese / English tool intents.

    Returns the tool that should handle the request,
    or None when normal direct chat is sufficient.
    """

    q = query.lower().strip()

    # ---------------------------------------------------------
    # 0. Explicit tool names
    # ---------------------------------------------------------

    tool_names = [
        "code_exec",
        "file_read",
        "file_write",
        "file_list",
        "web_search",
        "query_knowledge_base",
    ]

    for tool_name in tool_names:
        if re.search(
            rf"(?<!\w){re.escape(tool_name)}(?!\w)",
            q,
        ):
            return tool_name

    # ---------------------------------------------------------
    # 1. code_exec
    # ---------------------------------------------------------

    code_patterns = [
        # English
        r"\bcalculate\b",
        r"\bcompute\b",
        r"\bcalculator\b",
        r"\brun python\b",
        r"\bexecute python\b",
        r"\brun code\b",
        r"\bexecute code\b",

        # Chinese
        r"算一下",
        r"算一算",
        r"算出",
        r"求值",
        r"重新计算",
        r"重算",
        r"计算器",
        r"运行代码",
        r"执行代码",
        r"运行\s*python",
        r"执行\s*python",

        # Arithmetic expressions
        r"\d+\s*[\+\-\*/×÷]\s*\d+",
        r"\d+\s*乘以\s*\d+",
        r"\d+\s*除以\s*\d+",
        r"\d+\s*加上\s*\d+",
        r"\d+\s*减去\s*\d+",
    ]

    if _matches_any(q, code_patterns):
        return "code_exec"

    # Common filename extensions
    file_ext = r"(?:txt|md|json|ya?ml|csv|log|py|toml|ini)"

    # ---------------------------------------------------------
    # 2. file_write
    # ---------------------------------------------------------

    file_write_patterns = [
        # English
        r"\bcreate (?:a )?file\b",
        r"\bwrite (?:to )?(?:a )?file\b",
        r"\bsave (?:to )?(?:a )?file\b",
        r"\bappend (?:to )?(?:a )?file\b",

        # Chinese
        r"创建文件",
        r"新建文件",
        r"写入文件",
        r"保存到文件",
        r"生成文件",
        r"追加到文件",

        # e.g. 创建 test.txt / 新建 notes.md
        rf"(?:创建|新建|生成|写入|保存).*\.(?:{file_ext[3:-1]})",
    ]

    if _matches_any(q, file_write_patterns):
        return "file_write"

    # ---------------------------------------------------------
    # 3. file_read
    # ---------------------------------------------------------

    file_read_patterns = [
        # English
        r"\bread (?:the )?file\b",
        r"\bopen (?:the )?file\b",
        r"\bshow (?:the )?file contents\b",
        r"\b(?:read|open|show)\s+(?:the\s+)?(?:(?:contents?|content)\s+of\s+)?(?:file\s+)?[\w./\\-]+\.(?:txt|md|json|ya?ml|csv|log|py|toml|ini)\b",

        # Chinese
        r"读取文件",
        r"读一下文件",
        r"查看文件内容",
        r"看看文件内容",
        r"打开文件",

        # e.g. 读取 test.txt / 打开 README.md
        rf"(?:读取|打开|查看|看看).*\.(?:{file_ext[3:-1]})",
    ]

    if _matches_any(q, file_read_patterns):
        return "file_read"

    # ---------------------------------------------------------
    # 4. file_list
    # ---------------------------------------------------------

    file_list_patterns = [
        # English
        r"\blist files\b",
        r"\blist directory\b",
        r"\bshow files\b",
        r"\bshow directory\b",

        # Chinese
        r"列出文件",
        r"文件列表",
        r"查看目录",
        r"列出目录",
        r"目录里有什么",
        r"文件夹里有什么",
        r"有哪些文件",
        r"工作区.*文件",
        r"workspace.*文件",
    ]

    if _matches_any(q, file_list_patterns):
        return "file_list"

    # ---------------------------------------------------------
    # 5. web_search
    # ---------------------------------------------------------

    web_patterns = [
        # English
        r"\bsearch the web\b",
        r"\bsearch online\b",
        r"\blook up online\b",
        r"\blatest\b",
        r"\brecent news\b",
        r"\bcurrent release\b",
        r"\blatest version\b",

        # Chinese
        r"搜索网页",
        r"上网查",
        r"联网查",
        r"网上查",
        r"网上找",
        r"查一下最新",
        r"最新消息",
        r"最新新闻",
        r"近期新闻",
        r"最近.*(?:新闻|消息|更新)",
        r"今天.*(?:新闻|消息)",
        r"最新版本",
        r"当前版本",
    ]

    if _matches_any(q, web_patterns):
        return "web_search"

    # ---------------------------------------------------------
    # 6. query_knowledge_base
    # ---------------------------------------------------------

    rag_patterns = [
        # English
        r"\bknowledge base\b",
        r"\bsearch the docs\b",
        r"\bsearch documentation\b",
        r"\bretrieve documents\b",

        # Chinese
        r"知识库",
        r"查文档",
        r"检索文档",
        r"从文档里找",
        r"从资料里找",
        r"根据项目文档",
        r"根据知识库",
        r"根据文档",
        r"查询资料",
        r"项目资料",
    ]

    if _matches_any(q, rag_patterns):
        return "query_knowledge_base"

    # ---------------------------------------------------------
    # 7. Local-AI ecosystem questions -> knowledge base
    # ---------------------------------------------------------

    ecosystem_terms = [
        "ollama",
        "llama.cpp",
        "localai",
        "open webui",
        "anythingllm",
        "privategpt",
        "litellm",
        "gpt4all",
        "text-generation-webui",
        "tabby",
        "gguf",
    ]

    if any(term in q for term in ecosystem_terms):
        return "query_knowledge_base"

    return None

def _detect_contextual_tool_intent(
    query: str,
    conversation_messages: list[dict] | None = None,
) -> str | None:
    """
    Detect tool intent using both the current query and
    recent conversation context.
    """

    # First, try the current message alone.
    current_intent = _detect_tool_intent(query)

    if current_intent:
        return current_intent

    if not conversation_messages:
        return None

    q = query.lower().strip()

    # Only inspect a small amount of recent history.
    recent_messages = conversation_messages[-4:]

    recent_text = "\n".join(
        str(message.get("content", ""))
        for message in recent_messages
    ).lower()

    # ---------------------------------------------------------
    # Follow-up calculation
    # ---------------------------------------------------------
    calculation_followups = [
        r"再算",
        r"重新算",
        r"再计算",
        r"再乘",
        r"再除",
        r"再加",
        r"再减",
        r"用计算器",
        r"继续计算",
        r"\bcalculate that\b",
        r"\bcompute that\b",
    ]

    if _matches_any(q, calculation_followups):
        if (
            "code_exec" in recent_text
            or _detect_tool_intent(recent_text) == "code_exec"
        ):
            return "code_exec"

    # ---------------------------------------------------------
    # Follow-up file read
    # ---------------------------------------------------------
    if _is_file_read_followup(q):
        recent_path = _find_recent_file_path(
            conversation_messages,
        )

        if recent_path:
            return "file_read"

    # ---------------------------------------------------------
    # Follow-up web search
    # ---------------------------------------------------------
    web_followups = [
        r"继续查",
        r"再查一下",
        r"再搜一下",
        r"继续搜索",
        r"查更多",
        r"\bsearch more\b",
        r"\blook up more\b",
    ]

    if _matches_any(q, web_followups):
        if (
            "web_search" in recent_text
            or "上网" in recent_text
            or "搜索" in recent_text
            or "最新" in recent_text
        ):
            return "web_search"

    # ---------------------------------------------------------
    # Follow-up knowledge-base search
    # ---------------------------------------------------------
    rag_followups = [
        r"继续查文档",
        r"再查知识库",
        r"从资料里继续找",
        r"文档里还有",
        r"\bsearch the docs again\b",
    ]

    if _matches_any(q, rag_followups):
        return "query_knowledge_base"

    return None

def _extract_first_json_object(text: str) -> dict | None:
    """Extract the first valid JSON object embedded in text."""

    decoder = json.JSONDecoder()

    for index, char in enumerate(text):
        if char != "{":
            continue

        try:
            obj, _ = decoder.raw_decode(text[index:])

            if isinstance(obj, dict):
                return obj

        except json.JSONDecodeError:
            continue

    return None


def _extract_file_path(query: str) -> str | None:
    """Extract a common workspace file path."""

    match = re.search(
        r"((?:[\w.\-]+[\\/])*[\w.\-]+\."
        r"(?:txt|md|json|ya?ml|csv|log|py|toml|ini))",
        query,
        re.IGNORECASE,
    )

    return match.group(1) if match else None


def _find_recent_file_path(
    conversation_messages: list[dict] | None,
) -> str | None:
    """
    Find one unambiguous file path from recent user messages.

    If the most recent relevant user message contains multiple
    file paths, return None instead of guessing.
    """

    if not conversation_messages:
        return None

    pattern = (
        r"((?:[\w.\-]+[\\/])*[\w.\-]+\."
        r"(?:txt|md|json|ya?ml|csv|log|py|toml|ini))"
    )

    for message in reversed(conversation_messages[-6:]):
        if message.get("role") != "user":
            continue

        content = str(
            message.get("content", "")
        )

        matches = re.findall(
            pattern,
            content,
            re.IGNORECASE,
        )

        # Remove duplicates while keeping order.
        unique_paths = list(
            dict.fromkeys(matches)
        )

        if len(unique_paths) == 1:
            return unique_paths[0]

        # The latest relevant user turn contains more than one
        # possible file. Do not guess.
        if len(unique_paths) > 1:
            return None

    return None


def _is_file_read_followup(
    query: str,
) -> bool:
    """Detect references to a previously mentioned file."""

    patterns = [
        # Chinese: action-style
        r"打开刚才",
        r"读取刚才",
        r"再读取刚才",
        r"看看刚才",
        r"看一下刚才",
        r"打开那个文件",
        r"读取那个文件",
        r"再读取那个文件",
        r"重新读取那个文件",

        # Chinese: content-style
        r"刚才的文件内容",
        r"刚才那个文件.*内容",
        r"那个文件.*内容",
        r"刚才文件.*内容",
        r"刚才保存的文件",
        r"刚才写入的文件",
        r"刚才生成的文件",
        r"刚刚的文件",

        # English
        r"\bopen that file\b",
        r"\bread that file\b",
        r"\bread that file again\b",
        r"\bopen that file again\b",
        r"\bwhat(?:'s| is| was) in that file\b",
        r"\bwhat(?:'s| is| was) the content of that file\b",
        r"\bshow (?:me )?that file(?:'s)? contents?\b",
    ]

    return _matches_any(
        query.lower().strip(),
        patterns,
    )


def _extract_simple_math_expression(
    query: str,
    conversation_messages: list[dict] | None = None,
) -> str | None:
    """Convert common arithmetic requests into Python syntax."""

    normalized = query

    replacements = [
        ("乘以", "*"),
        ("乘", "*"),
        ("×", "*"),
        ("除以", "/"),
        ("除", "/"),
        ("÷", "/"),
        ("加上", "+"),
        ("加", "+"),
        ("减去", "-"),
        ("减", "-"),
    ]

    for old, new in replacements:
        normalized = normalized.replace(old, new)

    # Example: 66 * 7
    match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)",
        normalized,
    )

    if match:
        return (
            f"{match.group(1)} "
            f"{match.group(2)} "
            f"{match.group(3)}"
        )

    # Example: 再乘以11
    follow_up = re.search(
        r"(?:再|继续)?\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)",
        normalized,
    )

    if follow_up and conversation_messages:
        for message in reversed(conversation_messages):
            if message.get("role") != "assistant":
                continue

            numbers = re.findall(
                r"-?\d+(?:\.\d+)?",
                str(message.get("content", "")),
            )

            if numbers:
                return (
                    f"{numbers[-1]} "
                    f"{follow_up.group(1)} "
                    f"{follow_up.group(2)}"
                )

    return None


def _is_multi_step_request(query: str) -> bool:
    """Keep multi-tool / multi-step requests inside ReAct."""

    patterns = [
        r"然后",
        r"接着",
        r"再把",
        r"并(?:且)?(?:保存|写入|创建|读取|搜索|查询)",
        r"\band then\b",
        r"\bafter that\b",
        r"\bthen save\b",
        r"\bthen write\b",
    ]

    return _matches_any(query.lower(), patterns)


def _clean_retrieval_query(
    query: str,
    tool_name: str,
) -> str:
    """
    Remove routing phrases and answer-format constraints from
    search / RAG queries.

    Keep only the information-retrieval topic.
    """

    q = query.strip()

    # ---------------------------------------------------------
    # Remove tool-routing prefixes
    # ---------------------------------------------------------

    if tool_name == "web_search":
        q = re.sub(
            r"^(?:帮我)?\s*"
            r"(?:上网查一下|上网查|联网查一下|联网查|"
            r"网上查一下|网上查|搜索一下|搜索网页|"
            r"search the web(?: for)?|"
            r"search online(?: for)?|"
            r"look up online(?: for)?)\s*",
            "",
            q,
            flags=re.IGNORECASE,
        )

    elif tool_name == "query_knowledge_base":
        q = re.sub(
            r"^(?:帮我)?\s*"
            r"(?:根据知识库|查一下知识库|查询知识库|"
            r"根据文档|查文档|检索文档|"
            r"search the knowledge base(?: for)?|"
            r"search the docs(?: for)?)\s*",
            "",
            q,
            flags=re.IGNORECASE,
        )

        # These words describe the answer action, not the topic.
        q = re.sub(
            r"^(?:解释一下|解释|介绍一下|介绍|"
            r"说明一下|说明)\s*",
            "",
            q,
        )

    # ---------------------------------------------------------
    # Remove answer constraints from the end
    # ---------------------------------------------------------

    constraint_patterns = [
        # Chinese
        r"[，,。]\s*只根据",
        r"[，,。]\s*仅根据",
        r"[，,。]\s*只使用",
        r"[，,。]\s*仅使用",
        r"[，,。]\s*不要补充",
        r"[，,。]\s*搜索结果里",
        r"[，,。]\s*检索结果里",
        r"[，,。]\s*请只",

        # English
        r"[,.;]\s*only based on",
        r"[,.;]\s*only use",
        r"[,.;]\s*use only",
        r"[,.;]\s*do not add",
        r"[,.;]\s*don't add",
        r"[,.;]\s*answer only",
    ]

    for pattern in constraint_patterns:
        parts = re.split(
            pattern,
            q,
            maxsplit=1,
            flags=re.IGNORECASE,
        )

        if len(parts) > 1:
            q = parts[0]
            break

    return q.strip(
        " \t\r\n，,。.;：:"
    )

def _expand_rag_query(
    query: str,
) -> str:
    """
    Expand short or ambiguous knowledge-base queries with
    retrieval-oriented terms.

    Keep this deterministic so it adds no extra LLM call.
    """

    q = query.strip()

    normalized = re.sub(
        r"\s+",
        " ",
        q.lower(),
    ).strip(
        " \t\r\n?？。.!！"
    )

    expansions = {
        # GGUF definition-style queries
        "gguf": "GGUF model format llama.cpp",
        "gguf 是什么": "GGUF model format llama.cpp",
        "what is gguf": "GGUF model format llama.cpp",
        "what's gguf": "GGUF model format llama.cpp",
        "explain gguf": "GGUF model format llama.cpp",
    }

    return expansions.get(
        normalized,
        q,
    )

def _build_fast_tool_call(
    query: str,
    detected_tool: str,
    conversation_messages: list[dict] | None = None,
) -> tuple[str, dict] | None:
    """
    Build a deterministic single-tool call.

    If arguments are ambiguous, return None and let ReAct handle it.
    """

    # Multi-step requests belong to ReAct.
    if _is_multi_step_request(query):
        return None

    # Explicit JSON has highest priority.
    explicit_json = _extract_first_json_object(query)

    if explicit_json:
        return detected_tool, explicit_json

    # ---------------------------------------------------------
    # code_exec
    # ---------------------------------------------------------

    if detected_tool == "code_exec":
        expression = _extract_simple_math_expression(
            query,
            conversation_messages,
        )

        if expression:
            return "code_exec", {
                "code": expression,
            }

        return None

    # ---------------------------------------------------------
    # file_list
    # ---------------------------------------------------------

    if detected_tool == "file_list":
        if (
            "workspace" in query.lower()
            or "工作区" in query
            or "有哪些文件" in query
            or "文件列表" in query
            or "列出文件" in query
        ):
            return "file_list", {
                "directory": ".",
            }

        return None

    # ---------------------------------------------------------
    # file_read
    # ---------------------------------------------------------

    if detected_tool == "file_read":
        # First try the current message.
        path = _extract_file_path(query)

        # For follow-ups such as "再读取刚才那个文件",
        # resolve the file from recent conversation history.
        if (
                not path
                and _is_file_read_followup(query)
        ):
            path = _find_recent_file_path(
                conversation_messages,
            )

        if path:
            return "file_read", {
                "path": path,
            }

        # Still ambiguous -> do not guess.
        return None

    # ---------------------------------------------------------
    # file_write
    # ---------------------------------------------------------

    if detected_tool == "file_write":
        path = _extract_file_path(query)

        content_match = re.search(
            r"(?:内容(?:写成|写为|写|为|是)?|"
            r"content(?:\s+is|\s*:)?)[：:\s]*"
            r"[\"“'](.+?)[\"”']",
            query,
            re.IGNORECASE,
        )

        if path and content_match:
            return "file_write", {
                "path": path,
                "content": content_match.group(1),
            }

        return None

    # ---------------------------------------------------------
    # web_search
    # ---------------------------------------------------------

    if detected_tool == "web_search":
        # Context-dependent follow-ups should stay in ReAct.
        if any(
                word in query
                for word in ["刚才", "它", "这个", "继续"]
        ):
            return None

        cleaned = _clean_retrieval_query(
            query,
            "web_search",
        )

        if cleaned:
            return "web_search", {
                "query": cleaned,
                "max_results": 5,
            }

        return None

    # ---------------------------------------------------------
    # query_knowledge_base
    # ---------------------------------------------------------

    if detected_tool == "query_knowledge_base":
        if any(
                word in query
                for word in ["刚才", "它", "这个", "继续"]
        ):
            return None

        # First remove routing / answer-format instructions.
        cleaned = _clean_retrieval_query(
            query,
            "query_knowledge_base",
        )

        if not cleaned:
            return None

        # Then improve retrieval for known short/ambiguous queries.
        expanded = _expand_rag_query(
            cleaned,
        )

        log.info(
            "RAG query: cleaned=%r expanded=%r",
            cleaned,
            expanded,
        )

        return "query_knowledge_base", {
            "query": expanded,
            "k": 5,
        }

    return None

def _build_deterministic_workflow(
    query: str,
) -> dict | None:
    """
    Detect common multi-tool workflows whose steps and arguments
    are already explicit and do not require agent planning.
    """

    q = query.lower().strip()

    # Requests requiring reasoning/transformation should stay in ReAct.
    complex_markers = [
        "总结后",
        "分析后",
        "比较后",
        "筛选后",
        "整理后",
        "after analyzing",
        "after comparing",
        "summarize and",
    ]

    if any(marker in q for marker in complex_markers):
        return None

    path = _extract_file_path(query)

    if not path:
        return None

    web_patterns = [
        r"上网查",
        r"联网查",
        r"网上查",
        r"搜索网页",
        r"搜索一下",
        r"查一下最新",
        r"\bsearch the web\b",
        r"\bsearch online\b",
        r"\blook up online\b",
    ]

    write_patterns = [
        r"写入",
        r"写到",
        r"保存到",
        r"存到",
        r"\bwrite\b.*\bto\b",
        r"\bsave\b.*\bto\b",
    ]

    # ---------------------------------------------------------
    # web_search -> file_write
    # ---------------------------------------------------------

    if (
        _matches_any(q, web_patterns)
        and _matches_any(q, write_patterns)
    ):
        search_query = re.sub(
            r"^(?:帮我)?\s*"
            r"(?:上网查一下|上网查|联网查一下|联网查|"
            r"网上查一下|网上查|搜索一下|搜索网页|查一下最新|"
            r"search the web(?: for)?|"
            r"search online(?: for)?|"
            r"look up online(?: for)?)\s*",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()

        # Keep only the search part before the next explicit step.
        search_query = re.split(
            r"\s*(?:，|,)?\s*"
            r"(?:然后|接着|再把|并且|and then|then)\s*",
            search_query,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        if not search_query:
            return None

        return {
            "kind": "web_search_to_file_write",
            "search_query": search_query,
            "path": path,
        }

    return None

def _decode_tool_payload(
    observation,
) -> dict | None:
    """
    Decode a JSON-object tool response when possible.
    """

    if isinstance(observation, dict):
        return observation

    if not isinstance(observation, str):
        return None

    try:
        payload = json.loads(observation)
    except (json.JSONDecodeError, TypeError):
        return None

    if isinstance(payload, dict):
        return payload

    return None


def _tool_error_message(
    observation,
) -> str | None:
    """
    Return the tool error message when the MCP call
    returned {"error": "..."}.
    """

    payload = _decode_tool_payload(
        observation,
    )

    if not payload:
        return None

    error = payload.get("error")

    if error:
        return str(error).strip()

    return None


def _web_search_has_results(
    observation,
) -> bool:
    """Return True only when web_search has real results."""

    payload = _decode_tool_payload(
        observation,
    )

    if not payload:
        return False

    results = payload.get("results")

    return (
        isinstance(results, list)
        and len(results) > 0
    )

async def _call_tool_raw(
    tool_name: str,
    arguments: dict,
    agent_executor: AgentExecutor,
):
    """Call one MCP tool directly without entering ReAct."""

    tool = next(
        (
            tool
            for tool in agent_executor.tools
            if tool.name == tool_name
        ),
        None,
    )

    if tool is None:
        raise ValueError(
            f"Tool not available: {tool_name}"
        )

    log.info(
        "Workflow step: %s args=%s",
        tool_name,
        arguments,
    )

    return await tool.ainvoke({
        "input": json.dumps(
            arguments,
            ensure_ascii=False,
        )
    })

def _format_web_search_markdown(
    observation,
) -> str:
    """Convert web_search JSON into factual Markdown without an LLM."""

    try:
        if isinstance(observation, str):
            data = json.loads(observation)
        else:
            data = observation
    except (json.JSONDecodeError, TypeError):
        return str(observation)

    if not isinstance(data, dict):
        return str(observation)

    query = str(
        data.get("query", "")
    ).strip()

    results = data.get(
        "results",
        [],
    )

    lines = [
        "# Web Search Results",
        "",
    ]

    if query:
        lines.extend([
            f"Query: {query}",
            "",
        ])

    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        url = str(
            item.get("url", "")
        ).strip()

        snippet = str(
            item.get("snippet", "")
        ).strip()

        lines.append(
            f"## {index}. {title or 'Untitled'}"
        )

        if url:
            lines.append(
                f"- URL: {url}"
            )

        if snippet:
            lines.append(
                f"- Summary: {snippet}"
            )

        lines.append("")

    return "\n".join(lines).strip()

async def _run_deterministic_workflow(
    workflow: dict,
    agent_executor: AgentExecutor,
) -> dict:
    """
    Execute an explicit multi-tool workflow without ReAct.
    """

    kind = workflow.get("kind")

    # ---------------------------------------------------------
    # web_search -> file_write
    # ---------------------------------------------------------

    if kind == "web_search_to_file_write":
        search_query = workflow["search_query"]
        path = workflow["path"]

        # Step 1: search once
        search_result = await _call_tool_raw(
            "web_search",
            {
                "query": search_query,
                "max_results": 5,
            },
            agent_executor,
        )

        search_error = _tool_error_message(
            search_result,
        )

        if search_error:
            log.warning(
                "Workflow web_search failed: %s",
                search_error,
            )

            return {
                "output": (
                    "Web search failed, so the output "
                    "file was not written. "
                    f"Error: {search_error}"
                ),
                "intermediate_steps": [
                    {
                        "action": "web_search",
                        "observation": str(search_result),
                    }
                ],
            }

        if not _web_search_has_results(
            search_result,
        ):
            log.warning(
                "Workflow web_search returned no usable results"
            )

            return {
                "output": (
                    "Web search returned no usable results, "
                    "so the output file was not written."
                ),
                "intermediate_steps": [
                    {
                        "action": "web_search",
                        "observation": str(search_result),
                    }
                ],
            }

        # Step 2: deterministic formatting
        content = _format_web_search_markdown(
            search_result,
        )

        # Step 3: write once
        write_result = await _call_tool_raw(
            "file_write",
            {
                "path": path,
                "content": content,
            },
            agent_executor,
        )

        write_error = _tool_error_message(
            write_result,
        )

        if write_error:
            log.warning(
                "Workflow file_write failed: %s",
                write_error,
            )

            return {
                "output": (
                    "Web search succeeded, but writing "
                    f"`{path}` failed. "
                    f"Error: {write_error}"
                ),
                "intermediate_steps": [
                    {
                        "action": "web_search",
                        "observation": str(search_result),
                    },
                    {
                        "action": "file_write",
                        "observation": str(write_result),
                    },
                ],
            }

        return {
            "output": (
                f"已完成搜索并将结果写入 `{path}`。"
            ),
            "intermediate_steps": [
                {
                    "action": "web_search",
                    "observation": str(search_result),
                },
                {
                    "action": "file_write",
                    "observation": str(write_result),
                },
            ],
        }

    raise ValueError(
        f"Unsupported deterministic workflow: {kind}"
    )

def _should_use_tools(query: str) -> bool:
    """Determine whether this request should enter the ReAct tool agent."""

    if _is_openwebui_internal_request(query):
        return False

    return _detect_tool_intent(query) is not None


def _get_explicit_tool_request(
    query: str,
    tool_names: list[str],
) -> str | None:
    """
    Detect only tools that the user explicitly asked to use.

    Do not treat inferred routing intent as an explicit tool request.
    """

    q = query.lower().strip()

    # Explicit tool-name requests.
    for name in tool_names:
        tool_name = name.lower()

        patterns = [
            rf"\buse\s+(?:the\s+)?{re.escape(tool_name)}\b",
            rf"\bcall\s+(?:the\s+)?{re.escape(tool_name)}\b",
            rf"\brun\s+(?:the\s+)?{re.escape(tool_name)}\b",

            rf"(?:使用|调用|运行)\s*{re.escape(tool_name)}",
        ]

        if _matches_any(q, patterns):
            return name

    # Natural-language explicit alias for code_exec.
    if (
        "code_exec" in tool_names
        and _matches_any(
            q,
            [
                r"用计算器",
                r"调用计算器",
                r"使用计算器",
            ],
        )
    ):
        return "code_exec"

    return None

def _is_openwebui_background_task(query: str) -> bool:
    """Detect Open WebUI metadata/background requests."""
    q = query.strip().lower()

    if not q.startswith("### task:"):
        return False

    markers = [
        "suggest 3-5 relevant follow-up questions",
        "generate 1-3 broad tags",
        "generate a concise title",
        "generate a concise title summarizing",
    ]

    return any(marker in q for marker in markers)

async def _run_direct_chat(
    query: str,
    conversation_messages: list[dict] | None = None,
) -> dict:
    """Handle normal multi-turn conversation without ReAct."""

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.1,
        timeout=120,
    )

    messages = [
        SystemMessage(
            content=(
                "You are a helpful local AI assistant. "
                "Use previous messages in this conversation as context. "
                "If the user gives you information to retain for later "
                "messages in this conversation, remember and use it. "
                "Follow the user's instructions carefully."
            )
        )
    ]

    # Add actual previous conversation turns.
    for message in conversation_messages or []:
        role = message.get("role")
        content = message.get("content", "")

        if role == "user":
            messages.append(
                HumanMessage(content=content)
            )

        elif role == "assistant":
            messages.append(
                AIMessage(content=content)
            )

    # Current user request.
    messages.append(
        HumanMessage(content=query)
    )

    response = await llm.ainvoke(messages)

    return {
        "output": response.content,
        "intermediate_steps": [],
    }

async def _run_fast_tool(
    tool_name: str,
    arguments: dict,
    query: str,
    agent_executor: AgentExecutor,
) -> dict:
    """Execute one deterministic MCP tool without entering ReAct."""

    tool = next(
        (
            tool
            for tool in agent_executor.tools
            if tool.name == tool_name
        ),
        None,
    )

    if tool is None:
        raise ValueError(
            f"Tool not available: {tool_name}"
        )

    log.info(
        "Fast Path: %s args=%s",
        tool_name,
        arguments,
    )

    # mcp_adapter exposes one string input containing JSON.
    observation = await tool.ainvoke({
        "input": json.dumps(
            arguments,
            ensure_ascii=False,
        )
    })

    error = _tool_error_message(
        observation,
    )

    if error:
        log.warning(
            "Fast Path tool failed: %s: %s",
            tool_name,
            error,
        )

        return {
            "output": (
                f"Tool `{tool_name}` failed: {error}"
            ),
            "intermediate_steps": [
                {
                    "action": tool_name,
                    "observation": str(observation),
                }
            ],
        }

    if (
        tool_name == "web_search"
        and not _web_search_has_results(observation)
    ):
        log.warning(
            "web_search returned no usable results"
        )

        return {
            "output": (
                "Web search completed but returned "
                "no usable results."
            ),
            "intermediate_steps": [
                {
                    "action": tool_name,
                    "observation": str(observation),
                }
            ],
        }
    # ---------------------------------------------------------
    # code_exec
    # ---------------------------------------------------------

    if tool_name == "code_exec":
        output = str(observation).strip()

    # ---------------------------------------------------------
    # file_read
    # ---------------------------------------------------------

    elif tool_name == "file_read":
        try:
            data = json.loads(observation)

            if isinstance(data, dict) and "content" in data:
                output = str(data["content"])
            else:
                output = str(observation)

        except (json.JSONDecodeError, TypeError):
            output = str(observation)

    # ---------------------------------------------------------
    # file_write
    # ---------------------------------------------------------

    elif tool_name == "file_write":
        try:
            data = json.loads(observation)

            if isinstance(data, dict) and data.get("error"):
                output = str(data["error"])
            else:
                output = (
                    f"File written successfully: "
                    f"{arguments.get('path', '')}"
                )

        except (json.JSONDecodeError, TypeError):
            output = str(observation)

    # ---------------------------------------------------------
    # file_list
    # ---------------------------------------------------------

    elif tool_name == "file_list":
        try:
            data = json.loads(observation)

            output = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )

        except (json.JSONDecodeError, TypeError):
            output = str(observation)

    # ---------------------------------------------------------
    # web_search / RAG
    #
    # Tool selection does not need ReAct, but the raw search
    # results still need one lightweight LLM synthesis step.
    # ---------------------------------------------------------

    elif tool_name in {
        "web_search",
        "query_knowledge_base",
    }:
        llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.1,
            timeout=120,
        )

        messages = [
            SystemMessage(
                content=(
                    "A tool has already executed successfully. "
                    "Answer the user's request using the tool result. "
                    "Do not call any tools. "
                    "Do not invent facts. "
                    "Preserve source names and URLs when available."
                )
            ),
            HumanMessage(
                content=(
                    f"User request:\n{query}\n\n"
                    f"Tool result:\n{observation}"
                )
            ),
        ]

        response = await llm.ainvoke(messages)

        output = str(response.content).strip()

    else:
        output = str(observation)

    return {
        "output": output,
        "intermediate_steps": [
            {
                "action": tool_name,
                "observation": str(observation),
            }
        ],
    }

async def _recover_from_tool_steps(
    query: str,
    steps: list,
) -> str | None:
    """
    Recover a final answer when a tool succeeded but
    the ReAct parser failed to produce a Final Answer.
    """

    if not steps:
        return None

    # ---------------------------------------------------------
    # Special case: code_exec
    # Return exact stdout whenever possible.
    # ---------------------------------------------------------

    last_action, last_observation = steps[-1]

    tool_name = getattr(
        last_action,
        "tool",
        "",
    )

    if tool_name == "code_exec":
        try:
            if isinstance(last_observation, str):
                data = json.loads(last_observation)
            else:
                data = last_observation
        except (json.JSONDecodeError, TypeError):
            data = None

        if isinstance(data, dict):
            returncode = data.get("returncode")
            stdout = str(
                data.get("stdout", "")
            ).strip()

            if returncode == 0 and stdout:
                # If user explicitly asked for only the result,
                # return the tool output directly.
                lowered = query.lower()

                if (
                    "result only" in lowered
                    or "reply with the result only" in lowered
                ):
                    return stdout

                return f"The result is {stdout}."

    # ---------------------------------------------------------
    # Generic recovery for other successful tools.
    # Do NOT enter ReAct again.
    # ---------------------------------------------------------

    observations = []

    for action, observation in steps:
        observations.append(
            f"Tool: {getattr(action, 'tool', 'unknown')}\n"
            f"Observation: {observation}"
        )

    observation_text = "\n\n".join(
        observations
    )

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.1,
        timeout=120,
    )

    messages = [
        SystemMessage(
            content=(
                "You are formatting the final answer after tools "
                "have already executed. "
                "Do not call any tools. "
                "Treat the tool observations as authoritative. "
                "Do not recompute or change numerical results. "
                "Answer the user's original request directly."
            )
        ),
        HumanMessage(
            content=(
                f"Original user request:\n{query}\n\n"
                f"Tool observations:\n{observation_text}"
            )
        ),
    ]

    response = await llm.ainvoke(messages)

    return str(response.content).strip()

async def run_agent(
    query: str,
    agent_executor: AgentExecutor,
    chat_history: str = "",
    conversation_messages: list[dict] | None = None,
) -> dict:
    if _is_openwebui_background_task(query):
        log.info("Routing Open WebUI background task to direct chat")

        return await _run_direct_chat(
            query,
            conversation_messages,
        )

    # ---------------------------------------------------------
    # Deterministic multi-tool workflow
    # ---------------------------------------------------------

    workflow = _build_deterministic_workflow(
        query,
    )

    if workflow is not None:
        log.info(
            "Routing deterministic workflow: %s",
            workflow["kind"],
        )

        return await _run_deterministic_workflow(
            workflow,
            agent_executor,
        )
    # ---------------------------------------------------------
    # 1. Detect tool intent
    # ---------------------------------------------------------

    detected_tool = _detect_contextual_tool_intent(
        query,
        conversation_messages,
    )

    # ---------------------------------------------------------
    # 2. No tool -> Direct Chat
    # ---------------------------------------------------------

    if detected_tool is None:
        log.info(
            "Routing request to direct chat"
        )

        return await _run_direct_chat(
            query,
            conversation_messages,
        )

    # ---------------------------------------------------------
    # 3. Deterministic single-tool request -> Fast Path
    # ---------------------------------------------------------

    fast_call = _build_fast_tool_call(
        query,
        detected_tool,
        conversation_messages,
    )

    if fast_call is not None:
        tool_name, arguments = fast_call

        return await _run_fast_tool(
            tool_name,
            arguments,
            query,
            agent_executor,
        )

    # ---------------------------------------------------------
    # 4. Ambiguous / multi-step request -> ReAct
    # ---------------------------------------------------------

    is_multi_step = _is_multi_step_request(query)

    if is_multi_step:
        log.info(
            "Routing multi-step request to ReAct agent"
        )
    else:
        log.info(
            "Routing ambiguous tool request to ReAct agent: %s",
            detected_tool,
        )

    tool_names = [
        tool.name
        for tool in agent_executor.tools
    ]

    requested_tool = _get_explicit_tool_request(
        query,
        tool_names,
    )

    # First attempt
    result = await agent_executor.ainvoke({
        "input": query,
        "ollama_model": settings.ollama_model,
        "chat_history": chat_history,
    })

    steps = result.get(
        "intermediate_steps",
        [],
    )

    used_tools = [
        getattr(step[0], "tool", "")
        for step in steps
    ]

    # If the user explicitly requested a tool but
    # the model ignored it, retry once.
    if (
        requested_tool
        and requested_tool not in used_tools
    ):
        log.warning(
            "Requested tool '%s' was not used. "
            "Retrying once.",
            requested_tool,
        )

        retry_query = (
            f"The user explicitly requested the "
            f"`{requested_tool}` tool. "
            f"You MUST call `{requested_tool}` before "
            f"giving the Final Answer. "
            f"Do not answer from memory.\n\n"
            f"Original request:\n{query}"
        )

        result = await agent_executor.ainvoke({
            "input": retry_query,
            "ollama_model": settings.ollama_model,
            "chat_history": chat_history,
        })

        steps = result.get(
            "intermediate_steps",
            [],
        )

        used_tools = [
            getattr(step[0], "tool", "")
            for step in steps
        ]

        # Still ignored after retry:
        # do not pretend that the tool was used.
        if requested_tool not in used_tools:
            return {
                "output": (
                    f"Error: requested tool "
                    f"`{requested_tool}` was not executed."
                ),
                "intermediate_steps": [],
            }

    output = result.get(
        "output",
        "",
    )

    # A tool may have executed successfully while the small model
    # subsequently failed to follow the ReAct Final Answer format.
    if (
        steps
        and (
            not output.strip()
            or "Agent stopped due to iteration limit" in output
            or "Agent stopped due to time limit" in output
        )
    ):
        log.warning(
            "Agent stopped after successful tool execution. "
            "Recovering final answer from tool observations."
        )

        recovered = await _recover_from_tool_steps(
            query,
            steps,
        )

        if recovered:
            output = recovered

    return {
        "output": output,
        "intermediate_steps": [
            {
                "action": getattr(
                    step[0],
                    "tool",
                    str(step[0]),
                ),
                "observation": str(step[1]),
            }
            for step in steps
        ],
    }

