"""Contrato público da API.

Congelado no commit do contrato (minuto ~5): forks NÃO alteram este arquivo — ele está em
`frozen` no OWNERSHIP.json. Campo novo exige decisão da sessão principal, porque todo fork,
teste e eval depende desta forma.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Especialistas do kit. O desafio troca os nomes (ex.: knowledge/support) aqui e em agents.AGENTS.
AgentName = Literal["faq", "records", "escalation"]
# "partial": o faq respondeu o que a fonte cobre e disse o que falta; não escala por si
AgentStatus = Literal["ok", "partial", "insufficient", "error"]


class ChatRequest(BaseModel):
    """`user_id` do corpo só vale com AUTH_MODE=demo (marcado identity_verified=false).

    Com AUTH_MODE=required a identidade vem exclusivamente do Bearer token.
    """
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


class RouterDecision(BaseModel):
    intent: str
    plan: list[AgentName]
    language: Literal["pt", "en"]
    confidence: float = Field(ge=0, le=1)


class ToolCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
    ok: bool = True


class Source(BaseModel):
    id: str
    title: str
    url: str


class Handoff(BaseModel):
    required: bool = False
    reason: str | None = None
    ticket_id: str | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ChatResponse(BaseModel):
    trace_id: str
    conversation_id: str
    user_id: str
    identity_verified: bool = True
    answer: str
    intent: str
    confidence: float = 1.0
    route: list[str]
    replans: list[str] = Field(default_factory=list)
    # quem decidiu: "llm" (supervisor LLM, laço de tool use), "fast_path" (atalho de 1 passo com LLM ligado: o
    # especialista responde e, se não resolver, o supervisor LLM decide) ou "table" (determinístico: offline e queda
    # do LLM)
    engine: Literal["table", "fast_path", "llm"] = "table"
    language: Literal["pt", "en"] = "pt"
    sources: list[Source] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    handoff: Handoff = Field(default_factory=Handoff)
    pending_action: str | None = None
    blocked: bool = False
    guardrails: list[str] = Field(default_factory=list)
    # números da resposta sem base em fonte, tool, template ou pergunta (app/grounding.py); [] = tudo conferido
    unsupported_numbers: list[str] = Field(default_factory=list)
    # promessa financeira / compromisso legal sem base na evidência do turno (app/grounding.py::risk_flags)
    risk_flags: list[str] = Field(default_factory=list)
    # o que a checagem numérica fez (NUMBERS_POLICY, app/grounding.py): none = nada sem base; regenerated = a
    # reescrita tirou o número; redacted = trocado por "[valor não confirmado]" com oferta de humano; escalated =
    # trocado e caso aberto; flagged = só sinalizado (NUMBERS_POLICY=flag)
    numbers_action: Literal["none", "regenerated", "redacted", "escalated", "flagged"] = "none"
    # estado do caso de suporte (app/casestate.py): só "resolved" com prova do cliente ou da ferramenta
    case_state: str | None = None
    usage: Usage = Field(default_factory=Usage)
    # {arquivo de prompt: hash curto} das instruções usadas neste atendimento (observability.record_prompt)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    # o que sustentou a resposta (resultado de tool, trecho citado, resultado web, cartão policy:capabilities), já
    # mascarado: o juiz lê isto
    evidence: list[str] = Field(default_factory=list)
    # frases sem base na evidência ou oferta de ação que nenhuma ferramenta faz (app/claims.py):
    # [{index, sentence, reason, source: llm|lexical|offer, action: removed|flagged}]; [] = nada apontado
    unsupported_claims: list[dict] = Field(default_factory=list)
    # o que a checagem de frases fez (CLAIMS_POLICY): none | removed | flagged | kept_original (corte quebraria a
    # resposta: fica a original, sinalizada)
    claims_action: Literal["none", "removed", "flagged", "kept_original"] = "none"
    # árvore de passos do turno (supervisor.step_view): agente, status, ms, ferramentas com args e prévia mascarada
    steps: list[dict] = Field(default_factory=list)
