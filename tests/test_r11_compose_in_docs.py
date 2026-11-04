"""R11-F: todo `docker compose [-f X]* exec|run|logs|restart|up ... <serviço>` do README e dos docs aponta para um
serviço que existe nos arquivos de compose que o comando usa (os `-f`; sem eles, o docker-compose.yml).

No ensaio, o passo "Entrar" do README dizia `docker compose exec app` e o serviço é `api`: o comando falhava no passo 2
do teste de 3 minutos, e nenhum teste lia o README (o smoke do docker usa `docker run`). Ficam fora o histórico
(CHANGELOG e changelog.d citam o comando errado ao registrar a correção) e os estudos de repositórios de terceiros.
"""
import re
import textwrap
from pathlib import Path

import yaml
from test_production_ops import _ComposeLoader  # aceita `!override` / `!reset` (o overlay endurecido usa)

from app.config import ROOT

CMD = re.compile(r"\bdocker(?: |-)compose(?![\w.*-])([^`\n|;&#()<>]*)")  # docker-compose.yml é arquivo, não comando
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
INLINE = re.compile(r"`([^`]+)`")
SKIP = re.compile(r"(?:^|/)(?:changelog\.d|ensaio|estudo|pesquisa)/|CHANGELOG[^/]*\.md$")
GLOBAL_VALUED = {"-f", "--file", "-p", "--project-name", "--profile", "--env-file", "--project-directory", "--ansi",
                 "--progress", "--parallel"}
# opções que levam valor (o token seguinte é o valor, não o serviço), por subcomando; as outras são chaves
VALUED = {
    "exec": {"-e", "--env", "-u", "--user", "-w", "--workdir", "--index"},
    "run": {"-e", "--env", "-u", "--user", "-w", "--workdir", "-v", "--volume", "-p", "--publish", "--name",
            "--entrypoint", "-l", "--label", "--cap-add", "--cap-drop", "--pull"},
    "logs": {"-n", "--tail", "--since", "--until", "--index"},
    "restart": {"-t", "--timeout"},
    "up": {"-t", "--timeout", "--scale", "--wait-timeout", "--exit-code-from", "--attach", "--no-attach", "--pull"},
}
ONE_SERVICE = {"exec", "run"}  # depois do serviço vem o comando que roda dentro do container
PLACEHOLDER = re.compile(r"[<>{}$]|\.\.\.")


def parse(tokens: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(arquivos do -f, subcomando, serviços) de `docker compose <tokens>`; subcomando None = fora dos que citam
    serviço (ps, config, down...)."""
    files, i = [], 0
    while i < len(tokens) and tokens[i].startswith("-"):
        opt, _, inline = tokens[i].partition("=")
        if opt in ("-f", "--file"):
            files.append(inline or (tokens[i + 1] if i + 1 < len(tokens) else ""))
        i += 2 if opt in GLOBAL_VALUED and not inline else 1
    if i >= len(tokens) or tokens[i] not in VALUED:
        return files, None, []
    sub, i, services = tokens[i], i + 1, []
    while i < len(tokens):
        opt, _, inline = tokens[i].partition("=")
        if opt.startswith("-"):
            i += 2 if opt in VALUED[sub] and not inline else 1
            continue
        services.append(tokens[i])
        i += 1
        if sub in ONE_SERVICE:
            break
    return files, sub, [s for s in services if not PLACEHOLDER.search(s)]


def commands(text: str) -> list[tuple[int, str]]:
    """(linha, comando) de cada `docker compose` em código: blocos ``` (com continuação `\\`) e código em linha."""
    found: list[tuple[int, str]] = []

    def scan(snippet: str, line: int) -> None:
        found.extend((line, m.group(0).strip()) for m in CMD.finditer(snippet))

    for block in FENCE.finditer(text):
        start = text.count("\n", 0, block.start(1)) + 1
        lines = block.group(1).split("\n")
        i = 0
        while i < len(lines):
            j, joined = i, lines[i]
            while joined.rstrip().endswith("\\") and j + 1 < len(lines):
                j += 1
                joined = joined.rstrip()[:-1] + " " + lines[j]
            scan(joined, start + i)
            i = j + 1
    rest = FENCE.sub(lambda b: "\n" * b.group(0).count("\n"), text)  # sem os blocos, as linhas não mudam
    for span in INLINE.finditer(rest):
        if "\n\n" not in span.group(1):  # código em linha quebra linha dentro do parágrafo, não entre parágrafos
            scan(span.group(1).replace("\n", " "), rest.count("\n", 0, span.start()) + 1)
    return sorted(found)


def _services(files: list[str], root: Path) -> tuple[set[str], list[str]]:
    names, missing = set(), []
    for name in files:
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        compose = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506 — SafeLoader
        names |= set((compose or {}).get("services") or {})
    return names, missing


def compose_problems(paths: list[Path], root: Path = ROOT) -> list[str]:
    problems = []
    for path in paths:
        where = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        for line, cmd in commands(path.read_text(encoding="utf-8")):
            files, sub, services = parse(cmd.split()[2:] if cmd.startswith("docker compose") else cmd.split()[1:])
            if sub is None:
                continue
            default = ["docker-compose.yml", *(["docker-compose.override.yml"]
                                               if (root / "docker-compose.override.yml").exists() else [])]
            known, missing = _services(files or default, root)
            problems += [f"{where}:{line}: `{cmd}` usa {name}, que não existe" for name in missing]
            problems += [f"{where}:{line}: `{cmd}`: serviço `{svc}` não existe em {', '.join(files or default)} "
                         f"(serviços: {', '.join(sorted(known))})" for svc in services if svc not in known]
    return problems


def docs(root: Path = ROOT) -> list[Path]:
    """README e docs que alguém segue ao pé da letra (fora o histórico e os estudos de terceiros)."""
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    return [p for p in paths if p.is_file() and not SKIP.search(p.relative_to(root).as_posix())]


def test_every_compose_command_in_the_readme_and_docs_names_an_existing_service():
    problems = compose_problems(docs())
    assert not problems, "\n".join(problems)


def test_the_check_reads_flags_files_services_and_continuations(tmp_path):
    for name in ("docker-compose.yml", "docker-compose.scale.yml"):
        (tmp_path / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    md = tmp_path / "README.md"
    md.write_text(textwrap.dedent("""\
        Passo:

        ```bash
        docker compose exec app python -m app.auth seed-passwords   # serviço errado
        TOKEN=$(docker compose exec -T api python -m app.auth u1)
        docker compose -f docker-compose.yml -f docker-compose.scale.yml logs --tail 50 -f lb api
        docker compose run --rm -e X=1 api pytest
        docker compose exec lb sh
        docker compose -f docker-compose.nao-existe.yml up
        docker compose restart -t 5 grafana \\
          prometheus
        ```

        Em linha: `docker compose --profile postgres up -d --build postgres api-pg
        lb-pg`, `docker compose logs <serviço>`, `docker-compose.yml` e `docker compose ps`.
        """), encoding="utf-8")
    got = compose_problems([md], tmp_path)
    assert len(got) == 3, got
    assert got[0].startswith("README.md:4: `docker compose exec app python -m app.auth seed-passwords`: serviço `app`")
    assert got[1].startswith("README.md:8: `docker compose exec lb sh`: serviço `lb` não existe em docker-compose.yml")
    assert got[2] == ("README.md:9: `docker compose -f docker-compose.nao-existe.yml up` usa "
                      "docker-compose.nao-existe.yml, que não existe")
    assert parse("-f a.yml --file=b.yml logs -n 5 -t api lb".split()) == (["a.yml", "b.yml"], "logs", ["api", "lb"])
    assert parse("exec -dT -u root api env".split()) == ([], "exec", ["api"])
    assert parse("--profile postgres config -q".split()) == ([], None, [])
