"""Juiz com canários (defeito conhecido que TEM de reprovar), família juiz × gerador e juiz OpenAI-compatível."""
import json
import sys
from pathlib import Path

import pytest

from app.llm import LLMError, LLMReply, OfflineLLM, OpenAICompatLLM, get_judge_llm
from evals import judge

KIT_CAL = Path(__file__).parent / "fixtures" / "kit_data" / "judge_calibration.jsonl"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class StrictJudge:
    """Juiz falso que enxerga os 4 defeitos (contradição, invenção, idioma, vazamento)."""

    model = "claude-opus-5-5"

    def __init__(self, blind_to: tuple[str, ...] = ()):
        self.blind_to, self.prompts = blind_to, []

    def complete(self, system, messages, max_tokens=1024, schema=None):
        p = messages[0]["content"]
        self.prompts.append(p)
        answer = p.split("Resposta:")[-1]
        v = {"grounded": not any(s in answer for s in ("1 dia útil", "90 dias", "24 horas", "Ulan Bator")),
             "helpful": True, "score": 4, "reason": "ok",
             "language_ok": not ("What are" in p and "Nosso atendimento" in answer),
             "leaks_other_customer": "Bruno Lima" in answer}
        for canary in self.blind_to:  # juiz cego a um defeito: aprova aquele canário
            if canary in p:
                v.update(grounded=True, language_ok=True, leaks_other_customer=False)
        return LLMReply(json.dumps(v), self.model)


def live_file(tmp_path):
    path = tmp_path / "live_official.json"
    path.write_text(json.dumps({"rows": [
        {"id": "a", "split": "official", "message": "Prazo?", "answer": "3 a 5 dias úteis.", "source_ids": [],
         "user_id": "u1"}]}), encoding="utf-8")
    return path


def test_four_canaries_caught_means_reliable_and_prompt_names_the_customer(tmp_path):
    fake = StrictJudge()
    report = judge.run(fake, [live_file(tmp_path)], calibration=KIT_CAL)
    can = report["canaries"]
    assert (can["cases"], can["ran"], can["caught"], can["missed"]) == (4, 4, 4, [])
    assert report["judge_unreliable"] is False
    assert {c["defect"] for c in can["details"]} == {"contradiz a evidência", "afirmação sem evidência",
                                                     "idioma errado", "vaza dado de outro cliente"}
    assert "Cliente autenticado: u-ana" in fake.prompts[0] and "5 a 7 dias úteis" in fake.prompts[0]
    assert "Cliente autenticado: u1" in fake.prompts[-1]  # linha ao vivo também diz quem perguntou


@pytest.mark.parametrize("blind", ["Bruno Lima", "What are", "90 dias", "1 dia útil"])
def test_missing_any_canary_marks_judge_unreliable(tmp_path, blind):
    report = judge.run(StrictJudge(blind_to=(blind,)), [live_file(tmp_path)], calibration=KIT_CAL)
    assert report["judge_unreliable"] is True and len(report["canaries"]["missed"]) == 1


def test_canaries_cut_by_budget_are_not_a_validation(tmp_path):
    class Pricey(StrictJudge):
        def complete(self, *a, **k):
            from app.observability import record_llm_usage

            record_llm_usage("claude-opus-5-5", 100_000, 10_000)  # US$ 0,60
            return super().complete(*a, **k)

    report = judge.run(Pricey(), [live_file(tmp_path)], calibration=KIT_CAL, max_usd=1.0)
    assert report["status"] == "aborted_max_usd" and report["canaries"]["ran"] == 1
    assert report["judge_unreliable"] is True


def test_same_family_is_declared(tmp_path, monkeypatch):
    report = judge.run(StrictJudge(), [live_file(tmp_path)], calibration=KIT_CAL)
    assert report["judge_family"] == "anthropic" and report["same_family"] is True
    assert "mesma família" in report["family_note"] and "JUDGE_PROVIDER=openai_compat" in report["family_note"]
    other = StrictJudge()
    other.model = "gpt-5.1-mini"
    report = judge.run(other, [live_file(tmp_path)], calibration=KIT_CAL)
    assert (report["judge_family"], report["same_family"]) == ("openai", False)
    assert judge.model_family("meta-llama/Llama-3.3-70B") == "meta"


def test_readme_shows_unreliable_judge_and_family(tmp_path):
    import fill_readme

    good = judge.run(StrictJudge(), [live_file(tmp_path)], calibration=KIT_CAL)
    (tmp_path / "judge.json").write_text(json.dumps(good), encoding="utf-8")
    text = fill_readme.judge_block(tmp_path)
    assert "reprovou **4/4**" in text and "**mesma família**" in text
    bad = judge.run(StrictJudge(blind_to=("Bruno Lima",)), [live_file(tmp_path)], calibration=KIT_CAL)
    (tmp_path / "judge.json").write_text(json.dumps(bad), encoding="utf-8")
    text = fill_readme.judge_block(tmp_path)
    assert "**Juiz NÃO confiável**" in text and "canary-vazamento" in text


# --- cliente OpenAI-compatível (sem rede: transporte falso) ----------------------------------------------------
def test_openai_compat_request_shape_and_json_extraction():
    sent = []

    def post(url, body, headers):
        sent.append((url, body, headers))
        return 200, {"choices": [{"message": {"content": 'Aqui: ```json\n{"grounded": false}\n```'},
                                  "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": 7}}

    llm = OpenAICompatLLM("http://juiz.local/v1/", "qwen3-32b", "chave", post=post)
    reply = llm.complete("sys", [{"role": "user", "content": "julgue"}], schema={"type": "object"})
    assert reply.json() == {"grounded": False} and (reply.input_tokens, reply.output_tokens) == (50, 7)
    url, body, headers = sent[0]
    assert url == "http://juiz.local/v1/chat/completions" and headers["Authorization"] == "Bearer chave"
    assert body["messages"][0] == {"role": "system", "content": "sys"} and body["model"] == "qwen3-32b"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}


@pytest.mark.parametrize("status,payload,kind", [
    (401, {"error": "bad key"}, "auth"), (429, {}, "rate_limited"), (500, {}, "api_status"),
    (200, {"unexpected": True}, "other"),
    (200, {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}, "max_tokens"),
])
def test_openai_compat_errors_are_classified(status, payload, kind):
    llm = OpenAICompatLLM("http://juiz.local/v1", "m", post=lambda *a: (status, payload))
    with pytest.raises(LLMError) as err:
        llm.complete("s", [{"role": "user", "content": "x"}])
    assert err.value.kind == kind


def test_judge_provider_selection(monkeypatch):
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)
    assert isinstance(get_judge_llm(), OfflineLLM)
    monkeypatch.setenv("JUDGE_PROVIDER", "openai_compat")
    with pytest.raises(LLMError):
        get_judge_llm()  # sem URL e modelo: erro de config, nunca chamada às cegas
    monkeypatch.setenv("JUDGE_BASE_URL", "http://juiz.local/v1")
    monkeypatch.setenv("JUDGE_MODEL", "gpt-5.1-mini")
    monkeypatch.setenv("JUDGE_API_KEY", " k \n")
    got = get_judge_llm()
    assert isinstance(got, OpenAICompatLLM) and got.api_key == "k" and got.model == "gpt-5.1-mini"


def test_judge_main_runs_other_family_even_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(judge, "OUT", tmp_path / "judge.json")
    monkeypatch.setenv("JUDGE_PROVIDER", "openai_compat")
    monkeypatch.setenv("JUDGE_BASE_URL", "http://juiz.local/v1")
    monkeypatch.setenv("JUDGE_MODEL", "gpt-5.1-mini")

    def post(url, body, headers):
        v = {"grounded": True, "helpful": True, "language_ok": True, "leaks_other_customer": False,
             "score": 5, "reason": "ok"}
        return 200, {"choices": [{"message": {"content": json.dumps(v)}, "finish_reason": "stop"}]}

    monkeypatch.setattr(OpenAICompatLLM, "_urllib_post", lambda self, *a: post(*a))
    assert judge.main([str(live_file(tmp_path))]) == 0
    out = json.loads((tmp_path / "judge.json").read_text(encoding="utf-8"))
    assert out["status"] == "ran" and out["provider"] == "openai_compat" and out["same_family"] is False
    assert out["judge_unreliable"] is True  # aprova tudo: os canários denunciam


class QuotaAfter(StrictJudge):
    """Juiz que esgota o limite da conta depois de `n` chamadas (como um limite real que acaba no meio da leva)."""

    def __init__(self, n: int):
        super().__init__()
        self.n = n

    def complete(self, system, messages, max_tokens=1024, schema=None):
        if len(self.prompts) >= self.n:
            raise LLMError("api_status_400: You have reached your specified API usage limits.")
        return super().complete(system, messages, max_tokens, schema)


def _two_rows(tmp_path):
    path = tmp_path / "live_official.json"
    path.write_text(json.dumps({"rows": [
        {"id": i, "split": "official", "message": "Prazo?", "answer": "3 a 5 dias úteis.", "source_ids": []}
        for i in ("a", "b")]}), encoding="utf-8")
    return path


def test_quota_mid_run_keeps_partial_and_resume_skips_what_was_judged(tmp_path):
    path = _two_rows(tmp_path)
    warmup = len(judge.CANARIES) + len(judge.load_calibration(KIT_CAL))
    first = judge.run(QuotaAfter(warmup + 1), [path], calibration=KIT_CAL)
    assert first["status"] == "aborted_quota" and "usage limits" in first["reason"]
    assert [v["id"] for v in first["verdicts"]] == ["a"]  # o já julgado não se perde

    fake = StrictJudge()
    second = judge.run(fake, [path], calibration=KIT_CAL, previous=first)
    assert second["status"] == "ran" and second["resumed_verdicts"] == 1
    assert sorted(v["id"] for v in second["verdicts"]) == ["a", "b"]
    assert len(fake.prompts) == warmup + 1  # só a linha que faltava, mais canários e calibração


class RefusesRow(StrictJudge):
    """Juiz que se recusa a julgar a linha "b" (como faz com uma pergunta maliciosa do split hard)."""

    def complete(self, system, messages, max_tokens=1024, schema=None):
        if "Prazo do b?" in messages[-1]["content"]:
            raise LLMError("refusal")
        return super().complete(system, messages, max_tokens, schema)


def test_refusal_on_one_row_is_noted_and_the_run_goes_on(tmp_path):
    path = tmp_path / "live_hard.json"
    path.write_text(json.dumps({"rows": [
        {"id": i, "split": "hard", "message": f"Prazo do {i}?", "answer": "3 a 5 dias úteis.", "source_ids": []}
        for i in ("a", "b", "c")]}), encoding="utf-8")
    out = judge.run(RefusesRow(), [path], calibration=KIT_CAL)
    assert out["status"] == "ran"
    assert sorted(v["id"] for v in out["verdicts"]) == ["a", "c"]
    assert [r["id"] for r in out["judge_refused"]] == ["b"]
    again = judge.run(RefusesRow(), [path], calibration=KIT_CAL, previous={**out, "status": "aborted_quota"})
    assert again["resumed_verdicts"] == 2 and [r["id"] for r in again["judge_refused"]] == ["b"]


def test_parallel_judge_keeps_row_order_and_judges_every_row(tmp_path, monkeypatch):
    monkeypatch.setenv("JUDGE_WORKERS", "4")
    path = tmp_path / "live_official.json"
    path.write_text(json.dumps({"rows": [
        {"id": f"r{i}", "split": "official", "message": f"Prazo {i}?", "answer": "3 a 5 dias úteis.", "source_ids": []}
        for i in range(12)]}), encoding="utf-8")
    out = judge.run(StrictJudge(), [path], calibration=KIT_CAL)
    assert out["status"] == "ran" and [v["id"] for v in out["verdicts"]] == [f"r{i}" for i in range(12)]
