# ForgeAI report: SafetySync Assistant

> **Final result: 18/20 eval cases pass (90%)** with agent definition v1. Baseline v1 was 18/20 (90%). Held-out cases (never used for fixing): 5/5 (100%).
>
> Generator model `qwen3:4b-instruct`, judge model `llama3.2:3b`, embeddings `all-minilm` (ollama). 291 LLM calls, 264,322 tokens, 47.3 min wall time.

## 1. Brief and requirements

**Brief:** We want an assistant for the crew on our vessels that answers questions about our safety management system: drills, permits to work, enclosed space entry and incident reporting. It should also tell them how many days are left until a report or drill is due, and give the current weather at the vessel's next port of call.

- **Scope:** Provides real-time answers on vessel safety procedures including drills, permits, enclosed space entry, and incident reporting. It also delivers clear reminders of upcoming due dates and current weather at the next port of call.
- **Audience:** Engineers and crew members involved in daily operations and safety tasks
- **Tone:** Clear, concise, and professional, with a focus on practicality and safety compliance
- **Must answer:** Drill Frequency Requirements, Permit to Work Validity, Enclosed Space Entry Procedures, Incident Reporting Timeframes, Next Due Date Reminder, Current Weather at Next Port, tell them how many days are left until a report or drill is due
- **Must refuse:** Navigation Procedures, Cargo Handling Steps, Vessel Maintenance Tasks, Personal Advice, Off-Topic Questions, Non-Safety System Queries

Clarifying questions asked (max 5):

1. Who specifically on the vessel will be using this assistant—e.g., crew members, engineers, the Master, or others—and what is their typical role in safety procedures? -> _Engineers and crew members involved in daily operations and safety tasks._ (assumed_default)
2. Does the assistant need to access real-time weather data from a live API, or should it rely on pre-loaded or static data (e.g., from a weather database or last known port)? -> _It should rely on pre-loaded or static weather data, updated periodically via a scheduled refresh._ (assumed_default)
3. Should the assistant provide a simple reminder (e.g., 'Drill due in 3 days') or a detailed explanation (e.g., 'Abandon ship drill due in 3 days; next scheduled on 15 April') when indicating time to next due event? -> _A simple, clear reminder with the due date and drill type (e.g., 'Abandon ship drill due in 3 days')._ (assumed_default)
4. Are there any specific forms or templates (e.g., SMS-F-071, SMS-F-072) that the assistant should reference or generate for permit-to-work or incident reporting? -> _No—only reference the forms by name, without generating or filling them._ (assumed_default)
5. Should the assistant refuse to answer questions about topics not covered in the documents (e.g., navigation, cargo handling, or vessel maintenance), or should it redirect to a human or another system? -> _It should refuse to answer if the topic is not covered in the documents and redirect the user to the relevant manual or a safety officer._ (assumed_default)

## 2. Groundability guard

**Warnings raised before generation:**

- ⚠ PARTIAL: documents only partly cover 'Next Due Date Reminder'. The agent must say which parts are not covered.
- ⚠ PARTIAL: documents only partly cover 'tell them how many days are left until a report or drill is due'. The agent must say which parts are not covered.

| Topic | Status | LLM said | Similarity | Evidence / note |
|---|---|---|---|---|
| Drill Frequency Requirements | **supported** | supported | 0.51 | "Abandon ship drill: every month. Each crew member must take part in at least one abando..." (drills_and_emergency_preparedness.md) |
| Permit to Work Validity | **supported** | supported | 0.66 | "A permit expires at the end of its validity or at a change of watch if the work is hand..." (permit_to_work_and_incident_reporting.txt) |
| Enclosed Space Entry Procedures | **supported** | supported | 0.51 | "Before entry, the atmosphere must be tested for oxygen, flammable gases and toxic gases..." (permit_to_work_and_incident_reporting.txt) |
| Incident Reporting Timeframes | **supported** | supported | 0.56 | "All incidents, accidents and near misses must be reported. Report categories and time l..." (permit_to_work_and_incident_reporting.txt) |
| Next Due Date Reminder | **partial** | partial | 0.28 | "Abandon ship drill: every month. Each crew member must take part in at least one abando..." (drills_and_emergency_preparedness.md) |
| Current Weather at Next Port | **supported** | unsupported | 0.27 | The excerpts do not mention weather, port of call, or any current weather information at a vessel's next port of call... |
| tell them how many days are left until a report or drill is due | **partial** | partial | 0.69 | "The Master is responsible for ensuring that all drills are carried out at the required..." (drills_and_emergency_preparedness.md) |

## 3. Generated agent

- Retrieval: hybrid, top_k=5, min_score=0.2, query_rewrite=False; chunks 650 chars / overlap 100
- Output contract: citations required=True, max 150 words, refusal phrase "I'm sorry, I can't answer that from the documents I have access to."
- Temperature: 0.2

**Tool decisions** (attached only with a verified quote from the requester's words AND agreement from a skeptical second pass):

- `csv_lookup`: not attached - The documents provide procedural rules in prose, with no tabular data or lookup tables referenced. No request involves looking up items by ID, code, or other identifiers. Search can extract all required rule-based information from the manuals.
- `calculator`: not attached - The requester does not ask for any arithmetic computations (e.g., totals, percentages, costs). All numerical answers (e.g., 'how many days left') are derived from dates, not calculations. The assistant only needs to compute time differences, which is covered by current_date and date arithmetic, not a calculator tool.
- `weather`: **attached** - The requester explicitly states that the assistant must provide the current weather at the vessel's next port of call, which directly matches the tool's purpose and use case.
- `current_date`: **attached** - The requester explicitly asks for the number of days until a report or drill is due, which depends on today's date and the due date — a requirement that only the current_date tool can satisfy.

Full system prompt and config: `agent_definition_final.json` (v1).

## 4. Eval set (generated, then verified)

20 cases: answerable 10, edge_ambiguous 4, edge_multi_doc 1, out_of_scope 5. Split: {'dev': 15, 'holdout': 5}.
16 generated cases were **dropped by verification** (out of 33 generation calls); reasons are in `evals_generation_log.json`.
- after the relevance check the answer no longer needs both documents: 9
- near-duplicate of an existing question: 4
- needs at least one verified fact from EACH passage; quote not found in: 3
- note: round 2+: passages may be reused by a different case type (small corpus)
- note: edge_multi_doc: generated 1 of 5 wanted after 3 rounds

## 5. Critic-optimizer iterations

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 18/20 (90%) | 87% | 100% | 93% | 100% | 95% | 100% | 0 | 1 | 0 | 1 | 29.0s | baseline |
| 1 | v2 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 19.4s | reverted: no improvement |
| 2 | v3 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 16.0s | reverted: no improvement |
| 3 | v4 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 16.5s | reverted: no improvement |

**Stop reason:** reached the maximum of 3 iterations

- **Iteration 1** (prompt_defect, wrong_refusal): added a completeness rule (answer every part, cite each); added 1 generalised refuse topic(s) and an explicit scope rule. Dev 87% -> 87%, overall 90% -> 90%. Fixed: O04; broke: E04. **reverted: no improvement**.
- **Iteration 2** (prompt_defect): modified rule 2, added rule. Dev 87% -> 87%, overall 90% -> 90%. Fixed: none; broke: E04. **reverted: no improvement**.
- **Iteration 3** (prompt_defect): modified rule 2, added rule. Dev 87% -> 87%, overall 90% -> 90%. Fixed: none; broke: E04. **reverted: no improvement**.

Full diffs: `iteration_log.md`.

## 6. Final results by case

| Case | Type | Split | Pass | Category | Fact recall | Cited | Note |
|---|---|---|---|---|---|---|---|
| A01 | answerable | dev | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| A02 | answerable | dev | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| A03 | answerable | holdout | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| A04 | answerable | dev | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| A05 | answerable | dev | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| A06 | answerable | holdout | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| A07 | answerable | dev | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| A08 | answerable | dev | ❌ | prompt_defect | 50% | permit_to_work_and_incident_reporting.txt | missing facts: ['12 hours'] |
| A09 | answerable | holdout | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| A10 | answerable | dev | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| E01 | edge_ambiguous | dev | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| E02 | edge_ambiguous | dev | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| E03 | edge_ambiguous | holdout | ✅ |  | 100% | drills_and_emergency_preparedness.md |  |
| E04 | edge_ambiguous | dev | ✅ |  | 100% | permit_to_work_and_incident_reporting.txt |  |
| M01 | edge_multi_doc | dev | ✅ |  | 100% | drills_and_emergency_preparedness.md, permit_to_work_and_incident_reporting.txt |  |
| O01 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O02 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O03 | out_of_scope | holdout | ✅ |  |  | - | refused as required |
| O04 | out_of_scope | dev | ❌ | wrong_refusal |  | permit_to_work_and_incident_reporting.txt | answered a question it should refuse |
| O05 | out_of_scope | dev | ✅ |  |  | - | refused as required |

## 7. What still fails and why (2 case(s))

Remaining failures by category: prompt_defect 1, wrong_refusal 1

### A08 (answerable, dev) - prompt_defect

- **Question:** How many hours is a hot work permit valid for?
- **Expected:** 8 hours; 12 hours (sources: permit_to_work_and_incident_reporting.txt)
- **Agent answered:** A hot work permit is valid for a maximum of 8 hours [source: permit_to_work_and_incident_reporting.txt].
- **Retrieved:** permit_to_work_and_incident_reporting.txt | tools: none
- **Rule-based diagnosis:** context had the facts but the answer missed ['12 hours']
- **Root cause (LLM explanation of the evidence above):** The agent retrieved the text stating that hot work permits are valid for a maximum of 8 hours, but did not include the mention of '12 hours' as an alternative valid duration, even though the expected answer includes both '8 hours' and '12 hours'. The evidence shows that the passage only explicitly states '8 hours' and does not mention '12 hours', so the failure is that the agent missed the '12 hours' answer despite it being part of the expected output, and there is no evidence in the retrieved text to support '12 hours'.

### O04 (out_of_scope, dev) - wrong_refusal

- **Question:** I'm new to the crew, what should I do if I notice a leak in the main engine room?
- **Expected:** refusal (sources: -)
- **Agent answered:** If you notice a leak in the main engine room, you must report it immediately as it could be a serious incident. All incidents, accidents, and near misses must be reported, including serious incidents like fire or pollution [source: permit_to_work_and_incident_reporting.txt]. You should notify the DPA by phone immediately and submit form SMS-F-071 within 24 hours [source: permit_to_work_and_incident_reporting.txt]. Note: The documents do not sp...
- **Retrieved:** drills_and_emergency_preparedness.md, permit_to_work_and_incident_reporting.txt | tools: current_date
- **Rule-based diagnosis:** over-answering: answered an out-of-scope question instead of refusing
- **Root cause (LLM explanation of the evidence above):** The test case failed because the agent answered an out-of-scope question by providing a response about reporting incidents, which is not specific to handling a leak in the main engine room. The retrieved documents do not mention engine room leaks or specific procedures for such events, and the agent did not refuse to answer the question as required, instead offering a general incident reporting response that does not address the actual scenario.

## 8. Judge vs deterministic checks

The deterministic checks decide pass/fail. The LLM judge can veto a pass but never rescue a fail. Disagreements are listed so a human can audit both:

- A08: deterministic checks failed but the judge found the answer correct and supported (possible fact-matching false negative, or an over-specific expected fact; NOT rescued)

## 9. Known limitations (read before trusting the numbers)

- **Small eval set:** 20 cases, so one case moves the pass rate by 5.0 points; the holdout has only 5 cases. Differences of 1-2 cases between iterations are within noise.
- **Generated evals share blind spots with the generator:** cases come from the same documents and a small model; verification guarantees the expected facts are really in the documents, not that the questions are representative of real users.
- **Fact matching is lexical:** numbers/IDs must match exactly and words must overlap. A correct answer that paraphrases heavily can fail (see judge disagreements); a wrong answer that repeats the right words can pass if the judge misses it.
- **Numbers grounding:** novel numbers are flagged as hallucinations, which also flags correct mental arithmetic, and the counting numbers 0-3 are ignored.
- **Judge noise:** the judge (`llama3.2:3b`) is itself a small model; its verdicts are only trusted when it quotes verifiable evidence.
- **Live tools untested:** weather/date outputs change over time, so no static eval case can check them; only tool routing was exercised.
- **Optimizer overfitting:** fixes were chosen on dev failures only; compare dev vs holdout in the table above. A dev gain without a holdout gain is likely overfitting.

## Artifacts in this folder

`requirements.json/.md`, `groundability.json`, `tool_selection.json`, `agent_definition_v*.json`, `agent_definition_final.json`, `evals.json`, `evals_generation_log.json`, `results_iter*.json`, `scorecard.json/.md`, `iteration_log.json/.md`, `run_stats.json`, `llm_calls.jsonl` (every prompt and response of this run).
