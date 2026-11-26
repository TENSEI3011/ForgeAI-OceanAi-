# ForgeAI report: ShoreHR Helper

> **Final result: 19/20 eval cases pass (95%)** with agent definition v1. Baseline v1 was 19/20 (95%). Held-out cases (never used for fixing): 4/5 (80%).
>
> Generator model `qwen3:4b-instruct`, judge model `llama3.2:3b`, embeddings `all-minilm` (ollama). 189 LLM calls, 175,392 tokens, 28.6 min wall time.

## 1. Brief and requirements

**Brief:** I need an assistant that answers HR policy questions for our shore staff: leave, code of conduct, travel and expense claims, and payroll questions such as when salaries are credited and what the deductions on a payslip mean.

- **Scope:** An AI assistant that answers factual policy questions about leave, code of conduct, travel and expense claims, and payroll for shore-based employees at Coralis Shipping Pvt. Ltd. in Mumbai and Singapore.
- **Audience:** Shore-based office employees in the Mumbai head office and Singapore branch.
- **Tone:** Friendly, plain English, concise. Mentions the policy name and section when possible so staff can check it themselves.
- **Must answer:** Annual Leave Entitlement, Code of Conduct Rules, Travel Approval Process, Expense Claim Procedure
- **Must refuse:** Personal Salary Changes, Individual Disciplinary Cases, Legal or Tax Advice, Employee Personal Conflicts, Other Employees' Pay Details, Offshore Staff Queries, Payroll Credit Dates (requested, but not covered by the documents), Payslip Deduction Explanations (requested, but not covered by the documents)

Clarifying questions asked (max 5):

1. Who specifically will use this assistant—e.g., shore staff members, managers, HR officers, or a specific role like operations or finance? -> _The users are shore-based office employees in our Mumbai head office and Singapore branch. Seafarers on our vessels are NOT users of this assistant._ (requester_file)
2. Should the assistant provide step-by-step guidance on how to claim expenses or apply for leave, or only answer factual policy questions? -> _Staff ask both about entitlements and limits (how many days, how much) and about procedures (how to apply for leave, how to submit an expense claim, who approves). Both are in scope._ (requester_file)
3. Are there any policy areas or questions that should be redirected to HR or a manager (e.g., personal conflicts, salary changes, or sensitive topics)? -> _The assistant must not give legal or tax advice and must never discuss individual disciplinary cases, other employees, or anyone's personal salary._ (requester_file)
4. Should the assistant calculate leave entitlements or per diem amounts based on service length or travel duration, or only state fixed values from the documents? -> _Payroll questions (salary credit dates, payslip deductions) come up a lot and we would like them answered._ (requester_file)
5. Should the assistant use a formal, professional tone, or a more conversational, friendly tone for shore staff? -> _Tone: friendly, plain English, concise. Mention the policy name and section when possible so staff can check it._ (requester_file)

## 2. Groundability guard

**Warnings raised before generation:**

- ⚠ UNSUPPORTED: the brief asks for 'Payroll Credit Dates' but the documents do not cover it. It was moved to must-refuse; the agent will decline instead of guessing.
- ⚠ UNSUPPORTED: the brief asks for 'Payslip Deduction Explanations' but the documents do not cover it. It was moved to must-refuse; the agent will decline instead of guessing.

| Topic | Status | LLM said | Similarity | Evidence / note |
|---|---|---|---|---|
| Annual Leave Entitlement | **supported** | supported | 0.61 | "Employees with less than 5 years of continuous service are entitled to 21 working days..." (leave_policy.pdf) |
| Code of Conduct Rules | **supported** | supported | 0.70 | "The company does not tolerate harassment of any kind. Complaints of sexual harassment a..." (code_of_conduct.pdf) |
| Travel Approval Process | **supported** | supported | 0.66 | "All business travel must be pre-approved in the PeoplePort Travel module before any boo..." (travel_and_expenses_policy.pdf) |
| Expense Claim Procedure | **supported** | supported | 0.63 | "Expense claims must be submitted through PeoplePort Expenses within 30 days of the end..." (travel_and_expenses_policy.pdf) |
| Payroll Credit Dates | **unsupported** | unsupported | 0.33 | The excerpts do not contain any information about payroll credit dates, salary crediting, or payslip deductions. |
| Payslip Deduction Explanations | **unsupported** | unsupported | 0.39 | The excerpts do not contain any information about payslip deductions or what they mean, even though they mention payr... |

## 3. Generated agent

- Retrieval: hybrid, top_k=5, min_score=0.2, query_rewrite=False; chunks 850 chars / overlap 130
- Output contract: citations required=True, max 150 words, refusal phrase "I'm sorry, I can't answer that from the documents I have access to."
- Temperature: 0.2

**Tool decisions** (attached only with a verified quote from the requester's words AND agreement from a skeptical second pass):

- `csv_lookup`: not attached - The documents are policy documents (prose), not structured CSV tables with item codes or prices. No request involves looking up specific items or records by ID or code. Semantic search of policy text suffices.
- `weather`: not attached - Weather is not mentioned in any policy or user request. The assistant does not need to report weather conditions for any location, and it is irrelevant to HR policy questions.
- `current_date`: not attached - justification quote not found in the requester's words: 'how many days, how much, notice periods, carry-forward limits, must be used by 31 March, weekend travel must be recorded and availed within 60 days'
- `calculator`: not attached - critic pass rejected it: The requester asks about when salaries are credited and what deductions mean, which refers to explaining policy content, not performing arithmetic. The documents provide the factual rules (e.g., deduction types, credit dates), and no request involves computing totals, percentages, or quantities. Thus, no arithmetic is required.

Full system prompt and config: `agent_definition_final.json` (v1).

## 4. Eval set (generated, then verified)

20 cases: answerable 10, edge_ambiguous 4, edge_multi_doc 1, out_of_scope 5. Split: {'dev': 15, 'holdout': 5}.
18 generated cases were **dropped by verification** (out of 35 generation calls); reasons are in `evals_generation_log.json`.
- after the relevance check the answer no longer needs both documents: 15
- near-duplicate of an existing question: 2
- question leaks its own answer: 1
- note: round 2+: passages may be reused by a different case type (small corpus)
- note: edge_multi_doc: generated 1 of 5 wanted after 3 rounds

## 5. Critic-optimizer iterations

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 19/20 (95%) | 100% | 80% | 100% | 100% | 100% | 93% | 0 | 1 | 0 | 0 | 6.0s | baseline |

**Stop reason:** dev pass rate 100% reached the target (90%)


Full diffs: `iteration_log.md`.

## 6. Final results by case

| Case | Type | Split | Pass | Category | Fact recall | Cited | Note |
|---|---|---|---|---|---|---|---|
| A01 | answerable | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| A02 | answerable | dev | ✅ |  | 100% | travel_and_expenses_policy.pdf |  |
| A03 | answerable | holdout | ✅ |  | 100% | leave_policy.pdf | judge verdict discarded (unverifiable quote) |
| A04 | answerable | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| A05 | answerable | dev | ✅ |  | 100% | travel_and_expenses_policy.pdf |  |
| A06 | answerable | holdout | ✅ |  | 100% | leave_policy.pdf |  |
| A07 | answerable | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| A08 | answerable | dev | ✅ |  | 100% | travel_and_expenses_policy.pdf |  |
| A09 | answerable | holdout | ❌ | prompt_defect | 100% | travel_and_expenses_policy.pdf | citation problem (cited ['travel_and_expenses_policy.pdf'], expected ['leave_... |
| A10 | answerable | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| E01 | edge_ambiguous | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| E02 | edge_ambiguous | dev | ✅ |  | 100% | travel_and_expenses_policy.pdf |  |
| E03 | edge_ambiguous | holdout | ✅ |  | 100% | leave_policy.pdf |  |
| E04 | edge_ambiguous | dev | ✅ |  | 100% | code_of_conduct.pdf |  |
| M01 | edge_multi_doc | dev | ✅ |  | 100% | leave_policy.pdf, travel_and_expenses_policy.pdf |  |
| O01 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O02 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O03 | out_of_scope | holdout | ✅ |  |  | - | refused as required |
| O04 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O05 | out_of_scope | dev | ✅ |  |  | - | refused as required |

## 7. What still fails and why (1 case(s))

Remaining failures by category: prompt_defect 1

### A09 (answerable, holdout) - prompt_defect

- **Question:** How many comp-off days do I get for working a weekend on business travel?
- **Expected:** 1 day (sources: leave_policy.pdf)
- **Agent answered:** You get 1 day of compensatory time off (comp-off) for working a weekend on business travel [source: travel_and_expenses_policy.pdf, page 2]. - This comp-off must be recorded in PeoplePort and availed within 60 days of the day worked [source: travel_and_expenses_policy.pdf, page 2]. - The rule applies to both weekends and public holidays during business travel [source: travel_and_expenses_policy.pdf, page 2]. Note: The policy does not specify a...
- **Retrieved:** leave_policy.pdf, travel_and_expenses_policy.pdf | tools: none
- **Rule-based diagnosis:** citation contract not followed
- **Root cause (LLM explanation of the evidence above):** The test case failed because the expected answer specified '1 day' as the number of comp-off days, but the evidence shows that the policy only states a general rule of 1 day for weekends or public holidays during business travel, without specifying a limit or maximum number of days. The agent correctly identified the 1-day entitlement from the travel_and_expenses_policy.pdf, but the expected answer assumes a fixed number without evidence of a cap or limit, and the citation contract was not followed because the source material does not address the specific question about 'how many' comp-off days in total, only per day worked.

## 8. Judge vs deterministic checks

The deterministic checks decide pass/fail. The LLM judge can veto a pass but never rescue a fail. Disagreements are listed so a human can audit both:

- A02: judge said fail but gave no verifiable quote for it (ignored)
- A09: deterministic checks failed but the judge found the answer correct and supported (possible fact-matching false negative, or an over-specific expected fact; NOT rescued)
- M01: judge said fail but gave no verifiable quote for it (ignored)

## 9. Known limitations (read before trusting the numbers)

- **Small eval set:** 20 cases, so one case moves the pass rate by 5.0 points; the holdout has only 5 cases. Differences of 1-2 cases between iterations are within noise.
- **Generated evals share blind spots with the generator:** cases come from the same documents and a small model; verification guarantees the expected facts are really in the documents, not that the questions are representative of real users.
- **Fact matching is lexical:** numbers/IDs must match exactly and words must overlap. A correct answer that paraphrases heavily can fail (see judge disagreements); a wrong answer that repeats the right words can pass if the judge misses it.
- **Numbers grounding:** novel numbers are flagged as hallucinations, which also flags correct mental arithmetic, and the counting numbers 0-3 are ignored.
- **Judge noise:** the judge (`llama3.2:3b`) is itself a small model; its verdicts are only trusted when it quotes verifiable evidence.
- **Optimizer overfitting:** fixes were chosen on dev failures only; compare dev vs holdout in the table above. A dev gain without a holdout gain is likely overfitting.

## Prompt tournament (stretch goal)

Three candidate system prompts were evaluated on the dev split; the eval set picked the winner (holdout cases were not used). Ties: fewer hallucinations, then fewer wrong refusals, then shorter.

| Candidate | Dev pass | Hallucinations | Wrong refusals | Prompt chars | Winner |
|---|---|---|---|---|---|
| conservative | 15/15 (100%) | 0 | 0 | 2633 | **yes** |
| standard | 15/15 (100%) | 0 | 0 | 2750 |  |
| helpful | 15/15 (100%) | 0 | 0 | 2799 |  |

## Artifacts in this folder

`requirements.json/.md`, `groundability.json`, `tool_selection.json`, `agent_definition_v*.json`, `agent_definition_final.json`, `evals.json`, `evals_generation_log.json`, `results_iter*.json`, `scorecard.json/.md`, `iteration_log.json/.md`, `run_stats.json`, `llm_calls.jsonl` (every prompt and response of this run).
