# ForgeAI report: SparesCostAssistant

> **Final result: 22/24 eval cases pass (92%)** with agent definition v3. Baseline v1 was 20/24 (83%). Held-out cases (never used for fixing): 5/6 (83%).
>
> Generator model `qwen3:4b-instruct`, judge model `llama3.2:3b`, embeddings `all-minilm` (ollama). 284 LLM calls, 290,850 tokens, 204.9 min wall time.

## 1. Brief and requirements

**Brief:** I need an assistant that helps procurement officers find spares, check prices and stock, compare supplier terms and estimate order costs.

- **Scope:** The assistant helps procurement officers find spares for container vessels, checks current prices and stock levels, compares supplier terms including discounts, freight, and warranty, and estimates total order costs based on quantity, unit price, and supplier-specific terms.
- **Audience:** Procurement officers responsible for marine vessel maintenance spares in container vessel operations.
- **Tone:** Professional, clear, and precise, with a focus on factual accuracy and actionable procurement support.
- **Must answer:** Find Container Spares, Check Prices and Stock, Compare Supplier Terms, Estimate Order Costs
- **Must refuse:** Personal Financial Advice, Health or Wellness Recommendations, Travel Itinerary Planning, Non-Marine Part Sourcing, Legal Contract Drafting, Inventory Management for Non-Vessels

Clarifying questions asked (max 5):

1. What specific vessel class or type does the procurement officer primarily serve (e.g., container, tanker, offshore platform), and is there a preference for parts from certain categories (e.g., engine, electrical)? -> _Container vessel (general maintenance spares)_ (assumed_default)
2. Should the assistant compare supplier terms only for the same part, or also consider overall cost including freight, lead time, and warranty when evaluating supplier options? -> _Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms._ (requester_file)
3. Does the procurement officer need to generate a full purchase order with supplier-specific terms (e.g., payment terms, minimum order value) or just a cost estimate and part list? -> _Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms._ (requester_file)
4. Are there any parts or categories that should be excluded from consideration (e.g., due to high lead time, low stock, or made-to-order nature), or should the assistant flag them automatically? -> _Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms._ (requester_file)
5. Should the assistant consider future pricing validity (e.g., supplier terms valid until 31 March 2026) when recommending parts, or only use current prices? -> _Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms._ (requester_file)

## 2. Groundability guard

**Warnings raised before generation:**

- ⚠ PARTIAL: documents only partly cover 'Find Container Spares'. The agent must say which parts are not covered.

| Topic | Status | LLM said | Similarity | Evidence / note |
|---|---|---|---|---|
| Find Container Spares | **partial** | partial | 0.64 | "category: Valves" (spares_catalogue.csv) |
| Check Prices and Stock | **supported** | supported | 0.32 | "Prices are in US dollars, ex-warehouse. Quotations and catalogue prices are valid for 6..." (supplier_terms_b.pdf) |
| Compare Supplier Terms | **supported** | supported | 0.53 | "These terms apply to all purchase orders placed by Coralis Shipping fleet procurement w..." (supplier_terms_a.pdf) |
| Estimate Order Costs | **supported** | supported | 0.52 | "A volume discount of 8% applies to the whole order when the order value before discount..." (supplier_terms_b.pdf) |

## 3. Generated agent

- Retrieval: hybrid, top_k=6, min_score=0.2, query_rewrite=False; chunks 850 chars / overlap 130
- Output contract: citations required=True, max 150 words, refusal phrase "I'm sorry, I can't answer that from the documents I have access to."
- Temperature: 0.0

**Tool decisions** (attached only with a verified quote from the requester's words AND agreement from a skeptical second pass):

- `weather`: not attached - There is no mention of weather, sea conditions, or forecasts in the request. Weather is not required for any of the procurement tasks described.
- `current_date`: not attached - While some terms mention expiry or lead times, the requester does not ask about deadlines, due dates, or time-based aging of items. No explicit need for today's date is stated.
- `csv_lookup`: **attached** - The requester explicitly asks to 'find spares' and 'check prices and stock', which requires lookup of part numbers and inventory data in the spares_catalogue.csv.
- `calculator`: **attached** - The requester explicitly requires the assistant to compute order costs by multiplying quantity by unit price and applying supplier-specific discounts and fees, which is a core arithmetic operation.

Full system prompt and config: `agent_definition_final.json` (v3).

## 4. Eval set (generated, then verified)

24 cases: answerable 10, edge_ambiguous 4, edge_multi_doc 5, out_of_scope 5. Split: {'dev': 18, 'holdout': 6}.
2 generated cases were **dropped by verification** (out of 23 generation calls); reasons are in `evals_generation_log.json`.
- after the relevance check the answer no longer needs both documents: 1
- near-duplicate of an existing question: 1

## 5. Critic-optimizer iterations

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 20/24 (83%) | 83% | 83% | 84% | 100% | 100% | 95% | 0 | 4 | 0 | 0 | 429.8s | baseline |
| 1 | v2 | 21/24 (88%) | 89% | 83% | 90% | 95% | 100% | 100% | 0 | 2 | 1 | 0 | 24.1s | kept |
| 2 | v3 | 22/24 (92%) | 94% | 83% | 95% | 100% | 100% | 100% | 0 | 1 | 1 | 0 | 23.1s | kept |

**Stop reason:** dev pass rate 94% reached the target (90%)

- **Iteration 1** (prompt_defect): added a completeness rule (answer every part, cite each). Dev 83% -> 89%, overall 83% -> 88%. Fixed: E01, M02, M04; broke: E02, M01. **kept**.
- **Iteration 2** (hallucination, prompt_defect): added strict number-grounding rule; temperature 0.2 -> 0.0; added rule; rejected 1 leaking/invalid rule(s). Dev 89% -> 94%, overall 88% -> 92%. Fixed: E02, M01; broke: E04. **kept**.

Full diffs: `iteration_log.md`.

## 6. Final results by case

| Case | Type | Split | Pass | Category | Fact recall | Cited | Note |
|---|---|---|---|---|---|---|---|
| A01 | answerable | dev | ✅ |  | 100% | spares_catalogue.csv |  |
| A02 | answerable | dev | ✅ |  | 100% | supplier_terms_b.pdf |  |
| A03 | answerable | holdout | ✅ |  | 100% | supplier_terms_a.pdf |  |
| A04 | answerable | dev | ✅ |  | 100% | spares_catalogue.csv |  |
| A05 | answerable | dev | ✅ |  | 100% | supplier_terms_b.pdf |  |
| A06 | answerable | holdout | ✅ |  | 100% | supplier_terms_a.pdf, spares_catalogue.csv |  |
| A07 | answerable | dev | ✅ |  | 100% | spares_catalogue.csv |  |
| A08 | answerable | dev | ✅ |  | 100% | supplier_terms_a.pdf |  |
| A09 | answerable | holdout | ✅ |  | 100% | tool:csv_lookup, spares_catalogue.csv, tool:calculator |  |
| A10 | answerable | dev | ✅ |  | 100% | spares_catalogue.csv |  |
| E01 | edge_ambiguous | dev | ✅ |  | 100% | supplier_terms_a.pdf |  |
| E02 | edge_ambiguous | dev | ✅ |  | 100% | spares_catalogue.csv |  |
| E03 | edge_ambiguous | holdout | ✅ |  | 100% | spares_catalogue.csv |  |
| E04 | edge_ambiguous | dev | ❌ | hallucination | 100% | spares_catalogue.csv |  |
| M01 | edge_multi_doc | dev | ✅ |  | 100% | supplier_terms_a.pdf, supplier_terms_b.pdf |  |
| M02 | edge_multi_doc | dev | ✅ |  | 100% | supplier_terms_a.pdf, supplier_terms_b.pdf |  |
| M03 | edge_multi_doc | holdout | ❌ | prompt_defect | 50% | supplier_terms_b.pdf | missing facts: ['in-stock items are dispatched within 2 working days of order... |
| M04 | edge_multi_doc | dev | ✅ |  | 100% | supplier_terms_b.pdf, supplier_terms_a.pdf, spares_catalogue.csv |  |
| M05 | edge_multi_doc | dev | ✅ |  | 100% | supplier_terms_b.pdf, supplier_terms_a.pdf |  |
| O01 | out_of_scope | dev | ✅ |  |  | spares_catalogue.csv | refused as required |
| O02 | out_of_scope | dev | ✅ |  |  | supplier_terms_b.pdf | refused as required |
| O03 | out_of_scope | holdout | ✅ |  |  | spares_catalogue.csv | refused as required |
| O04 | out_of_scope | dev | ✅ |  |  | - | refused as required |
| O05 | out_of_scope | dev | ✅ |  |  | supplier_terms_a.pdf | refused as required |

## 7. What still fails and why (2 case(s))

Remaining failures by category: hallucination 1, prompt_defect 1

### E04 (edge_ambiguous, dev) - hallucination

- **Question:** What's the part no for the turbocharger for aux engine?
- **Expected:** AE-1500; Turbocharger cartridge for auxiliary engine (sources: spares_catalogue.csv)
- **Agent answered:** The part number for the turbocharger for auxiliary engine is AE-1501 [source: spares_catalogue.csv]. - AE-1501: Turbocharger cartridge for auxiliary engine [source: spares_catalogue.csv] - AE-1500: Turbocharger cartridge for auxiliary engine [source: spares_catalogue.csv] - AE-1502: Turbocharger cartridge for auxiliary engine [source: spares_catalogue.csv] - AE-1503: Turbocharger cartridge for auxiliary engine [source: spares_catalogue.csv] No...
- **Retrieved:** spares_catalogue.csv | tools: none
- **Rule-based diagnosis:** judge vetoed a deterministic pass (contradicts the reference: 'Note: Multiple part numbers describe turbochargers for auxiliary engines, but AE-1501 is the first listed.')
- **Root cause (LLM explanation of the evidence above):** The test case failed because the agent selected AE-1501 as the part number despite the reference note specifying that multiple part numbers describe turbochargers for auxiliary engines, and AE-1501 is only the first listed, not the only or correct one. The expected answer includes both AE-1500 and AE-1501, but the agent's response treats AE-1501 as the sole answer, contradicting the reference note that explicitly states multiple part numbers exist and AE-1501 is just the first listed.

### M03 (edge_multi_doc, holdout) - prompt_defect

- **Question:** For a vessel in Piraeus requiring urgent delivery, how long after order confirmation will an in-stock spare part be dispatched if express service is not available, and what is the maximum time for delivery to such a location?
- **Expected:** in-stock items are dispatched within 2 working days of order confirmation; delivery to vessels or agents in Piraeus or Fujairah takes 4 working days from order confirmation (sources: supplier_terms_a.pdf, supplier_terms_b.pdf)
- **Agent answered:** For a vessel in Piraeus requiring urgent delivery, an in-stock spare part will be dispatched within 3 working days of order confirmation if express service is not available [source: supplier_terms_b.pdf, page 1]. Delivery to such a location takes 4 working days from order confirmation [source: supplier_terms_b.pdf, page 1]. The maximum time for delivery to Piraeus is 4 working days from order confirmation. Note: Express service is not availabl...
- **Retrieved:** supplier_terms_b.pdf, supplier_terms_a.pdf | tools: none
- **Rule-based diagnosis:** context had the facts but the answer missed ['in-stock items are dispatched within 2 working days of order confirmation']
- **Root cause (LLM explanation of the evidence above):** The test case failed because the agent retrieved 'in-stock items are dispatched within 3 working days of order confirmation' from supplier_terms_b.pdf, but the expected answer specified 'within 2 working days of order confirmation', and this discrepancy is directly evidenced in supplier_terms_a.pdf where it states 'in-stock items are dispatched within 2 working days of order confirmation'.

## 8. Judge vs deterministic checks

The deterministic checks decide pass/fail. The LLM judge can veto a pass but never rescue a fail. Disagreements are listed so a human can audit both:

- E04: judge vetoed a deterministic pass (contradicts the reference: 'Note: Multiple part numbers describe turbochargers for auxiliary engines, but AE-1501 is the first listed.')
- M01: judge said fail but gave no verifiable quote for it (ignored)
- M02: judge said fail but gave no verifiable quote for it (ignored)
- M05: judge said fail but gave no verifiable quote for it (ignored)

## 9. Known limitations (read before trusting the numbers)

- **Small eval set:** 24 cases, so one case moves the pass rate by 4.2 points; the holdout has only 6 cases. Differences of 1-2 cases between iterations are within noise.
- **Generated evals share blind spots with the generator:** cases come from the same documents and a small model; verification guarantees the expected facts are really in the documents, not that the questions are representative of real users.
- **Fact matching is lexical:** numbers/IDs must match exactly and words must overlap. A correct answer that paraphrases heavily can fail (see judge disagreements); a wrong answer that repeats the right words can pass if the judge misses it.
- **Numbers grounding:** novel numbers are flagged as hallucinations, which also flags correct mental arithmetic, and the counting numbers 0-3 are ignored.
- **Judge noise:** the judge (`llama3.2:3b`) is itself a small model; its verdicts are only trusted when it quotes verifiable evidence.
- **Optimizer overfitting:** fixes were chosen on dev failures only; compare dev vs holdout in the table above. A dev gain without a holdout gain is likely overfitting.

## Artifacts in this folder

`requirements.json/.md`, `groundability.json`, `tool_selection.json`, `agent_definition_v*.json`, `agent_definition_final.json`, `evals.json`, `evals_generation_log.json`, `results_iter*.json`, `scorecard.json/.md`, `iteration_log.json/.md`, `run_stats.json`, `llm_calls.jsonl` (every prompt and response of this run).
