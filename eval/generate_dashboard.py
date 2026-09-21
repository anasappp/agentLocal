import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"

ROUTER_REPORT = (
    REPORT_DIR
    / "router_eval_latest.json"
)

LIVE_REPORT = (
    REPORT_DIR
    / "live_eval_latest.json"
)

REACT_HERO_CANDIDATES = [
    REPORT_DIR
    / "hero_demo_react_baseline.json",

    REPORT_DIR
    / "hero_demo_latest.json",
]

WORKFLOW_HERO_CANDIDATES = [
    REPORT_DIR
    / "repo_debug_workflow_latest.json",

    REPORT_DIR
    / "repo_debug_workflow_v1.json",
]

OUTPUT_PATH = (
    REPORT_DIR
    / "dashboard.html"
)


def load_json(
    path: Path,
    default,
):
    if not path.exists():
        return default

    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def load_first_json(
    candidates: list[Path],
) -> tuple[dict, Path | None]:
    for path in candidates:
        if path.exists():
            return (
                load_json(
                    path,
                    {},
                ),
                path,
            )

    return {}, None


def percentile(
    values: list[float],
    p: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(
        values
    )

    index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil(
                p * len(ordered)
            ) - 1,
        ),
    )

    return ordered[
        index
    ]


def percent(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return (
        numerator
        / denominator
        * 100
    )


def hero_status(
    data: dict,
) -> str:
    if not data:
        return "N/A"

    return (
        "PASS"
        if data.get(
            "success",
            False,
        )
        else "FAIL"
    )


def hero_latency(
    data: dict,
) -> float:
    try:
        return float(
            data.get(
                "latency_ms",
                0,
            )
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def main() -> None:
    # -----------------------------------------------------
    # Load evaluation reports
    # -----------------------------------------------------

    router_results = load_json(
        ROUTER_REPORT,
        [],
    )

    live_results = load_json(
        LIVE_REPORT,
        [],
    )

    (
        react_hero,
        react_hero_path,
    ) = load_first_json(
        REACT_HERO_CANDIDATES
    )

    (
        workflow_hero,
        workflow_hero_path,
    ) = load_first_json(
        WORKFLOW_HERO_CANDIDATES
    )

    # -----------------------------------------------------
    # Router metrics
    # -----------------------------------------------------

    router_total = len(
        router_results
    )

    router_passed = sum(
        bool(
            item.get(
                "passed",
                False,
            )
        )
        for item in router_results
    )

    router_accuracy = percent(
        router_passed,
        router_total,
    )

    route_counts = Counter(
        item.get(
            "actual_route",
            "unknown",
        )
        for item in router_results
    )

    # -----------------------------------------------------
    # Live-agent metrics
    # -----------------------------------------------------

    core_results = [
        item
        for item in live_results
        if not item.get(
            "external",
            False,
        )
    ]

    live_total = len(
        core_results
    )

    live_passed = sum(
        bool(
            item.get(
                "passed",
                False,
            )
        )
        for item in core_results
    )

    task_success = percent(
        live_passed,
        live_total,
    )

    latencies = [
        float(
            item.get(
                "latency_ms",
                0,
            )
            or 0
        )
        for item in core_results
        if item.get(
            "error"
        ) is None
    ]

    average_latency = (
        sum(latencies)
        / len(latencies)
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

    # -----------------------------------------------------
    # Category metrics
    # -----------------------------------------------------

    category_data = defaultdict(
        lambda: {
            "total": 0,
            "passed": 0,
        }
    )

    for item in core_results:
        category = item.get(
            "category",
            "unknown",
        )

        category_data[
            category
        ]["total"] += 1

        if item.get(
            "passed",
            False,
        ):
            category_data[
                category
            ]["passed"] += 1

    # -----------------------------------------------------
    # Hero-demo metrics
    # -----------------------------------------------------

    react_status = hero_status(
        react_hero
    )

    workflow_status = hero_status(
        workflow_hero
    )

    react_latency = hero_latency(
        react_hero
    )

    workflow_latency = hero_latency(
        workflow_hero
    )

    hero_speedup = 0.0

    if (
        react_latency > 0
        and workflow_latency > 0
    ):
        hero_speedup = (
            react_latency
            / workflow_latency
        )

    if hero_speedup > 0:
        hero_note = (
            f"{hero_speedup:.2f}× faster "
            "than the free-form ReAct baseline "
            "in this controlled repository-debugging task."
        )

    else:
        hero_note = (
            "Comparison unavailable because one "
            "of the benchmark reports is missing."
        )

    # -----------------------------------------------------
    # Route table
    # -----------------------------------------------------

    route_rows = ""

    for (
        route,
        count,
    ) in sorted(
        route_counts.items()
    ):
        route_rows += f"""
<tr>
    <td>{route}</td>
    <td>{count}</td>
    <td>
        {percent(count, router_total):.1f}%
    </td>
</tr>
"""

    # -----------------------------------------------------
    # Category table
    # -----------------------------------------------------

    category_rows = ""

    for (
        category,
        data,
    ) in sorted(
        category_data.items()
    ):
        success = percent(
            data["passed"],
            data["total"],
        )

        category_rows += f"""
<tr>
    <td>{category}</td>
    <td>
        {data["passed"]}/{data["total"]}
    </td>
    <td>
        {success:.1f}%
    </td>
</tr>
"""

    # -----------------------------------------------------
    # Live-case latency table
    # -----------------------------------------------------

    case_rows = ""

    max_latency = max(
        latencies,
        default=1.0,
    )

    for item in core_results:
        latency = float(
            item.get(
                "latency_ms",
                0,
            )
            or 0
        )

        bar_width = (
            latency
            / max_latency
            * 100
            if max_latency > 0
            else 0
        )

        passed = bool(
            item.get(
                "passed",
                False,
            )
        )

        status = (
            "PASS"
            if passed
            else "FAIL"
        )

        status_class = (
            "pass"
            if passed
            else "fail"
        )

        case_rows += f"""
<tr>
    <td>
        {item.get("id", "")}
    </td>

    <td>
        {item.get("category", "")}
    </td>

    <td>
        <span class="{status_class}">
            {status}
        </span>
    </td>

    <td>
        <div class="latency-cell">

            <div
                class="latency-bar"
                style="width:{bar_width:.1f}%">
            </div>

            <span>
                {latency:.0f} ms
            </span>

        </div>
    </td>
</tr>
"""

    # -----------------------------------------------------
    # Dashboard HTML
    # -----------------------------------------------------

    html = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<title>
LocalAgent Eval Dashboard
</title>

<style>

body {{
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    background:
        #f6f7f9;

    color:
        #18181b;

    margin:
        0;
}}

.container {{
    max-width:
        1180px;

    margin:
        0 auto;

    padding:
        48px 28px 80px;
}}

h1 {{
    margin-bottom:
        6px;
}}

.subtitle {{
    color:
        #71717a;

    margin-bottom:
        32px;
}}

.cards {{
    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                180px,
                1fr
            )
        );

    gap:
        16px;

    margin-bottom:
        32px;
}}

.card {{
    background:
        white;

    border:
        1px solid #e4e4e7;

    border-radius:
        14px;

    padding:
        22px;
}}

.metric {{
    font-size:
        30px;

    font-weight:
        700;

    margin-top:
        8px;
}}

.label {{
    color:
        #71717a;

    font-size:
        14px;
}}

.section {{
    background:
        white;

    border:
        1px solid #e4e4e7;

    border-radius:
        14px;

    padding:
        24px;

    margin-top:
        20px;
}}

table {{
    width:
        100%;

    border-collapse:
        collapse;
}}

th,
td {{
    text-align:
        left;

    border-bottom:
        1px solid #eeeeef;

    padding:
        12px 8px;

    vertical-align:
        top;
}}

th {{
    color:
        #71717a;

    font-size:
        13px;
}}

.pass {{
    font-weight:
        700;
}}

.fail {{
    font-weight:
        700;

    text-decoration:
        underline;
}}

.latency-cell {{
    position:
        relative;

    min-width:
        220px;
}}

.latency-bar {{
    position:
        absolute;

    left:
        0;

    top:
        3px;

    height:
        18px;

    background:
        #e4e4e7;

    border-radius:
        4px;
}}

.latency-cell span {{
    position:
        relative;

    padding-left:
        6px;
}}

.note {{
    color:
        #71717a;

    font-size:
        13px;

    margin-top:
        18px;
}}

.architecture {{
    font-weight:
        600;
}}

</style>

</head>

<body>

<div class="container">

<h1>
LocalAgent Evaluation Dashboard
</h1>

<div class="subtitle">

Local LLM Agent Runtime ·
MCP ·
RAG ·
Fast Path ·
Deterministic Workflow

</div>


<!-- ================================================== -->
<!-- Top metrics                                        -->
<!-- ================================================== -->

<div class="cards">


<div class="card">

    <div class="label">
        Router Accuracy
    </div>

    <div class="metric">
        {router_accuracy:.1f}%
    </div>

    <div class="note">
        {router_passed}/{router_total}
        regression cases
    </div>

</div>


<div class="card">

    <div class="label">
        Core Task Success
    </div>

    <div class="metric">
        {task_success:.1f}%
    </div>

    <div class="note">
        {live_passed}/{live_total}
        end-to-end cases
    </div>

</div>


<div class="card">

    <div class="label">
        P50 Latency
    </div>

    <div class="metric">
        {p50:.0f} ms
    </div>

</div>


<div class="card">

    <div class="label">
        Average Latency
    </div>

    <div class="metric">
        {average_latency:.0f} ms
    </div>

</div>


<div class="card">

    <div class="label">
        P95 Latency
    </div>

    <div class="metric">
        {p95:.0f} ms
    </div>

    <div class="note">
        Small benchmark;
        interpret cautiously.
    </div>

</div>


<div class="card">

    <div class="label">
        Repo Debug Workflow
    </div>

    <div class="metric">
        {workflow_status}
    </div>

    <div class="note">
        {workflow_latency:.0f} ms ·
        runtime verified
    </div>

</div>


</div>


<!-- ================================================== -->
<!-- Repository Debugging Comparison                    -->
<!-- ================================================== -->

<div class="section">

<h2>
Repository Debugging Architecture Comparison
</h2>

<table>

<thead>

<tr>
    <th>
        Architecture
    </th>

    <th>
        Result
    </th>

    <th>
        Latency
    </th>

    <th>
        Execution Strategy
    </th>
</tr>

</thead>

<tbody>


<tr>

    <td class="architecture">
        Free-form ReAct
    </td>

    <td>
        {react_status}
    </td>

    <td>
        {react_latency:.0f} ms
    </td>

    <td>
        LLM dynamically plans all tool calls.
        In this controlled task it made
        unnecessary tool calls and failed
        the final task-level evaluation.
    </td>

</tr>


<tr>

    <td class="architecture">
        Semi-deterministic Workflow
    </td>

    <td>
        {workflow_status}
    </td>

    <td>
        {workflow_latency:.0f} ms
    </td>

    <td>
        Runtime controls deterministic
        execution steps while the LLM
        handles root-cause reasoning only.
    </td>

</tr>


</tbody>

</table>

<div class="note">
{hero_note}
</div>

</div>


<!-- ================================================== -->
<!-- Route Distribution                                 -->
<!-- ================================================== -->

<div class="section">

<h2>
Route Distribution
</h2>

<table>

<thead>

<tr>
    <th>
        Route
    </th>

    <th>
        Cases
    </th>

    <th>
        Share
    </th>
</tr>

</thead>

<tbody>

{route_rows}

</tbody>

</table>

</div>


<!-- ================================================== -->
<!-- Category Success                                   -->
<!-- ================================================== -->

<div class="section">

<h2>
Category Success
</h2>

<table>

<thead>

<tr>
    <th>
        Category
    </th>

    <th>
        Passed
    </th>

    <th>
        Success Rate
    </th>
</tr>

</thead>

<tbody>

{category_rows}

</tbody>

</table>

</div>


<!-- ================================================== -->
<!-- End-to-End Latency                                 -->
<!-- ================================================== -->

<div class="section">

<h2>
End-to-End Case Latency
</h2>

<table>

<thead>

<tr>
    <th>
        Case
    </th>

    <th>
        Category
    </th>

    <th>
        Status
    </th>

    <th>
        Latency
    </th>
</tr>

</thead>

<tbody>

{case_rows}

</tbody>

</table>

<div class="note">

External-provider cases are excluded
from core success and latency metrics.

</div>

</div>


</div>

</body>

</html>
"""

    OUTPUT_PATH.write_text(
        html,
        encoding="utf-8",
    )

    print(
        "Dashboard generated:"
    )

    print(
        OUTPUT_PATH
    )

    print()

    print(
        "ReAct Hero source:",
        react_hero_path,
    )

    print(
        "Workflow Hero source:",
        workflow_hero_path,
    )

    print(
        "ReAct Hero:",
        react_status,
        f"{react_latency:.2f} ms",
    )

    print(
        "Workflow Hero:",
        workflow_status,
        f"{workflow_latency:.2f} ms",
    )

    if hero_speedup > 0:
        print(
            "Workflow speedup:",
            f"{hero_speedup:.2f}x",
        )


if __name__ == "__main__":
    main()