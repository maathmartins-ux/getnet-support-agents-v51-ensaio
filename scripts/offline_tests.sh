#!/usr/bin/env bash
# Testes com a rede CORTADA (namespace de rede vazio, só loopback): prova que a suíte não depende de download,
# chave ou serviço externo. Referência pública: uma solução 9,5 não subia a suíte sem baixar o tokenizer.
#
#   scripts/offline_tests.sh [args do pytest]
#
# 1º `unshare -rn` (sem root, user namespace). Runner Ubuntu 24.04 do GitHub restringe user namespace sem
# privilégio (AppArmor): cai para `sudo unshare -n` e volta ao usuário original com setpriv. Sem nenhum dos dois,
# FALHA (rede não cortada não é prova); OFFLINE_ALLOW_NETWORK=1 roda mesmo assim e avisa. OFFLINE_FORCE_SUDO=1
# exercita o caminho do sudo numa máquina onde o unshare sem root funciona.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
# hermético também no git: assinatura de commit ou credencial do usuário que dependem de rede ficam de fora
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
# Dois passos dentro do namespace. SUBIR a loopback exige ser root do namespace (CAP_NET_ADMIN); no caminho do
# sudo o pytest roda como o usuário comum, então a loopback sobe ANTES de largar o root (CI de 01/11/2026:
# PermissionError ao subir a loopback depois do setpriv). A sonda de rede roda já como o usuário que roda os testes.
lo_up='
import fcntl, socket, struct
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
flags = struct.unpack("16sh", fcntl.ioctl(s, 0x8913, struct.pack("16sh", b"lo", 0)))[1]
fcntl.ioctl(s, 0x8914, struct.pack("16sh", b"lo", flags | 1))
'
probe='
import socket, sys
for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
    try:
        socket.create_connection(host, timeout=3).close()
        sys.exit(f"rede NÃO cortada: {host} respondeu")
    except OSError:
        pass
print("rede cortada: só loopback")
'
# comando como TEXTO (função exportada não atravessa `sudo env`; foi o erro da 1ª versão do caminho do sudo)
tests_cmd='"$PY" -c "$probe" && exec "$PY" -m pytest -q -p no:cacheprovider "$@"'
run_inner() { "$PY" -c "$lo_up" && bash -c "$tests_cmd" bash "$@"; }
export -f run_inner
export PY lo_up probe tests_cmd

if [[ -z "${OFFLINE_FORCE_SUDO:-}" ]] && unshare -rn true 2>/dev/null; then
  exec unshare -rn bash -c 'run_inner "$@"' bash "$@"
elif sudo -n unshare -n true 2>/dev/null; then
  # root do namespace sobe a loopback; depois vira o usuário comum e roda a sonda + pytest
  exec sudo -n env "PATH=$PATH" "HOME=$HOME" "PYTHONPATH=${PYTHONPATH:-}" "PY=$PY" "lo_up=$lo_up" "probe=$probe" \
    "tests_cmd=$tests_cmd" "RUN_UID=$(id -u)" "RUN_GID=$(id -g)" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    unshare -n -- bash -c '"$PY" -c "$lo_up" && exec setpriv --reuid="$RUN_UID" --regid="$RUN_GID" --clear-groups \
      env "PY=$PY" "probe=$probe" bash -c "$tests_cmd" bash "$@"' bash "$@"
elif [[ "${OFFLINE_ALLOW_NETWORK:-}" == "1" ]]; then
  echo "AVISO: sem unshare nem sudo; testes rodam COM rede (OFFLINE_ALLOW_NETWORK=1)" >&2
  exec "$PY" -m pytest -q -p no:cacheprovider "$@"
else
  echo "não consigo cortar a rede (unshare -rn e sudo unshare -n indisponíveis); veja o cabeçalho" >&2
  exit 1
fi
