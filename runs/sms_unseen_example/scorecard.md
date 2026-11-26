# Scorecard

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 18/20 (90%) | 87% | 100% | 93% | 100% | 95% | 100% | 0 | 1 | 0 | 1 | 29.0s | baseline |
| 1 | v2 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 19.4s | reverted: no improvement |
| 2 | v3 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 16.0s | reverted: no improvement |
| 3 | v4 | 18/20 (90%) | 87% | 100% | 87% | 100% | 100% | 100% | 0 | 2 | 0 | 0 | 16.5s | reverted: no improvement |

Pass (all) counts every case; the optimizer only saw **dev** failures, **holdout** cases were never used to choose fixes. Correct = expected-fact recall >= 60% on answerable cases. Grounded = no numbers/IDs outside the retrieved context. Columns per category count failing cases.

- iteration 0: by type {'answerable': '9/10', 'edge_ambiguous': '4/4', 'edge_multi_doc': '1/1', 'out_of_scope': '4/5'}; judge vetoes 0; judge/deterministic disagreements 1; over-length answers 0%
- iteration 1: by type {'answerable': '9/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '1/1', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 4; over-length answers 0%
- iteration 2: by type {'answerable': '9/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '1/1', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 3; over-length answers 0%
- iteration 3: by type {'answerable': '9/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '1/1', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 3; over-length answers 7%
