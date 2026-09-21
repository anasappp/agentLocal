import argparse
import json
import math
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "live_cases.json"
REPORT_DIR = ROOT / "reports"

AGENT_URL = (
    "http://127.0.0.1:8000/v1/chat/completions"
)

MODEL = "local-agent"


def extract_content(payload: dict) -> str:
    choices = payload.get("choices", [])

    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    return str(content).strip()


def extract_tokens(payload: dict) -> int | None:
    usage = payload.get("usage")

    if not isinstance(usage, dict):
        return None

    total = usage.get("total_tokens")

    if isinstance(total, int):
        return total

    return None


def check_output(
    output: str,
    check: dict,
) -> tuple[bool, str]:
    check_type = check.get(
        "type",
        "not_empty",
    )

    lowered = output.lower()

    if check_type == "not_empty":
        passed = bool(output.strip())

        return (
            passed,
            "non-empty output"
            if passed
            else "empty output",
        )

    values = [
        str(value)
        for value in check.get(
            "values",
            [],
        )
    ]

    if check_type == "all_contains":
        missing = [
            value
            for value in values
            if value.lower() not in lowered
        ]

        if missing:
            return (
                False,
                f"missing: {missing}",
            )

        return True, "all expected values found"

    if check_type == "any_contains":
        matched = [
            value
            for value in values
            if value.lower() in lowered
        ]

        if matched:
            return (
                True,
                f"matched: {matched[0]}",
            )

        return (
            False,
            f"none matched: {values}",
        )

    return (
        False,
        f"unknown check type: {check_type}",
    )


def percentile(
    values: list[float],
    p: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil(p * len(ordered)) - 1,
        ),
    )

    return ordered[index]


def call_agent(
    client: httpx.Client,
    messages: list[dict],
) -> tuple[str, float, int | None]:
    started = time.perf_counter()

    response = client.post(
        AGENT_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
        },
    )

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000

    response.raise_for_status()

    payload = response.json()

    return (
        extract_content(payload),
        elapsed_ms,
        extract_tokens(payload),
    )


def run_case(
    client: httpx.Client,
    case: dict,
) -> dict:
    messages = []
    total_latency_ms = 0.0
    total_tokens = 0
    token_data_available = False
    final_output = ""

    try:
        for turn in case["turns"]:
            messages.append({
                "role": "user",
                "content": turn,
            })

            (
                output,
                latency_ms,
                tokens,
            ) = call_agent(
                client,
                messages,
            )

            total_latency_ms += latency_ms

            if tokens is not None:
                token_data_available = True
                total_tokens += tokens

            final_output = output

            messages.append({
                "role": "assistant",
                "content": output,
            })

        passed, reason = check_output(
            final_output,
            case.get(
                "check",
                {"type": "not_empty"},
            ),
        )

        return {
            "id": case["id"],
            "category": case["category"],
            "external": bool(
                case.get("external", False)
            ),
            "passed": passed,
            "reason": reason,
            "latency_ms": round(
                total_latency_ms,
                2,
            ),
            "tokens": (
                total_tokens
                if token_data_available
                else None
            ),
            "output": final_output,
            "error": None,
        }

    except Exception as exc:
        return {
            "id": case["id"],
            "category": case["category"],
            "external": bool(
                case.get("external", False)
            ),
            "passed": False,
            "reason": "request failed",
            "latency_ms": round(
                total_latency_ms,
                2,
            ),
            "tokens": (
                total_tokens
                if token_data_available
                else None
            ),
            "output": final_output,
            "error": repr(exc),
        }


def build_report(
    results: list[dict],
) -> str:
    core = [
        result
        for result in results
        if not result["external"]
    ]

    passed = sum(
        result["passed"]
        for result in core
    )

    total = len(core)

    success_rate = (
        passed / total * 100
        if total
        else 0.0
    )

    latencies = [
        result["latency_ms"]
        for result in core
        if result["error"] is None
    ]

    avg_latency = (
        sum(latencies) / len(latencies)
        if latencies
        else 0.0
    )

    p50 = percentile(
        latencies,
        0.50,
    )

    p95 = percentile(
        latencies,
        0.95,
    )

    category_results = defaultdict(list)

    for result in core:
        category_results[
            result["category"]
        ].append(result)

    lines = [
        "# Live Agent Evaluation",
        "",
        (
            "- Generated: "
            f"{datetime.now().isoformat(timespec='seconds')}"
        ),
        f"- Core cases: {total}",
        f"- Passed: {passed}",
        f"- Failed: {total - passed}",
        (
            "- Task Success Rate: "
            f"{success_rate:.2f}%"
        ),
        (
            "- Average latency: "
            f"{avg_latency:.2f} ms"
        ),
        f"- P50 latency: {p50:.2f} ms",
        f"- P95 latency: {p95:.2f} ms",
        "",
        "## Category Success",
        "",
    ]

    for category, items in sorted(
        category_results.items()
    ):
        category_passed = sum(
            item["passed"]
            for item in items
        )

        category_total = len(items)

        lines.append(
            f"- {category}: "
            f"{category_passed}/"
            f"{category_total} "
            f"({category_passed / category_total * 100:.2f}%)"
        )

    lines.extend([
        "",
        "## Case Results",
        "",
        "| Case | Category | Result | Latency | Tokens | Reason |",
        "|---|---|---|---:|---:|---|",
    ])

    for result in results:
        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        if result["external"]:
            status += " (external)"

        tokens = (
            str(result["tokens"])
            if result["tokens"] is not None
            else "-"
        )

        reason = str(
            result["reason"]
        ).replace(
            "|",
            "/",
        )

        lines.append(
            "| "
            f"{result['id']} | "
            f"{result['category']} | "
            f"{status} | "
            f"{result['latency_ms']:.2f} ms | "
            f"{tokens} | "
            f"{reason} |"
        )

    failures = [
        result
        for result in results
        if not result["passed"]
    ]

    lines.extend([
        "",
        "## Failure Details",
        "",
    ])

    if not failures:
        lines.append(
            "No failures."
        )

    for result in failures:
        output = (
            result["output"]
            or ""
        ).replace(
            "```",
            "'''",
        )

        lines.extend([
            f"### {result['id']}",
            "",
            f"- Category: `{result['category']}`",
            f"- Reason: `{result['reason']}`",
            f"- Error: `{result['error']}`",
            "",
            "```text",
            output[:1500],
            "```",
            "",
        ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Also run unstable external-provider cases.",
    )

    args = parser.parse_args()

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cases = json.loads(
        CASES_PATH.read_text(
            encoding="utf-8"
        )
    )

    selected_cases = [
        case
        for case in cases
        if (
            args.include_external
            or not case.get(
                "external",
                False,
            )
        )
    ]

    print(
        f"Running {len(selected_cases)} "
        "live agent cases..."
    )

    results = []

    with httpx.Client(
        timeout=180.0,
    ) as client:

        # Warm up the chat model.
        print("Warm-up...")

        try:
            call_agent(
                client,
                [{
                    "role": "user",
                    "content": (
                        "Reply with OK only."
                    ),
                }],
            )
        except Exception as exc:
            print(
                "Warm-up warning:",
                repr(exc),
            )

        for case in selected_cases:
            print(
                f"[RUN] {case['id']}"
            )

            result = run_case(
                client,
                case,
            )

            results.append(result)

            status = (
                "PASS"
                if result["passed"]
                else "FAIL"
            )

            print(
                f"[{status}] "
                f"{case['id']} "
                f"{result['latency_ms']:.2f} ms"
            )

    core_results = [
        result
        for result in results
        if not result["external"]
    ]

    passed = sum(
        result["passed"]
        for result in core_results
    )

    total = len(core_results)

    success_rate = (
        passed / total * 100
        if total
        else 0.0
    )

    print()
    print(
        "Core Task Success: "
        f"{passed}/{total} "
        f"({success_rate:.2f}%)"
    )

    json_path = (
        REPORT_DIR
        / "live_eval_latest.json"
    )

    md_path = (
        REPORT_DIR
        / "live_eval_latest.md"
    )

    json_path.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md_path.write_text(
        build_report(results),
        encoding="utf-8",
    )

    print(
        f"JSON report: {json_path}"
    )

    print(
        f"Markdown report: {md_path}"
    )


if __name__ == "__main__":
    main()