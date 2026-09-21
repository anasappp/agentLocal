import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]

SETUP_SCRIPT = (
    ROOT
    / "scripts"
    / "setup_hero_demo.py"
)

REPORT_PATH = (
    ROOT
    / "workspace"
    / "hero_debug_report.md"
)

CALCULATOR_PATH = (
    ROOT
    / "workspace"
    / "hero_repo"
    / "calculator.py"
)

RESULT_JSON = (
    ROOT
    / "eval"
    / "reports"
    / "hero_demo_latest.json"
)

RESULT_MD = (
    ROOT
    / "eval"
    / "reports"
    / "hero_demo_latest.md"
)

AGENT_URL = (
    "http://127.0.0.1:8000"
    "/v1/chat/completions"
)


PROMPT = """
请完成一个仓库级调试任务。

目标仓库位于工作区的 hero_repo。

请完成以下步骤：

1. 查看 hero_repo 中有哪些文件。
2. 阅读：
   - hero_repo/README.md
   - hero_repo/calculator.py
   - hero_repo/test_calculator.py
3. 必须实际运行测试，不能只根据源码猜结果。

运行测试时，请使用 Python 执行下面这种逻辑：

import subprocess
import sys

result = subprocess.run(
    [sys.executable, "test_calculator.py"],
    cwd="workspace/hero_repo",
    capture_output=True,
    text=True,
    timeout=20,
)

print("test_returncode =", result.returncode)
print("test_stdout =", result.stdout)
print("test_stderr =", result.stderr)

4. 根据真实测试输出定位根因。
5. 不要修改 calculator.py 或任何源代码。
6. 将诊断报告保存到：
   hero_debug_report.md

报告必须包含以下四个标题：

Test Result
Root Cause
Evidence
Recommended Fix

Evidence 中必须记录真实测试失败信息，
包括 expected 12 和 got 2。

完成后告诉我报告已经生成。
""".strip()


def reset_fixture() -> None:
    subprocess.run(
        [
            sys.executable,
            str(SETUP_SCRIPT),
        ],
        cwd=ROOT,
        check=True,
    )


def extract_answer(
    payload: dict,
) -> str:
    choices = payload.get(
        "choices",
        [],
    )

    if not choices:
        return ""

    return str(
        choices[0]
        .get("message", {})
        .get("content", "")
    ).strip()


def main() -> None:
    # Every run starts from the same known buggy repo.
    reset_fixture()

    started = time.perf_counter()

    with httpx.Client(
        timeout=180.0,
    ) as client:
        response = client.post(
            AGENT_URL,
            json={
                "model": "local-agent",
                "messages": [
                    {
                        "role": "user",
                        "content": PROMPT,
                    }
                ],
                "stream": False,
            },
        )

        response.raise_for_status()

        payload = response.json()

    latency_ms = (
        time.perf_counter()
        - started
    ) * 1000

    answer = extract_answer(
        payload,
    )

    report_exists = (
        REPORT_PATH.exists()
    )

    report_text = ""

    if report_exists:
        report_text = (
            REPORT_PATH.read_text(
                encoding="utf-8",
            )
        )

    report_lower = (
        report_text.lower()
    )

    required_sections = [
        "Test Result",
        "Root Cause",
        "Evidence",
        "Recommended Fix",
    ]

    structure_ok = all(
        section in report_text
        for section in required_sections
    )

    diagnosis_ok = any(
        marker in report_lower
        for marker in [
            "return a - b",
            "subtraction",
            "减法",
        ]
    )

    evidence_ok = (
        "expected 12"
        in report_lower
        and
        "got 2"
        in report_lower
    )

    source_text = (
        CALCULATOR_PATH.read_text(
            encoding="utf-8",
        )
    )

    source_unchanged = (
        "return a - b"
        in source_text
    )

    success = all([
        report_exists,
        structure_ok,
        diagnosis_ok,
        evidence_ok,
        source_unchanged,
    ])

    result = {
        "success": success,
        "latency_ms": round(
            latency_ms,
            2,
        ),
        "report_exists": report_exists,
        "structure_ok": structure_ok,
        "diagnosis_ok": diagnosis_ok,
        "evidence_ok": evidence_ok,
        "source_unchanged": (
            source_unchanged
        ),
        "agent_answer": answer,
    }

    RESULT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULT_JSON.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    RESULT_MD.write_text(
        f"""# Repository Engineering Hero Demo

- Success: {success}
- Latency: {latency_ms:.2f} ms
- Report generated: {report_exists}
- Report structure: {structure_ok}
- Root cause identified: {diagnosis_ok}
- Runtime evidence captured: {evidence_ok}
- Source code unchanged: {source_unchanged}

## Agent Final Answer

{answer}

## Generated Debugging Report

{report_text}
""",
        encoding="utf-8",
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()

    print(
        "Hero Demo:",
        "PASS" if success else "FAIL",
    )

    print(
        f"Latency: "
        f"{latency_ms:.2f} ms"
    )

    print(
        f"Report: {REPORT_PATH}"
    )

    print(
        f"Eval report: {RESULT_MD}"
    )


if __name__ == "__main__":
    main()