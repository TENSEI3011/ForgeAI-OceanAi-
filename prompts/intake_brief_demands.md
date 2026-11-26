List every distinct thing this brief asks the assistant to do or to answer.

Brief:
"""{{brief}}"""

Rules:
- One item per distinct subject area or capability the requester names (typically 2-6 items).
- Use the brief's OWN words for each item (copy the phrase; do not paraphrase, do not add anything),
  but drop the shared lead-in: from "help users with A, B and C" list "A", "B", "C".
- Include side requests too (e.g. a calculation, a live lookup), and examples the requester gives
  ("such as ...") as part of the item they belong to.

Return JSON: {"demands": ["...", "..."]}
