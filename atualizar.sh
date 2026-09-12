#!/bin/bash
# Atualiza tudo de uma vez: baixa os dados novos do WHOOP, carimba o peso do
# dia no histórico e regera o dashboard.
#
# Uso manual:        ./atualizar.sh
# Uso automático:    ver a seção "Atualização automática" no README.
#
# Não precisa de navegador: o token se renova sozinho pelo refresh_token.

set -uo pipefail
cd "$(dirname "$0")" || exit 1

PY=$(command -v python3 || echo /usr/bin/python3)
LOG="atualizar.log"
carimbo() { date "+%Y-%m-%d %H:%M:%S"; }

estado=0
{
  echo "===== $(carimbo) ====="

  if "$PY" whoop.py fetch; then
    "$PY" build_dashboard.py || echo "AVISO: dashboard não foi gerado."
    echo "-- histórico de peso --"
    "$PY" whoop.py weight | tail -6
    echo "ok em $(carimbo)"
  else
    echo "FALHOU no fetch. Se disser que o token foi revogado, rode:"
    echo "  python3 whoop.py url   e autorize de novo no navegador."
    estado=1
  fi
} >> "$LOG" 2>&1

# Mostra o fim do log quando rodado à mão, fica silencioso no automático.
[ -t 1 ] && tail -25 "$LOG"
exit "$estado"
