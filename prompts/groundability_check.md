You check whether a document collection can support a topic that an assistant is expected to answer.

The assistant's brief: "{{brief}}"
Topic to check: "{{topic}}"

The most relevant excerpts found in the documents:
{{excerpts}}

Using ONLY these excerpts, decide:
- "supported": the excerpts contain concrete information (rules, numbers, procedures, items) that
  directly answers typical user questions about this topic.
- "partial": the excerpts cover some aspects of the topic but clearly miss important parts.
- "unsupported": the excerpts do not substantively cover the topic. A passing mention of a word is
  NOT support. Related-but-different subjects are NOT support.

For "supported" or "partial", copy one sentence word-for-word from the excerpts as "quote" and give its
file name as "source". For "unsupported", leave quote empty.

Return JSON: {"status": "supported|partial|unsupported", "quote": "...", "source": "...", "reason": "one short sentence"}
