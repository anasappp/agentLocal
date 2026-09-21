import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

from agent.repo_debug_workflow import (
    run_repo_debug_workflow,
)


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

SOURCE_PATH = (
    ROOT
    / "workspace"
    / "hero_repo"
    / "calculator.py"
)

RESULT_JSON = (
    ROOT
    / "eval"
    / "reports"
    / "repo_debug_workflow_latest.json"
)

RESULT_MD = (
    ROOT
    / "eval"
    / "reports"
    / "repo_debug_workflow_latest.md"
)


async def main() -> None:
    # -----------------------------------------------------
    # 1. Reset demo repository
    # -----------------------------------------------------

    subprocess.run(
        [
            sys.executable,
            str(SETUP_SCRIPT),
        ],
        cwd=ROOT,
        check=True,
    )

    print(
        "Hero repository reset."
    )

    # -----------------------------------------------------
    # 2. Run deterministic debugging workflow
    # -----------------------------------------------------

    started = time.perf_counter()

    result = await run_repo_debug_workflow(
        repo_dir="hero_repo",
        test_file="test_calculator.py",
        source_files=[
            "calculator.py",
        ],
        report_path="hero_debug_report.md",
    )

    latency_ms = (
        time.perf_counter()
        - started
    ) * 1000

    # -----------------------------------------------------
    # 3. Verify generated report
    # -----------------------------------------------------

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

    structure_ok = all(
        section in report_text
        for section in [
            "Test Result",
            "Root Cause",
            "Evidence",
            "Recommended Fix",
        ]
    )

    diagnosis = result.get(
        "diagnosis",
        {},
    )

    diagnosed_file = str(
        diagnosis.get(
            "root_cause_file",
            "",
        )
    )

    root_cause_text = str(
        diagnosis.get(
            "root_cause",
            "",
        )
    ).lower()

    diagnosis_ok = (
        diagnosed_file == "calculator.py"
        and any(
            marker in root_cause_text
            for marker in [
                "a - b",
                "subtract",
                "subtraction",
                "减法",
                "相减",
            ]
        )
    )

    evidence_ok = (
        "expected 12"
        in report_lower
        and
        "got 2"
        in report_lower
    )

    # -----------------------------------------------------
    # 4. Verify Agent did not modify source code
    # -----------------------------------------------------

    source_text = (
        SOURCE_PATH.read_text(
            encoding="utf-8",
        )
    )

    source_unchanged = (
        "return a - b"
        in source_text
    )

    # -----------------------------------------------------
    # 5. Final workflow evaluation
    # -----------------------------------------------------

    success = all([
        report_exists,
        structure_ok,
        diagnosis_ok,
        evidence_ok,
        source_unchanged,
    ])

    summary = {
        "success": success,
        "latency_ms": round(
            latency_ms,
            2,
        ),
        "report_exists": report_exists,
        "structure_ok": structure_ok,
        "diagnosis_ok": diagnosis_ok,
        "evidence_ok": evidence_ok,
        "source_unchanged": source_unchanged,
        "diagnosis": diagnosis,
        "files_read": result.get(
            "files_read",
            [],
        ),
        "test_result": result.get(
            "test_result",
            {},
        ),
    }

    # -----------------------------------------------------
    # 6. Save machine-readable result
    # -----------------------------------------------------

    RESULT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULT_JSON.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -----------------------------------------------------
    # 7. Save human-readable result
    # -----------------------------------------------------

    markdown = (
        "# Repository Debug Workflow Evaluation\n\n"
        f"- Success: {success}\n"
        f"- Latency: {latency_ms:.2f} ms\n"
        f"- Report generated: {report_exists}\n"
        f"- Report structure valid: {structure_ok}\n"
        f"- Root cause correct: {diagnosis_ok}\n"
        f"- Runtime evidence present: {evidence_ok}\n"
        f"- Source code unchanged: {source_unchanged}\n\n"
        "## Diagnosis\n\n"
        f"Root cause file: `{diagnosed_file}`\n\n"
        f"{diagnosis.get('root_cause', '')}\n\n"
        "## Evidence\n\n"
        f"{diagnosis.get('evidence', '')}\n\n"
        "## Recommended Fix\n\n"
        f"{diagnosis.get('recommended_fix', '')}\n\n"
        "## Generated Debugging Report\n\n"
        f"{report_text}\n"
    )

    RESULT_MD.write_text(
        markdown,
        encoding="utf-8",
    )

    # -----------------------------------------------------
    # 8. Console result
    # -----------------------------------------------------

    print()
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()

    print(
        "Repo Debug Workflow:",
        "PASS" if success else "FAIL",
    )

    print(
        f"Latency: "
        f"{latency_ms:.2f} ms"
    )

    print(
        f"Report: "
        f"{REPORT_PATH}"
    )

    print(
        f"Eval report: "
        f"{RESULT_MD}"
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )