"""Every structured object in ForgeAI, as Pydantic v2 models.

Two kinds of models live here:
* artifacts the factory writes to disk (Requirements, AgentDefinition, EvalCase, Scorecard ...)
* small "LLM output" models (suffix Out) that a single llm_json() call must satisfy.
  They are deliberately small: a 4B model fills a 5-field object far more reliably than a
  40-field one, so big artifacts are assembled in code from several small, validated calls.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# =========================================================== requirements stage
class QA(BaseModel):
    question: str
    answer: str
    answered_by: Literal["human", "requester_file", "assumed_default"] = "assumed_default"


class Evidence(BaseModel):
    source: str
    snippet: str


class TopicGrounding(BaseModel):
    topic: str
    status: Literal["supported", "partial", "unsupported"]
    evidence: list[Evidence] = []
    note: str = ""
    top_similarity: float = 0.0
    keyword_overlap: float = 0.0
    llm_status: str = ""
    served_by_tool: str = ""      # set when documents cannot support it but a registry tool can


class DocInfo(BaseModel):
    source: str
    type: str
    chars: int
    pages: int = 0
    rows: int = 0
    columns: list[str] = []
    headings: list[str] = []
    summary: str = ""


class Requirements(BaseModel):
    brief: str
    agent_name: str
    scope: str
    audience: str
    tone: str
    must_answer_topics: list[str]
    must_refuse_topics: list[str]
    brief_demands: list[str] = []      # what the brief itself asks for (verified to come from the brief)
    clarifying_qa: list[QA] = Field(default_factory=list, max_length=5)
    groundability: list[TopicGrounding] = []
    warnings: list[str] = []
    documents: list[DocInfo] = []


# LLM outputs for the intake stage ------------------------------------------------
class DocSummaryOut(BaseModel):
    summary: str = Field(description="2-3 sentences: what this document covers and for whom")


class ClarifyingQuestion(BaseModel):
    question: str
    why: str = ""
    default_answer: str = Field(description="the most sensible assumption if nobody answers")


class ClarifyingQuestionsOut(BaseModel):
    questions: list[ClarifyingQuestion] = Field(max_length=8)


class BriefDemandsOut(BaseModel):
    demands: list[str] = Field(min_length=1, max_length=8,
                               description="each distinct thing the brief asks for, in the brief's own words")


class RequesterAnswerOut(BaseModel):
    note_numbers: list[int] = Field(default_factory=list, description="numbers of the notes that answer it")


class RequirementsDraftOut(BaseModel):
    agent_name: str
    scope: str
    audience: str
    tone: str
    must_answer_topics: list[str] = Field(min_length=1, max_length=10)
    must_refuse_topics: list[str] = Field(default_factory=list, max_length=8)


class ToolForTopicOut(BaseModel):
    tool: str = Field(default="", description="registry tool name that can provide this, or empty")
    reason: str = ""


class GroundingVerdictOut(BaseModel):
    status: Literal["supported", "partial", "unsupported"]
    quote: str = Field(description="verbatim sentence copied from the excerpts, or empty")
    source: str = ""
    reason: str = ""


# =========================================================== agent definition
class Chunking(BaseModel):
    chunk_size: int = Field(ge=200, le=3000)
    chunk_overlap: int = Field(ge=0, le=600)


class RetrievalConfig(BaseModel):
    top_k: int = Field(ge=1, le=15)
    mode: Literal["dense", "bm25", "hybrid"] = "hybrid"
    min_score: float = Field(ge=0.0, le=0.9, default=0.2)
    query_rewrite: bool = False


class OutputContract(BaseModel):
    format: Literal["markdown", "json"] = "markdown"
    require_citations: bool = True
    refusal_phrase: str
    max_words: int = Field(ge=30, le=400, default=180)
    fields: list[str] = []


class PromptSpec(BaseModel):
    """The structured source of the system prompt. The optimizer patches THIS, not free text."""
    role: str
    audience: str = ""
    tone: str = ""
    answer_topics: list[str] = []
    rules: list[str]
    refuse_topics: list[str]
    answer_style: str
    partial_topics: list[str] = []


class LLMConfig(BaseModel):
    temperature: float = Field(ge=0.0, le=1.0, default=0.2)


class AgentDefinition(BaseModel):
    name: str
    version: int = 1
    created_from: str
    description: str = ""
    system_prompt: str
    prompt_spec: PromptSpec
    chunking: Chunking
    retrieval: RetrievalConfig
    tools: list[str] = []
    tool_rationale: dict[str, str] = {}
    output_contract: OutputContract
    documents_dir: str
    llm: LLMConfig = LLMConfig()
    config_rationale: dict[str, str] = {}


# LLM outputs for the generator stage -----------------------------------------------
class ToolDecision(BaseModel):
    name: str
    needed: bool
    brief_quote: str = Field(default="", description="exact words from the brief/answers that require this tool")
    rationale: str = ""


class ToolSelectionOut(BaseModel):
    decisions: list[ToolDecision]


class PromptDraftOut(BaseModel):
    role: str = Field(description="2-4 sentences: who the assistant is, who it serves, its scope and tone")
    rules: list[str] = Field(min_length=2, max_length=8, description="domain-specific behaviour rules")
    answer_style: str = Field(description="one sentence describing the answer format")
    max_words: int = Field(ge=40, le=300, default=150)


# =========================================================== evals
CaseType = Literal["answerable", "out_of_scope", "edge_ambiguous", "edge_multi_doc"]


class EvalCase(BaseModel):
    id: str
    type: CaseType
    question: str
    expected_sources: list[str] = []
    expected_facts: list[str] = []
    should_refuse: bool = False
    source_quotes: list[str] = []
    tools_expected: list[str] = []
    verified: bool = False
    split: Literal["dev", "holdout"] = "dev"
    origin: str = ""          # how it was generated (chunk ids / refuse topic ...)
    notes: str = ""


class GenFact(BaseModel):
    fact: str = Field(description="short fact (2-10 words), copy numbers exactly")
    quote: str = Field(description="verbatim sentence from the passage that states this fact")


class GenCaseOut(BaseModel):
    question: str
    facts: list[GenFact] = Field(min_length=1, max_length=4)


class GenMultiFact(BaseModel):
    fact: str
    passage: Literal["A", "B"]
    quote: str


class GenMultiCaseOut(BaseModel):
    question: str
    facts: list[GenMultiFact] = Field(min_length=2, max_length=4)


class GenToolCaseOut(BaseModel):
    question: str
    expression: str = Field(description="arithmetic expression using numbers from the passage")
    quote: str
    fact: str = Field(description="the final answer as a short phrase containing the computed number")


class GenOOSOut(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=8)


class FactCheckOut(BaseModel):
    relevant: list[int] = Field(description="numbers of the facts that belong in a correct answer")


class AnswerabilityOut(BaseModel):
    answerable: bool
    quote: str = ""


# =========================================================== runtime / judging
class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str
    text: str
    score: float
    dense: float = 0.0
    page: Optional[int] = None


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = {}
    result: str = ""
    ok: bool = True


class AgentAnswer(BaseModel):
    question: str
    answer: str
    cited_sources: list[str] = []
    retrieved: list[RetrievedChunk] = []
    tools_called: list[ToolCall] = []
    refused: bool = False
    abstained_no_context: bool = False
    latency_s: float = 0.0
    rewritten_query: str = ""


class ToolStepOut(BaseModel):
    action: Literal["call", "answer"]
    tool: str = ""
    args: dict[str, Any] = {}
    reason: str = ""


class JudgeOut(BaseModel):
    answers_question: bool
    supported_by_context: bool
    evidence_quote: str = Field(default="", description="verbatim text from the CONTEXT supporting the answer")
    contradicts_reference: bool
    contradiction_quote: str = Field(default="", description="verbatim words from the ANSWER that contradict")
    unsupported_claim: str = Field(default="", description="verbatim words from the ANSWER not backed by context")


FailureCategory = Literal["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"]


class CaseResult(BaseModel):
    case_id: str
    type: str
    split: str
    question: str
    answer: str
    retrieved_sources: list[str]
    cited_sources: list[str]
    tools_called: list[str]
    refused: bool
    should_refuse: bool
    grounded: bool
    correct: bool
    refused_correctly: Optional[bool] = None
    citation_ok: bool = True
    fact_recall: float = 0.0
    missing_facts: list[str] = []
    context_fact_recall: float = 0.0
    novel_numbers: list[str] = []
    word_count: int = 0
    over_length: bool = False
    judge: Optional[dict[str, Any]] = None
    judge_veto: bool = False
    judge_disagreement: str = ""
    judge_notes: str = ""
    failure_category: Optional[FailureCategory] = None
    diagnosis: str = ""
    passed: bool = False
    latency_s: float = 0.0


class Scorecard(BaseModel):
    iteration: int
    definition_version: int
    n_cases: int
    pass_rate: float
    dev_pass_rate: float
    holdout_pass_rate: float
    grounded_rate: float
    correct_rate: float
    refusal_accuracy: float
    citation_rate: float
    over_length_rate: float
    failures_by_category: dict[str, int]
    pass_by_type: dict[str, str]
    avg_latency_s: float
    judge_vetoes: int
    judge_disagreements: int
    results: list[CaseResult]


class Change(BaseModel):
    category: str
    what: str
    why: str
    failures_addressed: list[str]
    diff: str = ""


class IterationRecord(BaseModel):
    iteration: int
    from_version: int
    to_version: int
    categories_targeted: list[str]
    changes: list[Change]
    before_score: float
    after_score: float
    before_dev: float
    after_dev: float
    flipped_to_pass: list[str] = []
    flipped_to_fail: list[str] = []
    decision: Literal["kept", "reverted: regression", "reverted: no improvement"]
    note: str = ""


class PromptPatchOut(BaseModel):
    add_rules: list[str] = Field(default_factory=list, max_length=3)
    modify_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=3,
                                               description='[{"index": int, "new_text": str}]')
    rationale: str = ""

    @field_validator("add_rules")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [r.strip() for r in v if r and r.strip()]


class TopicOut(BaseModel):
    topic: str = Field(description="short general topic name, 2-6 words")


class RootCauseOut(BaseModel):
    explanation: str
