import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from agent.agent import (
    _build_deterministic_workflow,
    _build_fast_tool_call,
    _detect_contextual_tool_intent,
    _is_openwebui_background_task,
)

try:
    from agent.agent import _is_multi_step_request
except ImportError:
    def _is_multi_step_request(query: str) -> bool:
        return False


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "cases.json"
REPORT_DIR = ROOT / "reports"


def classify_route(case: dict) -> dict:
    query = case["query"]
    history = case.get("history", [])

    # 1. Open WebUI metadata/background requests
    if _is_openwebui_background_task(query):
        return {
            "route": "background_direct",
            "tool": None,
            "workflow": None,
        }

    # 2. Fixed deterministic multi-tool workflow
    workflow = _build_deterministic_workflow(query)

    if workflow is not None:
        return {
            "route": "workflow",
            "tool": None,
            "workflow": workflow.get("kind"),
        }

    # 3. Detect current/contextual tool intent
    detected_tool = _detect_contextual_tool_intent(
        query,
        history,
    )

    if detected_tool is None:
        return {
            "route": "direct",
            "tool": None,
            "workflow": None,
        }

    # 4. Complex multi-step requests stay in ReAct
    if _is_multi_step_request(query):
        return {
            "route": "react",
            "tool": detected_tool,
            "workflow": None,
        }

    # 5. Try deterministic single-tool Fast Path
    fast_call = _build_fast_tool_call(
        query,
        detected_tool,
        history,
    )

    if fast_call is not None:
        tool_name, _arguments = fast_call

        return {
            "route": "fast_path",
            "tool": tool_name,
            "workflow": None,
        }

    # 6. Intent exists, but arguments/planning are ambiguous
    return {
        "route": "react",
        "tool": detected_tool,
        "workflow": None,
    }


def evaluate_case(case: dict) -> dict:
    actual = classify_route(case)

    route_ok = (
        actual["route"]
        == case["expected_route"]
    )

    tool_ok = True
    expected_tool = case.get("expected_tool")

    if expected_tool is not None:
        tool_ok = (
            actual["tool"]
            == expected_tool
        )

    workflow_ok = True
    expected_workflow = case.get(
        "expected_workflow"
    )

    if expected_workflow is not None:
        workflow_ok = (
            actual["workflow"]
            == expected_workflow
        )

    passed = (
        route_ok
        and tool_ok
        and workflow_ok
    )

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_route": case["expected_route"],
        "actual_route": actual["route"],
        "expected_tool": expected_tool,
        "actual_tool": actual["tool"],
        "expected_workflow": expected_workflow,
        "actual_workflow": actual["workflow"],
        "passed": passed,
    }


def build_markdown(
    results: list[dict],
) -> str:
    total = len(results)
    passed = sum(
        result["passed"]
        for result in results
    )

    accuracy = (
        passed / total * 100
        if total
        else 0.0
    )

    route_counts = Counter(
        result["actual_route"]
        for result in results
    )

    lines = [
        "# Agent Router Evaluation",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Total cases: {total}",
        f"- Passed: {passed}",
        f"- Failed: {total - passed}",
        f"- Routing accuracy: {accuracy:.2f}%",
        "",
        "## Route Distribution",
        "",
    ]

    for route, count in sorted(
        route_counts.items()
    ):
        ratio = (
            count / total * 100
            if total
            else 0.0
        )

        lines.append(
            f"- {route}: {count} ({ratio:.2f}%)"
        )

    lines.extend([
        "",
        "## Case Results",
        "",
        "| Case | Expected | Actual | Target | Result |",
        "|---|---|---|---|---|",
    ])

    for result in results:
        expected_target = (
            result["expected_tool"]
            or result["expected_workflow"]
            or "-"
        )

        actual_target = (
            result["actual_tool"]
            or result["actual_workflow"]
            or "-"
        )

        target = (
            f"{expected_target} → "
            f"{actual_target}"
        )

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        lines.append(
            "| "
            f"{result['id']} | "
            f"{result['expected_route']} | "
            f"{result['actual_route']} | "
            f"{target} | "
            f"{status} |"
        )

    failures = [
        result
        for result in results
        if not result["passed"]
    ]

    lines.extend([
        "",
        "## Failures",
        "",
    ])

    if not failures:
        lines.append(
            "No routing failures."
        )
    else:
        for result in failures:
            lines.extend([
                f"### {result['id']}",
                "",
                f"- Query: `{result['query']}`",
                (
                    "- Expected: "
                    f"`{result['expected_route']}` / "
                    f"`{result['expected_tool'] or result['expected_workflow']}`"
                ),
                (
                    "- Actual: "
                    f"`{result['actual_route']}` / "
                    f"`{result['actual_tool'] or result['actual_workflow']}`"
                ),
                "",
            ])

    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cases = json.loads(
        CASES_PATH.read_text(
            encoding="utf-8"
        )
    )

    results = [
        evaluate_case(case)
        for case in cases
    ]

    passed = sum(
        result["passed"]
        for result in results
    )

    total = len(results)

    print(
        f"Router Eval: "
        f"{passed}/{total} passed "
        f"({passed / total * 100:.2f}%)"
    )

    for result in results:
        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print(
            f"[{status}] "
            f"{result['id']}: "
            f"{result['expected_route']} "
            f"-> {result['actual_route']}"
        )

    json_path = (
        REPORT_DIR
        / "router_eval_latest.json"
    )

    md_path = (
        REPORT_DIR
        / "router_eval_latest.md"
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
        build_markdown(results),
        encoding="utf-8",
    )

    print()
    print(
        f"JSON report: {json_path}"
    )
    print(
        f"Markdown report: {md_path}"
    )


if __name__ == "__main__":
    main()