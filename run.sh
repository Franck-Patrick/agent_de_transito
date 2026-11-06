#!/usr/bin/env bash
# Sobe o projeto de qualquer pasta, sem precisar ativar a venv:
# cria a .venv se faltar, instala as dependências e inicia o servidor.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt

echo "Abra http://127.0.0.1:8000 no navegador (Ctrl+C para parar)"
exec .venv/bin/python -m uvicorn app.main:app --reload "$@"
