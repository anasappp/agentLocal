# Agent Router Evaluation

- Generated: 2026-09-21T10:46:06
- Total cases: 21
- Passed: 21
- Failed: 0
- Routing accuracy: 100.00%

## Route Distribution

- background_direct: 1 (4.76%)
- direct: 4 (19.05%)
- fast_path: 13 (61.90%)
- react: 1 (4.76%)
- workflow: 2 (9.52%)

## Case Results

| Case | Expected | Actual | Target | Result |
|---|---|---|---|---|
| direct_hello_cn | direct | direct | - → - | PASS |
| direct_cv_cn | direct | direct | - → - | PASS |
| direct_complexity_cn | direct | direct | - → - | PASS |
| direct_filename_question | direct | direct | - → - | PASS |
| calc_cn | fast_path | fast_path | code_exec → code_exec | PASS |
| calc_explicit_cn | fast_path | fast_path | code_exec → code_exec | PASS |
| file_list_cn | fast_path | fast_path | file_list → file_list | PASS |
| file_list_en | fast_path | fast_path | file_list → file_list | PASS |
| file_read_cn | fast_path | fast_path | file_read → file_read | PASS |
| file_read_en | fast_path | fast_path | file_read → file_read | PASS |
| rag_cn | fast_path | fast_path | query_knowledge_base → query_knowledge_base | PASS |
| rag_en | fast_path | fast_path | query_knowledge_base → query_knowledge_base | PASS |
| web_cn | fast_path | fast_path | web_search → web_search | PASS |
| web_en | fast_path | fast_path | web_search → web_search | PASS |
| workflow_cn | workflow | workflow | web_search_to_file_write → web_search_to_file_write | PASS |
| workflow_en | workflow | workflow | web_search_to_file_write → web_search_to_file_write | PASS |
| file_followup_cn | fast_path | fast_path | file_read → file_read | PASS |
| file_followup_en | fast_path | fast_path | file_read → file_read | PASS |
| calc_followup_cn | fast_path | fast_path | code_exec → code_exec | PASS |
| background_title | background_direct | background_direct | - → - | PASS |
| complex_agent_cn | react | react | - → file_write | PASS |

## Failures

No routing failures.