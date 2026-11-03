"""Pré-voo: transforma o kit no ponto de partida do desafio. Roda UMA vez, na sessão principal, logo após o
commit `chore: scaffold` e antes da SPEC.

Uso:
  python scripts/preflight.py            # cria o domínio do desafio e limpa os exemplos do produto
  python scripts/preflight.py --dry-run  # só mostra o que faria

O que faz (cada item fecha uma falha já medida):
1. Cria `src/app/domain/challenge/` como CÓPIA do domínio de exemplo, em 3 arquivos com dono único:
   - `flow.py`  (frente R): taxonomia, planos, FALLBACK, regras do router offline;
   - `tools.py` (frente T): ferramentas do CRM e caminho offline do agente records;
   - `__init__.py` (sessão principal): MIN_SCORE calibrado e a junção dos dois.
   Com o domínio escrito direto em router.py/supervisor.py/tools.py/agents.py, 59 testes do kit quebravam; por
   isso o motor é congelado (OWNERSHIP.json) e lê o domínio ativo.
2. Copia os prompts do kit para `src/app/domain/challenge_prompts/` (o desafio edita a cópia).
3. Tira a loja de exemplo do PRODUTO: data/sample.jsonl, data/records.json, data/intent_examples.jsonl, o
   glossário da loja e os casos/retrieval/calibração de exemplo em evals/ (os originais ficam em
   tests/fixtures/kit_data, que é o que os testes do kit usam). Sem esta limpeza, 3 textos da loja ficavam no
   índice de busca e 9 perguntas da loja entravam no Recall@3.
4. Roda a suíte do kit: tem de seguir verde com o domínio do desafio no lugar.

Antes de tudo: confere o REPOSITÓRIO da tentativa. O ramo padrão do remoto tem de ser `main` (a CI e quem abre
o repositório no GitHub leem o ramo padrão; corrigir isso depois custa minutos antes do relógio) e o kit tem de ter
vindo do ramo `kit-fonte` que a maestra criou antes do relógio: com `kit-fonte` presente, todo arquivo dele fora de
docs/kit/ está no HEAD (consumido pelo scaffold); sem `kit-fonte` (já apagado), o HEAD tem o commit
`chore: scaffold`. Falha com a correção escrita. `--skip-repo-check` pula só esta etapa (execução local, sem remoto).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "src" / "app" / "domain"
EXAMPLE = DOMAIN / "example.py"
TARGET = DOMAIN / "challenge"
PROMPTS = ROOT / "src" / "app" / "prompts"
TARGET_PROMPTS = DOMAIN / "challenge_prompts"

# Seções do example.py (marcadas por "# --- <nome>") → arquivo do pacote do desafio.
SECTION_FILE = {
    "taxonomia": "flow.py",
    "regras do router": "flow.py",
    "portão": "__init__.py",
    "prompts": "__init__.py",
    "ferramentas": "tools.py",
    "caminho offline": "tools.py",
    "achados": "tools.py",  # needs_for / NEEDS_BY_STATUS: achado do records que pede outro especialista
}
HEADERS = {
    "flow.py": '"""Domínio do desafio — FLUXO: taxonomia, planos, FALLBACK, regras do router.\n\n'
               'Contrato lido pelo motor: PLANS, FALLBACK, ALLOWED, DEPENDS, NO_ESCALATION, DEFAULT_INTENT,\n'
               'MULTI_PARTS, states_subject(), clause_intent(), combine().\nTeste: tests/test_domain_router.py.\n"""\n',
    "tools.py": '"""Domínio do desafio — FERRAMENTAS: registro TOOLS e caminho offline do records.\n\n'
                'Contrato lido pelo motor: TOOLS, ELIGIBLE_STATUS, records(), records_offline(). Teste em\n'
                'tests/test_tools.py. Nenhuma tool da loja de exemplo pode sobrar aqui (check.py reprova).\n"""\n',
    "__init__.py": '"""Domínio do desafio: junta flow + tools e guarda o limiar calibrado.\n\n'
                   'MIN_SCORE sai de `python -m evals.run_evals --calibrate-gate` NO CORPUS DO DESAFIO; troque aqui,\n'
                   'nunca no motor nem no domínio de exemplo (os testes do motor rodam no exemplo).\n"""\n',
}
IMPORTS = {
    "flow.py": "from __future__ import annotations\n\nimport re\n",
    "tools.py": "from __future__ import annotations\n\nimport json\nimport re\nfrom functools import lru_cache\n\n"
                "from app.config import data_dir\n",
    "__init__.py": "from __future__ import annotations\n\nfrom pathlib import Path\n",
}
SOURCES = ('{\n  "_doc": "Páginas do site oficial da empresa para `python -m app.ingest` (frente K). '
           'allowed_hosts = só o domínio do país do enunciado.",\n  "allowed_hosts": [],\n  "groups": {\n'
           '    "produtos": {"prefix": "prod", "pages": {}},\n    "suporte": {"prefix": "sup", "pages": {}}\n  }\n}\n')
PROMPTS_LINE = 'PROMPTS_DIR = Path(__file__).resolve().parent.parent / "challenge_prompts"'
# Exemplos que saem do produto (o original continua em tests/fixtures/kit_data).
EMPTIED = ["data/sample.jsonl", "data/records.json", "data/intent_examples.jsonl",
           "evals/cases.jsonl", "evals/retrieval.jsonl", "evals/judge_calibration.jsonl"]
# Ferramentas de construção do kit, sem papel no produto: saem do repositório da entrega.
KIT_ONLY = ["scripts/ensaio_overlay.sh", "scripts/medir_forks.py"]
GLOSSARY = ('{\n  "_doc": "Glossário pt -> en do DESAFIO (agents.expand_query): chave = termo do corpus em português; '
            'valor = como o cliente pergunta em inglês. Preenchido pela frente K."\n}\n')


def split_example(text: str) -> dict[str, str]:
    """Corta o example.py nas seções '# --- nome' e devolve o corpo de cada arquivo do pacote."""
    parts = re.split(r"^(# --- [^\n]*)$", text, flags=re.MULTILINE)
    files: dict[str, list[str]] = {name: [] for name in HEADERS}
    for marker, body in zip(parts[1::2], parts[2::2], strict=True):
        name = marker[len("# --- "):].split(" (")[0].split(" -")[0].strip()
        target = next((f for key, f in SECTION_FILE.items() if name.startswith(key)), None)
        if target is None:
            sys.exit(f"ERRO: seção sem destino no pré-voo: {marker!r}")
        files[target].append(marker + body)
    return {name: "".join(chunks) for name, chunks in files.items()}


def build(dry: bool) -> list[str]:
    done = []
    if TARGET.exists() or (DOMAIN / "challenge.py").exists():
        sys.exit("ERRO: o domínio do desafio já existe; o pré-voo roda uma vez só.")
    bodies = split_example(EXAMPLE.read_text(encoding="utf-8"))
    contents = {
        "flow.py": HEADERS["flow.py"] + IMPORTS["flow.py"] + "\n" + bodies["flow.py"],
        "tools.py": HEADERS["tools.py"] + IMPORTS["tools.py"] + "\n" + bodies["tools.py"],
        "__init__.py": HEADERS["__init__.py"] + IMPORTS["__init__.py"] + "\nfrom .flow import *  # noqa: F403\n"
                       "from .tools import *  # noqa: F403\n\n" + bodies["__init__.py"].replace(
                           "PROMPTS_DIR = None", PROMPTS_LINE),
    }
    for name, body in contents.items():
        done.append(f"criar src/app/domain/challenge/{name}")
        if not dry:
            TARGET.mkdir(exist_ok=True)
            (TARGET / name).write_text(body, encoding="utf-8")
    done.append("copiar src/app/prompts/*.md → src/app/domain/challenge_prompts/")
    if not dry:
        shutil.copytree(PROMPTS, TARGET_PROMPTS)
    for rel in EMPTIED:
        done.append(f"esvaziar {rel} (exemplo da loja; original em tests/fixtures/kit_data)")
        if not dry:
            path = ROOT / rel
            if rel.endswith(".json"):
                path.unlink(missing_ok=True)
            else:
                path.write_text("", encoding="utf-8")
    for rel in KIT_ONLY:
        if (ROOT / rel).exists():
            done.append(f"remover {rel} (ferramenta de construção do kit)")
            if not dry:
                (ROOT / rel).unlink()
    done.append("trocar data/glossary.json pelo esqueleto do desafio")
    done.append("criar data/sources.json (frente K: domínios e páginas do site da empresa)")
    if not dry:
        (ROOT / "data" / "glossary.json").write_text(GLOSSARY, encoding="utf-8")
        (ROOT / "data" / "sources.json").write_text(SOURCES, encoding="utf-8")
    return done


KIT_BRANCH = "kit-fonte"
DEFAULT_BRANCH = "main"
SCAFFOLD = re.compile(r"^chore: scaffold\b", re.MULTILINE)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def default_branch(repo: Path) -> str | None:
    """Ramo padrão do remoto `origin`: origin/HEAD local; senão pergunta ao remoto (ls-remote --symref)."""
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip().removeprefix("origin/")
    remote = git(repo, "ls-remote", "--symref", "origin", "HEAD")
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", remote.stdout, re.MULTILINE)
    return m.group(1) if m else None


def kit_ref(repo: Path) -> str | None:
    """`origin/kit-fonte` (preferido) ou o ramo local `kit-fonte`; None se nenhum existe (nem no remoto)."""
    for ref in (f"refs/remotes/origin/{KIT_BRANCH}", f"refs/heads/{KIT_BRANCH}"):
        if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return ref
    remote = git(repo, "ls-remote", "--heads", "origin", KIT_BRANCH)
    if remote.returncode == 0 and remote.stdout.strip():
        fetched = git(repo, "fetch", "--quiet", "origin", f"{KIT_BRANCH}:refs/remotes/origin/{KIT_BRANCH}")
        if fetched.returncode == 0:
            return f"refs/remotes/origin/{KIT_BRANCH}"
    return None


def tree_files(repo: Path, ref: str) -> set[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", ref)
    return set(out.stdout.splitlines()) if out.returncode == 0 else set()


def check_repo(repo: Path = ROOT) -> list[str]:
    """Problemas do repositório da tentativa (vazio = ok), cada um com a correção. Não muda nada no repositório."""
    if git(repo, "rev-parse", "--git-dir").returncode != 0:
        return [f"{repo} não é um repositório git: abra a sessão no repositório da tentativa."]
    problems = []
    if git(repo, "remote", "get-url", "origin").returncode != 0:
        problems.append("sem remoto `origin`: a sessão tem de estar no repositório da tentativa no GitHub.")
    else:
        branch = default_branch(repo)
        if branch is None:
            problems.append("não deu para ler o ramo padrão de `origin` (git ls-remote --symref origin HEAD): "
                            "confira no GitHub (Settings → Branches) que o padrão é `main`.")
        elif branch != DEFAULT_BRANCH:
            problems.append(f"o ramo padrão do repositório é `{branch}`, não `{DEFAULT_BRANCH}`: troque em GitHub → "
                            f"Settings → Branches → Default branch ANTES do relógio (a CI usa o padrão)")
    ref = kit_ref(repo)
    if ref is None:
        if not SCAFFOLD.search(git(repo, "log", "--format=%s", "HEAD").stdout):
            problems.append(f"o ramo `{KIT_BRANCH}` não existe e o HEAD não tem o commit `chore: scaffold`: a maestra "
                            f"cria `{KIT_BRANCH}` com o kit antes do relógio (sem add_repo na sessão do relógio).")
    else:
        kit = {f for f in tree_files(repo, ref) if not f.startswith("docs/kit/")}
        missing = sorted(kit - tree_files(repo, "HEAD"))
        if not kit:
            problems.append(f"o ramo `{KIT_BRANCH}` está vazio: a maestra põe o kit nele antes do relógio.")
        elif missing:
            problems.append(f"o kit de `{KIT_BRANCH}` não foi consumido: {len(missing)} arquivo(s) dele fora do HEAD "
                            f"(ex.: {', '.join(missing[:3])}). No T+0: `git checkout {ref.split('refs/remotes/')[-1]}"
                            " -- .`, tirar docs/kit do índice (V5_PROMPT_M passo 1) e o commit `chore: scaffold`.")
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != DEFAULT_BRANCH and not problems:
        print(f"aviso: o ramo atual é `{current}`, não `{DEFAULT_BRANCH}` (o push do relógio vai para `main`).")
    return problems


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


MIN_FREE_GB = 5.0


def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-repo-check", action="store_true",
                    help="pula a conferência do repositório (execução local, sem remoto)")
    args = ap.parse_args()
    if not args.skip_repo_check:
        problems = check_repo(ROOT)
        for p in problems:
            print(f"REPOSITÓRIO: {p}")
        if problems:
            print("\nPRÉ-VOO FALHOU: o repositório da tentativa não está pronto (PLAYBOOK §0, T1). Nada foi alterado.")
            return 1
        print(f"repositório: ramo padrão `{DEFAULT_BRANCH}`, kit de `{KIT_BRANCH}` consumido")
    free = disk_free_gb(ROOT)
    if free < MIN_FREE_GB:  # 13 mil /tmp/eval-* já lotaram o disco e o sqlite falhou no meio da bateria
        print(f"DISCO: {free:.1f} GB livres (mínimo {MIN_FREE_GB:.0f}). Libere antes: rm -rf /tmp/eval-* e caches.")
        return 1
    for line in build(args.dry_run):
        print(("[simulação] " if args.dry_run else "") + line)
    if args.dry_run:
        return 0
    run([sys.executable, "-m", "ruff", "check", "--fix", "-q", str(TARGET)])  # imports que o corte não usa
    lint = run([sys.executable, "-m", "ruff", "check", "."])
    tests = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    probe = run([sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); from app import domain; "
                                       "print(domain.name(), sorted(domain.active().PLANS))"])
    print(f"\nruff: {'OK' if lint.returncode == 0 else 'FALHOU'}\n{lint.stdout[-1500:]}")
    print(f"suíte do kit com o domínio do desafio no lugar: {tests.stdout.strip().splitlines()[-1:]}")
    print(f"domínio ativo fora dos testes: {probe.stdout.strip() or probe.stderr.strip()[-300:]}")
    ok = lint.returncode == 0 and tests.returncode == 0 and probe.stdout.startswith("challenge")
    print("\nPRÉ-VOO " + ("OK: commite com `git add -A && git commit -m 'preflight: domínio do desafio'`."
                          if ok else "FALHOU: não siga para a SPEC antes de corrigir."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
