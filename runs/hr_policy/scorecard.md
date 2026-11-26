# Scorecard

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 19/20 (95%) | 100% | 80% | 100% | 100% | 100% | 93% | 0 | 1 | 0 | 0 | 6.0s | baseline |

Pass (all) counts every case; the optimizer only saw **dev** failures, **holdout** cases were never used to choose fixes. Correct = expected-fact recall >= 60% on answerable cases. Grounded = no numbers/IDs outside the retrieved context. Columns per category count failing cases.

- iteration 0: by type {'answerable': '9/10', 'edge_ambiguous': '4/4', 'edge_multi_doc': '1/1', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 3; over-length answers 0%
