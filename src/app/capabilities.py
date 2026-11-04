"""Cartão de capacidades e política de ações (`policy:capabilities`): o que o assistente pode fazer, citável.

Gerado de forma determinística do registro de ferramentas (descrição, `write`, `risk`), da mecânica de ações
(app/actions.py: escrita só propõe; risco alto = confirmação do dono + aprovação de operador; TTL) e do fluxo
humano (escalonamento com protocolo, resposta do atendente na conversa). Por que existe: a regra do sistema
("a antecipação precisa da sua confirmação e da aprovação de um atendente") é verdadeira, mas não estava em
nenhuma fonte nem resultado de ferramenta; quem redige a usava e o juiz (e a checagem de frases) a via sem base.
Com o cartão, a regra vira evidência do turno: entra no prompt de quem redige, na lista de evidência (números
dele contam, ex. o TTL) e no `context` que o juiz lê.

O domínio acrescenta linhas próprias com `POLICY_LINES` (lista de frases, ou {"pt": [...], "en": [...]}) e ajusta
as palavras de cada ação com `ACTION_KEYWORDS` ({tool: [palavras]}), usadas pela checagem de ação oferecida
(app/claims.py). `LABELS` ({nome ou valor interno: "palavras" ou {"pt": ..., "en": ...}}) dá as palavras que o
cliente lê no lugar de um valor de lista fechada ("sem_sinal" → "sem sinal" / "no signal"), de um parâmetro e de
uma tool de escrita (aviso da decisão do operador, app/actions.py); sem rótulo, o valor sai com espaços no lugar
de "_". Sem LLM e sem I/O: o mesmo registro dá sempre o mesmo texto.
"""
from __future__ import annotations

import re

from . import domain
from .config import action_ttl_min

CARD_ID = "policy:capabilities"

_TEXT = {
    "pt": {
        "head": "Capacidades e política de ações deste assistente (gerado do registro de ferramentas do sistema):",
        "read": "Consultas que o assistente executa na hora, só com dados do cliente autenticado",
        "write": "Ações que o assistente pode PROPOR; nada é executado antes de o cliente confirmar a proposta",
        "high": ("Ações de risco alto: exigem a confirmação do cliente E, depois, a aprovação de um atendente "
                 "humano (operador) antes de executar"),
        "ttl": "Proposta de ação não confirmada expira em {ttl} minutos.",
        "human": ("Encaminhar para um atendente humano: abre um caso com protocolo; a resposta do atendente aparece "
                  "nesta mesma conversa."),
        "none": "Fora dessas ferramentas, o assistente não executa nenhuma ação no sistema.",
        "verdict": ("Decisão sobre caso individual (contestação, bloqueio ou liberação de valor retido) é de um "
                    "atendente humano; o assistente não decide."),
        "ids": "Identificadores que as consultas aceitam",
        "options": "Valores que as consultas e ações aceitam (lista fechada: outro valor não é aceito)",
        "default": "padrão",
    },
    "en": {
        "head": "Capabilities and action policy of this assistant (generated from the system's tool registry):",
        "read": "Lookups the assistant runs immediately, only on the authenticated customer's data",
        "write": "Actions the assistant can PROPOSE; nothing runs until the customer confirms the proposal",
        "high": ("High-risk actions: they need the customer's confirmation AND then the approval of a human agent "
                 "(operator) before they run"),
        "ttl": "An action proposal that is not confirmed expires after {ttl} minutes.",
        "human": ("Hand the case to a human agent: opens a case with a ticket number; the agent's reply shows up in "
                  "this same conversation."),
        "none": "Apart from these tools, the assistant does not carry out any action in the system.",
        "verdict": ("A decision on an individual case (dispute, block or release of a held amount) belongs to a human "
                    "agent; the assistant does not decide it."),
        "ids": "Identifiers the lookups accept",
        "options": "Values the lookups and actions accept (closed list: no other value is accepted)",
        "default": "default",
    },
}


def policy(name: str) -> dict | None:
    from .risk import policy as risk_policy

    return risk_policy(name)


def _tools() -> dict[str, dict]:
    from .tools import registry

    return registry()


def _domain_lines(language: str) -> list[str]:
    lines = getattr(domain.active(), "POLICY_LINES", None) or []
    if isinstance(lines, dict):
        lines = lines.get(language) or lines.get("pt") or []
    return [str(line).strip() for line in lines if str(line).strip()]


def _entry(name: str, tool: dict) -> str:
    from .risk import describe  # com limite de valor (RISK_POLICY), a regra de aprovação entra na descrição

    desc = " ".join(describe(name, {**tool, "description": str(tool.get("description", ""))}).split())
    return f"{name} ({desc})" if desc else name


def example_of(pattern: str) -> str | None:
    """Exemplo legível de um padrão simples de id ("^T\\d{4}[A-Z]$" → "T0000A"); None se o padrão não é simples."""
    body = pattern.strip("^$")
    out = re.sub(r"\\d\{(\d+)\}", lambda m: "0" * int(m.group(1)), body)
    out = out.replace("\\d+", "0").replace("\\d", "0").replace("[A-Z]", "A").replace("[a-z]", "a")
    return out if re.fullmatch(r"[A-Za-z0-9_-]+", out) else None


def _id_lines(tools: dict[str, dict]) -> list[str]:
    """Formato de cada identificador dos parâmetros das tools (medido: "informe o código no formato
    TX + 4 dígitos" vinha da descrição da tool, que o redator lê e o juiz não; sem base aos olhos do juiz)."""
    seen: dict[str, str] = {}
    for tool in tools.values():
        props = ((tool.get("input_schema") or tool.get("parameters") or {}).get("properties") or {})
        for name, spec in props.items():
            if not isinstance(spec, dict) or not spec.get("pattern") or name in seen:
                continue
            ex = example_of(str(spec["pattern"]))
            desc = str(spec.get("description", "")).strip()
            seen[name] = f"{name}" + (f" = {desc}" if desc else "") + (f" (ex.: {ex})" if ex else "")
    return list(seen.values())


def label(name: object, language: str = "pt") -> str | None:
    """Palavras que o domínio deu (`LABELS`) a um nome ou valor interno, no idioma; None se ele não deu."""
    found = (getattr(domain.active(), "LABELS", None) or {}).get(str(name))
    if isinstance(found, dict):
        found = found.get(language) or found.get("pt")
    return " ".join(str(found or "").split()) or None


def option_label(value: object, language: str = "pt") -> str:
    """O que o cliente lê no lugar de um valor de lista fechada: o rótulo do domínio ou o valor sem "_"."""
    return label(value, language) or " ".join(str(value).replace("_", " ").split())


def _enum_values(tools: dict[str, dict]) -> set[str]:
    return {str(v) for tool in tools.values()
            for spec in ((tool.get("input_schema") or tool.get("parameters") or {}).get("properties") or {}).values()
            if isinstance(spec, dict) and isinstance(spec.get("enum"), list) for v in spec["enum"]}


def readable_values(text: str, language: str = "pt", tools: dict[str, dict] | None = None) -> str:
    """Valor interno de lista fechada escrito na resposta vira o rótulo: medido no ensaio (rodada 11), 36 de 362
    respostas ao vivo mostravam "sem_sinal" ou "sem_conexao" ao cliente. Só valor com "_": "pix" e "today" já são
    palavras. A crase em volta sai junto; a tradução que o modelo pôs entre parênteses não fica repetida."""
    values = sorted((v for v in _enum_values(_tools() if tools is None else tools) if "_" in v), key=len, reverse=True)
    if not values or not any(v in text for v in values):
        return text
    used: set[str] = set()

    def words(m: re.Match) -> str:
        said = option_label(m.group(1), language)
        used.add(said)
        return said

    text = re.sub(r"`?(?<![\w/@.-])(" + "|".join(map(re.escape, values)) + r")(?![\w/@-])`?", words, text)
    for said in used:  # "sem_conexao" (no connection), com o rótulo "no connection" → "no connection"
        said = re.escape(said)
        text = re.sub(rf"({said})([\"”']?)[ \t]*\([ \t]*{said}[ \t]*\)", r"\1\2", text, flags=re.IGNORECASE)
    return text


def _option_lines(tools: dict[str, dict], language: str = "pt") -> list[str]:
    """Valores de cada parâmetro de lista fechada (enum), POR TOOL, com o padrão quando o schema o declara. "A consulta
    cobre ontem, hoje e os últimos 7 dias" é verdade do sistema, mas estava só no schema da tool, que o redator lê e o
    juiz não: a frase verdadeira contava como afirmação sem base. Por tool porque o mesmo parâmetro (período) tem
    padrão diferente em cada consulta; juntar as duas fazia o modelo escolher o período errado.
    Cada valor sai pelo rótulo legível (o valor cru fica no schema, para a chamada): o redator copiava o valor do
    cartão para o cliente ("with the reason \"sem_sinal\" or \"sem_conexao\"")."""
    default_word = _TEXT.get(language, _TEXT["pt"])["default"]
    out = []
    for tool_name, tool in tools.items():
        props = ((tool.get("input_schema") or tool.get("parameters") or {}).get("properties") or {})
        params = []
        for name, spec in props.items():
            values = spec.get("enum") if isinstance(spec, dict) else None
            if isinstance(values, list) and values:
                default = (f" ({default_word} {option_label(spec['default'], language)})"
                           if spec.get("default") is not None else "")
                params.append(f"{label(name, language) or name}{default}: "
                              + " | ".join(option_label(v, language) for v in values))
        if params:
            out.append(f"{tool_name} — " + "; ".join(params))
    return out


def card(language: str = "pt", tools: dict[str, dict] | None = None, extra: list[str] | None = None) -> str:
    """Texto do cartão no idioma do turno. `tools`/`extra` só para medir com outro registro (evals offline)."""
    t = _TEXT.get(language, _TEXT["pt"])
    tools = _tools() if tools is None else tools
    groups: dict[str, list[str]] = {"read": [], "write": [], "high": []}
    for name, tool in tools.items():
        kind = "high" if tool.get("write") and tool.get("risk") == "high" else "write" if tool.get("write") else "read"
        if kind == "high" and policy(name):  # quatro olhos só acima do limite: a descrição diz o limite
            kind = "write"
        groups[kind].append(_entry(name, tool))
    lines = [f"[{CARD_ID}] {t['head']}"]
    lines += [f"- {t[k]}: " + "; ".join(v) + "." for k, v in groups.items() if v]
    if groups["write"] or groups["high"]:
        lines.append("- " + t["ttl"].format(ttl=action_ttl_min()))
    lines += ["- " + t["human"], "- " + t["verdict"], "- " + t["none"]]
    ids = _id_lines(tools)
    if ids:
        lines.append(f"- {t['ids']}: " + "; ".join(ids) + ".")
    options = _option_lines(tools, language)
    if options:
        lines.append(f"- {t['options']}: " + " · ".join(options) + ".")
    lines += [f"- {line}" for line in (_domain_lines(language) if extra is None else extra)]
    return "\n".join(lines)


def prompt_block(language: str = "pt") -> str:
    """Bloco para o prompt de quem redige: o cartão como fonte citável, com a regra de uso."""
    rule = ("Ofereça só ações que estão neste cartão e descreva a política exatamente como está nele "
            f"(cite [{CARD_ID}]); não ofereça ação que não esteja aqui." if language != "en" else
            "Only offer actions listed in this card and describe the policy exactly as written here "
            f"(cite [{CARD_ID}]); never offer an action that is not listed.")
    return f"<capabilities>\n{card(language)}\n</capabilities>\n{rule}"
