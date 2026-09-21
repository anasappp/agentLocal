# Live Agent Evaluation

- Generated: 2026-09-21T11:22:20
- Core cases: 10
- Passed: 10
- Failed: 0
- Task Success Rate: 100.00%
- Average latency: 1526.11 ms
- P50 latency: 429.25 ms
- P95 latency: 7139.41 ms

## Category Success

- direct: 1/1 (100.00%)
- error_recovery: 2/2 (100.00%)
- file: 2/2 (100.00%)
- multi_turn: 2/2 (100.00%)
- rag: 1/1 (100.00%)
- tool_exact: 2/2 (100.00%)

## Case Results

| Case | Category | Result | Latency | Tokens | Reason |
|---|---|---|---:|---:|---|
| direct_cv_cn | direct | PASS | 2309.53 ms | 0 | all expected values found |
| calc_cn | tool_exact | PASS | 379.48 ms | 0 | all expected values found |
| calc_large_cn | tool_exact | PASS | 371.42 ms | 0 | all expected values found |
| file_write | file | PASS | 1680.72 ms | 0 | matched: eval_probe.txt |
| file_read | file | PASS | 312.82 ms | 0 | all expected values found |
| file_followup_cn | multi_turn | PASS | 709.30 ms | 0 | all expected values found |
| memory_cn | multi_turn | PASS | 1604.72 ms | 0 | all expected values found |
| missing_file | error_recovery | PASS | 324.45 ms | 0 | matched: not found |
| division_zero | error_recovery | PASS | 429.25 ms | 0 | matched: ZeroDivision |
| rag_gguf | rag | PASS | 7139.41 ms | 0 | all expected values found |

## Failure Details

No failures.