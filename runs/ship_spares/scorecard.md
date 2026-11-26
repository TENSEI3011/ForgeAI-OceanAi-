# Scorecard

| Iter | Def | Pass (all) | Dev | Holdout | Correct | Grounded | Refusal acc. | Citations | retrieval_miss | prompt_defect | hallucination | wrong_refusal | Avg latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v1 | 20/24 (83%) | 83% | 83% | 84% | 100% | 100% | 95% | 0 | 4 | 0 | 0 | 429.8s | baseline |
| 1 | v2 | 21/24 (88%) | 89% | 83% | 90% | 95% | 100% | 100% | 0 | 2 | 1 | 0 | 24.1s | kept |
| 2 | v3 | 22/24 (92%) | 94% | 83% | 95% | 100% | 100% | 100% | 0 | 1 | 1 | 0 | 23.1s | kept |

Pass (all) counts every case; the optimizer only saw **dev** failures, **holdout** cases were never used to choose fixes. Correct = expected-fact recall >= 60% on answerable cases. Grounded = no numbers/IDs outside the retrieved context. Columns per category count failing cases.

- iteration 0: by type {'answerable': '10/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '2/5', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 4; over-length answers 0%
- iteration 1: by type {'answerable': '10/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '3/5', 'out_of_scope': '5/5'}; judge vetoes 0; judge/deterministic disagreements 5; over-length answers 0%
- iteration 2: by type {'answerable': '10/10', 'edge_ambiguous': '3/4', 'edge_multi_doc': '4/5', 'out_of_scope': '5/5'}; judge vetoes 1; judge/deterministic disagreements 4; over-length answers 0%
