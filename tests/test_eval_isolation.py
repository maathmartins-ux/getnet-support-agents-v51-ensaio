"""Isolamento entre casos do eval e Store aquecido antes da leva paralela.

1. Todos os casos usam o mesmo user_id num banco só e a memória de longo prazo é por usuário: sem isolamento, um
   caso cita o valor de outro. Cada caso precisa começar sem a memória dos anteriores, sem trocar o user_id
   (o CRM é por usuário: trocar o id quebraria as tools).
2. Criado dentro dos workers, o Store da 1ª leva paralela dá "database is locked" nos primeiros casos.
"""
import threading

import pytest

from evals import run_evals
from evals.run_evals import run


class MemorySpy:
    """Cliente em processo que anota a memória de longo prazo encontrada no 1º turno de cada caso."""

    def __init__(self):
        self.inner = run_evals.Client(None)
        self.seen: list[tuple[str, str]] = []
        self.lock = threading.Lock()

    def send(self, message, user_id, conversation_id):
        from app.store import get_store

        if conversation_id is None:  # 1º turno do caso: nada de casos anteriores pode estar aqui
            with self.lock:
                self.seen.append((message, get_store().user_summary(user_id)))
        return self.inner.send(message, user_id, conversation_id)


@pytest.mark.parametrize("workers", [1, 4])
def test_each_case_starts_without_memory_of_other_cases(tmp_path, workers):
    spy = MemorySpy()
    report = run(out=tmp_path / "latest.json", workers=workers, repeat=2, client=spy)
    leaked = [(m, s) for m, s in spy.seen if s]
    assert spy.seen and not leaked, leaked
    # o CRM continua sendo do usuário do caso: a consulta ao pedido 1002 do u1 segue funcionando
    lookup = next(r for r in report["rows"] if r["id"] == "official-03")
    assert lookup["checks"]["tools"] is True
    assert report["isolation"] == "db_per_case"


def test_memory_inside_a_case_still_works(tmp_path):
    # o caso de memória (before + seguimento) depende do histórico da PRÓPRIA conversa: isolar não pode quebrar
    report = run(out=tmp_path / "latest.json", split="memory")
    assert report["metrics"]["memory"]["intent_acc"] == 100.0, report["failures"]


def test_store_is_created_before_the_parallel_wave(monkeypatch, tmp_path):
    from app import store

    first_init: dict[str, bool] = {}
    original = store.Store.__init__

    def spy(self, path):
        first_init.setdefault(str(path), threading.current_thread() is threading.main_thread())
        original(self, path)

    monkeypatch.setattr(store.Store, "__init__", spy)
    run(out=tmp_path / "latest.json", workers=4)
    created_in_worker = [p for p, main in first_init.items() if not main]
    assert first_init and not created_in_worker, created_in_worker


def test_earlier_conversations_of_the_same_user_run_first_each_from_scratch():
    """`earlier_conversations`: o caso de memória ENTRE conversas. Cada conversa anterior abre do zero, o turno avaliado
    abre outra, e o que ele sabe delas vem só do perfil do usuário (na evidência da linha, sem as datas)."""
    from evals import trace_stats

    sent: list[tuple[str, str | None, str]] = []

    class Spy:
        inner = run_evals.Client(None)

        def send(self, message, user_id, conversation_id):
            got = self.inner.send(message, user_id, conversation_id)
            sent.append((message, conversation_id, got["conversation_id"]))
            return got

    case = {"id": "mem-entre", "split": "memory", "user_id": "u1", "message": "Tem novidade?",
            "earlier_conversations": [["Onde está meu pedido 1002?", "E o prazo de entrega?"],
                                      ["Qual o horário de atendimento?"]],
            "expect": {"intent": "faq"}}
    row = run_evals.run_case(Spy(), case)
    (m1, c1, got1), (_, c1b, got1b), (_, c2, got2), (m3, c3, got3) = sent
    assert (m1, c1, c1b, c2, c3) == ("Onde está meu pedido 1002?", None, got1, None, None) and got1b == got1
    assert len({got1, got2, got3}) == 3 and m3 == "Tem novidade?"  # três conversas: a avaliada é nova
    memo = next(e for e in row["evidence"] if e.startswith("[memória de conversas anteriores]"))
    assert "registro citado pelo cliente: 1002" in memo
    assert run_evals.case_turns(case) == 4 and trace_stats.turns_by_case([case]) == {"mem-entre": 4}


def test_malformed_earlier_conversations_fail_at_load(tmp_path):
    bad = tmp_path / "cases.jsonl"
    bad.write_text('{"id": "x", "split": "memory", "message": "oi", "expect": {}, '
                   '"earlier_conversations": ["Onde está meu pedido?"]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="earlier_conversations"):
        run_evals.load_cases((bad,))
