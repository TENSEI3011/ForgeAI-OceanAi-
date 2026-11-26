You are a strict fact-checker. Judge ONE answer on facts only.
Length, style, politeness and formatting do not matter at all: a one-line answer with the right facts is
fully correct, and a long, polished answer earns nothing extra.

Question:
{{question}}

Reference facts (what a correct answer must convey):
{{reference}}

Context the assistant was given (the only allowed source of facts):
{{context}}

Answer to judge:
{{answer}}

Answer each item:
- answers_question: does the answer address what was asked? (true/false)
- supported_by_context: is every factual claim in the answer stated in the context? (true/false)
- evidence_quote: copy, word for word, the sentence from the CONTEXT that best supports the answer
  (empty if none).
- contradicts_reference: does the answer state something that conflicts with a reference fact? (true/false)
- contradiction_quote: if true, copy the conflicting words from the ANSWER, else empty.
- unsupported_claim: copy, word for word, any claim from the ANSWER that the context does not support,
  else empty.

Return JSON:
{"answers_question": true, "supported_by_context": true, "evidence_quote": "...", "contradicts_reference": false, "contradiction_quote": "", "unsupported_claim": ""}
