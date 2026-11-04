"""Cassete: o ao vivo grava cada resposta do LLM e `LLM_PROVIDER=replay` reproduz sem chave nem rede."""
import itertools
import json
import re
import threading
from types import SimpleNamespace as NS

import pytest
from fakes import FakeMessages, resp, text, tool_use

from app import llm as llm_mod
from app.llm import AnthropicLLM, Cassette, CassetteMiss, LLMError, ReplayLLM, get_llm, request_key
from evals import run_evals


def _kwargs(content="oi", system="sys", **extra):
    return {"system": system, "messages": [{"role": "user", "content": content}], **extra}


def test_key_depends_on_role_model_and_request_but_not_on_volatile_parts():
    base = request_key("agent", "claude-sonnet-5-5", _kwargs("pedido T-1a2b3c4d de 2026-11-01 (Sunday)"))
    assert base == request_key("agent", "claude-sonnet-5-5", _kwargs("pedido T-9f8e7d6c de 2026-12-24 (Thursday)"))
    assert base != request_key("router", "claude-sonnet-5-5", _kwargs("pedido T-1a2b3c4d de 2026-11-01 (Sunday)"))
    assert base != request_key("agent", "claude-haiku-5-5", _kwargs("pedido T-1a2b3c4d de 2026-11-01 (Sunday)"))
    assert base != request_key("agent", "claude-sonnet-5-5", _kwargs("outro pedido"))
    assert request_key("a", "m", _kwargs(tools=[{"name": "x"}])) != request_key("a", "m", _kwargs(tools=[]))


def test_save_is_plain_jsonl_or_gzip_when_large(tmp_path, monkeypatch):
    cas = Cassette()
    cas.record("k1", "agent", "m", response={"stop_reason": "end_turn", "content": [{"type": "text", "text": "a"}]})
    small = cas.save(tmp_path / "official.jsonl")
    assert small.name == "official.jsonl"
    monkeypatch.setattr(llm_mod, "CASSETTE_GZ_BYTES", 10)
    big = cas.save(tmp_path / "official.jsonl")
    assert big.name == "official.jsonl.gz" and not small.exists()  # nunca dois cassetes do mesmo split
    assert big.read_bytes() == cas.save(tmp_path / "official.jsonl").read_bytes()  # gzip sem data: mesmos bytes
    assert Cassette.load([big]).entries == cas.entries


def test_recorded_api_call_replays_with_attribute_access_and_dict_input():
    msgs = FakeMessages([resp("tool_use", text("vou olhar"), tool_use("lookup_record", {"order": "P-1"}))])
    live = AnthropicLLM("claude-sonnet-5-5", "low", client=NS(messages=msgs))
    live.role = "agent"
    with llm_mod.recording() as cas:
        got = live.create("sys", [{"role": "user", "content": "meu pedido"}], tools=[{"name": "lookup_record"}])
    assert got.stop_reason == "tool_use" and len(cas.entries) == 1
    replay = ReplayLLM("agent", "claude-sonnet-5-5", "low", Cassette(cas.entries))
    back = replay.create("sys", [{"role": "user", "content": "meu pedido"}], tools=[{"name": "lookup_record"}])
    block = back.content[1]
    assert (back.stop_reason, back.content[0].text, block.name, dict(block.input)) == \
        ("tool_use", "vou olhar", "lookup_record", {"order": "P-1"})
    assert getattr(block, "citations", None) is None  # campo ausente = AttributeError, como no SDK


def test_miss_says_record_again_and_is_counted(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "replay")
    monkeypatch.setenv("LLM_CASSETTE", "")
    monkeypatch.setattr(llm_mod, "cassette_files", lambda directory=None: [])
    llm_mod.reset_replay()
    replay = get_llm("router")
    assert isinstance(replay, ReplayLLM) and replay.enabled
    with pytest.raises(CassetteMiss, match="grave de novo"):
        replay.complete("sys", [{"role": "user", "content": "nunca gravado"}])
    assert llm_mod.replay_misses() == 1
    llm_mod.reset_replay()
    assert llm_mod.replay_misses() == 0


def test_error_entry_and_refusal_replay_as_llm_errors():
    cas = Cassette()
    k1 = request_key("agent", "m", _kwargs("a", max_tokens=4096))
    cas.record(k1, "agent", "m", error={"kind": "rate_limited", "message": "rate_limited: 429"})
    replay = ReplayLLM("agent", "m", "low", cas)
    with pytest.raises(LLMError) as err:
        replay.complete("sys", [{"role": "user", "content": "a"}])
    assert err.value.kind == "rate_limited"
    k2 = request_key("agent", "m", _kwargs("b", max_tokens=4096))
    cas.record(k2, "agent", "m", response={"stop_reason": "refusal", "content": [], "usage": {}})
    with pytest.raises(LLMError) as refusal:
        replay.complete("sys", [{"role": "user", "content": "b"}])
    assert refusal.value.kind == "refusal"


# --- ponta a ponta: gravar o ao vivo com um cliente falso e reproduzir no "CI" -----------------------------------
class ScriptedAPI:
    """Cliente Anthropic falso e não determinístico: cada resposta leva um contador (o replay tem de devolvê-lo)."""

    def __init__(self):
        self.counter, self.lock = itertools.count(1), threading.Lock()
        self.messages = NS(create=self.create)

    def create(self, **kwargs):
        with self.lock:
            n = next(self.counter)
        if (kwargs.get("output_config") or {}).get("format"):
            return resp("end_turn", text("{}"))  # JSON fora do contrato: router/guardrail caem no offline
        return resp("end_turn", text(f"Resposta gravada número {n}, de acordo com a fonte."))


@pytest.fixture
def fake_live(monkeypatch):
    api = ScriptedAPI()
    monkeypatch.setattr(llm_mod, "_anthropic", lambda model, effort: AnthropicLLM(model, effort, client=api))
    return api


def test_live_records_cassette_with_floors_and_replay_reproduces_it(fake_live):
    live = run_evals.run(split="official", live=True, repeat=2, workers=2)
    cas = live["cassette"]
    assert cas["requests"] > 0 and cas["repeat"] == 2 and cas["file"].endswith("official.jsonl")
    assert cas["floors"]["intent_acc"] == live["metrics"]["official"]["intent_acc"]
    assert "pass_at_1" in cas["floors"] and "max_crashes" in cas["floors"]
    assert (run_evals.cassettes_dir() / "official.jsonl").exists()
    summary = run_evals.run_replay()
    entry = summary["splits"]["official"]
    assert summary["passed"], entry["problems"]
    assert entry["misses"] == 0 and all(c["ok"] for c in entry["comparison"].values())
    replayed = json.loads((run_evals.replay_dir() / "replay_official.json").read_text(encoding="utf-8"))
    assert replayed["provider"] == "replay"
    key = lambda r: (r["id"], r["run"])  # noqa: E731
    # protocolo do caso é sorteado pelo store a cada execução (não vem do LLM): sai da comparação, como sai da chave
    ticket = lambda a: re.sub(r"\bT-[0-9a-f]{8}\b", "T-<ID>", a)  # noqa: E731
    answers = lambda rows: {key(r): ticket(r["answer"]) for r in rows}  # noqa: E731
    assert answers(replayed["rows"]) == answers(live["rows"])
    assert run_evals.main(["--replay"]) == 0


def test_replay_fails_below_floor_or_on_missing_recording(fake_live):
    run_evals.run(split="official", live=True, repeat=1)
    path = run_evals.RESULTS_DIR / "live_official.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["cassette"]["floors"]["pass_at_1"] = 100.1  # piso impossível: o replay tem de reprovar
    path.write_text(json.dumps(rec), encoding="utf-8")
    summary = run_evals.run_replay()
    assert not summary["passed"] and any("pass_at_1" in p for p in summary["splits"]["official"]["problems"])
    # cassete esvaziado: todo pedido vira falta e a mensagem manda gravar de novo
    (run_evals.cassettes_dir() / "official.jsonl").write_text("", encoding="utf-8")
    rec["cassette"]["floors"]["pass_at_1"] = 0
    path.write_text(json.dumps(rec), encoding="utf-8")
    summary = run_evals.run_replay()
    problems = summary["splits"]["official"]["problems"]
    assert not summary["passed"] and any("grave de novo" in p for p in problems)
    assert run_evals.main(["--replay"]) == 1


def test_replay_without_accepted_recording_refuses(tmp_path):
    run_evals.cassettes_dir().mkdir(parents=True)
    (run_evals.cassettes_dir() / "memory.jsonl").write_text("", encoding="utf-8")
    summary = run_evals.run_replay()
    assert not summary["passed"] and "grave de novo" in summary["splits"]["memory"]["problems"][0]


def test_smoke_outside_results_does_not_rerecord_the_ci_cassette(tmp_path, monkeypatch):
    from evals import run_evals

    monkeypatch.delenv("EVAL_CASSETTE", raising=False)
    assert run_evals.records_cassette(None) and run_evals.records_cassette(run_evals.RESULTS_DIR / "live_x.json")
    assert not run_evals.records_cassette(tmp_path / "smoke.json")  # fumaça fora de evals/results
    assert not run_evals.records_cassette(run_evals.RESULTS_DIR / "ablation_replan_no_needs_live.json")  # outro modo
    monkeypatch.setenv("EVAL_CASSETTE", "off")
    assert not run_evals.records_cassette(None)


def test_ablation_verdicts_go_to_their_own_judge_file():
    """A ablação tem os mesmos casos de um split: no judge.json ela se misturaria à taxa do split e do total."""
    from evals import run_evals

    assert run_evals.judge_file_for(run_evals.RESULTS_DIR / "live_real.json").name == "judge.json"
    assert run_evals.judge_file_for(run_evals.RESULTS_DIR / "ablation_replan_no_needs_live.json").name == \
        "judge_ablation_replan_no_needs_live.json"


def test_needs_ablation_line_compares_only_complete_runs_with_the_same_cases(tmp_path):
    import json as _json

    from scripts.fill_readme import _needs_ablation

    def write(name, status, cases, grounded):
        (tmp_path / name).write_text(_json.dumps({
            "split": "real", "status": status, "git_sha": "abc",
            "metrics": {"real": {"cases": cases, "numbers_acc": 100.0, "claims_acc": 97.5, "p50_ms": 20000,
                                 "cost_usd": 1.6}},
            "judge": {"verdicts": cases, "grounded": grounded, "helpful": grounded - 1}}), encoding="utf-8")

    write("live_real.json", "complete", 40, 38)
    write("ablation_replan_no_needs_live.json", "complete", 40, 33)
    line = _needs_ablation(tmp_path)[0]
    assert "mesmos 40 casos" in line and "38/40 com" in line and "33/40 sem" in line
    # rejulgado: o arquivo de vereditos vence o resumo gravado no relatório
    verdicts = [{"source": "live_real.json", "grounded": i < 39, "helpful": True} for i in range(40)]
    (tmp_path / "judge.json").write_text(_json.dumps({"verdicts": verdicts}), encoding="utf-8")
    assert "39/40 com" in _needs_ablation(tmp_path)[0]
    write("ablation_replan_no_needs_live.json", "aborted_max_usd", 28, 25)
    assert "não comparável" in _needs_ablation(tmp_path)[0]


def _ablation_arm(path, sha, rows, prompt="h1"):
    """Um braço da ablação `needs` (split real) com as linhas que a conta de p50 e de destino do achado lê."""
    rows = [{"prompt_versions": {"supervisor.md": prompt}, **r} for r in rows]
    path.write_text(json.dumps({
        "split": "real", "status": "complete", "git_sha": sha, "rows": rows,
        "metrics": {"real": {"cases": len(rows), "p50_ms": 2000, "cost_usd": 0.4}},
        "judge": {"verdicts": len(rows), "grounded": len(rows), "helpful": len(rows)}}), encoding="utf-8")


def test_needs_ablation_warns_when_the_arms_come_from_different_commits(tmp_path):
    """Medido na rodada 10: os braços eram de 35020c4 × 318f3af e o README dizia "no mesmo commit da bateria"."""
    from scripts.fill_readme import _needs_ablation

    rows = [{"id": "real-01", "ms": 1000.0}]
    _ablation_arm(tmp_path / "live_real.json", "abc", rows)
    _ablation_arm(tmp_path / "ablation_replan_no_needs_live.json", "abc", rows)
    same = _needs_ablation(tmp_path)[0]
    assert "mesmo commit `abc`" in same and "AVISO" not in same
    _ablation_arm(tmp_path / "ablation_replan_no_needs_live.json", "def", rows)
    other = _needs_ablation(tmp_path)[0]
    assert "**AVISO: braços em commits diferentes** (`abc` × `def`, mesmos prompts)" in other
    _ablation_arm(tmp_path / "ablation_replan_no_needs_live.json", "def", rows, prompt="h2")
    assert "prompts diferentes: supervisor.md" in _needs_ablation(tmp_path)[0]


def test_needs_ablation_gives_the_p50_where_the_finding_fired_and_what_happened_to_it(tmp_path):
    """Só 10 dos 40 casos reais dispararam o achado na rodada 10: o p50 do split inteiro misturava 30 casos de mesmo
    caminho nos dois braços. O achado conta pela árvore de passos (`needs`) ou, em gravação antiga, pelo replanejamento
    "records:need->faq"; o destino (supervisor.NEED_OUTCOMES) sai contado do braço com `needs`."""
    from app import supervisor
    from scripts.fill_readme import NEED_OUTCOME_LABEL, _needs_ablation

    def finding(outcome):
        return [{"agent": "records", "needs": [{"agent": "faq", "why": "terminal offline", "outcome": outcome}]},
                {"agent": "faq"}]

    base = [{"id": "real-01", "ms": 30000.0, "steps": finding("called")},
            {"id": "real-02", "ms": 20000.0, "steps": finding("ignored")},
            {"id": "real-03", "ms": 25000.0, "replans": ["records:need->faq (terminal offline)"]},  # gravação antiga
            {"id": "real-04", "ms": 1000.0, "steps": [{"agent": "faq"}]},
            {"id": "real-05", "ms": 2000.0, "steps": [{"agent": "faq"}]}]
    slower = {"real-01", "real-02", "real-03"}
    ablation = [{**r, "ms": r["ms"] + 10000.0 if r["id"] in slower else r["ms"]} for r in base]
    _ablation_arm(tmp_path / "live_real.json", "abc", base)
    _ablation_arm(tmp_path / "ablation_replan_no_needs_live.json", "abc", ablation)
    line = _needs_ablation(tmp_path)[0]
    assert "p50 só nos 3 casos em que o achado disparou 25.0 s × 35.0 s" in line
    assert ("2 achados no braço com `needs`: o modelo chamou o agente pedido 1, ignorou mesmo com o lembrete "
            "(`need_ignored`) 1") in line
    assert set(NEED_OUTCOME_LABEL) == set(supervisor.NEED_OUTCOMES)  # destino novo sem rótulo sairia "outro"
