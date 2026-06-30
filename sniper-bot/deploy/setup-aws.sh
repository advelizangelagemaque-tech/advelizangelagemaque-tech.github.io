#!/usr/bin/env bash
# Bootstrap do sniper numa instância EC2 (Amazon Linux ou Ubuntu).
# Uso:
#   bash setup-aws.sh
# Depois edite o .env com suas chaves e suba o serviço (veja DEPLOY-AWS.md).

set -euo pipefail

echo ">> Instalando dependências do sistema (python, git)..."
if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip git
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip git
else
  echo "!! Gerenciador de pacotes não reconhecido. Instale python3, pip e git manualmente."
  exit 1
fi

# Roda a partir da pasta do projeto (onde este script está).
cd "$(dirname "$0")/.."
echo ">> Pasta do projeto: $(pwd)"

echo ">> Criando ambiente virtual e instalando dependências Python..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements-dev.txt

echo ">> Rodando os testes..."
./venv/bin/python -m pytest -q

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> .env criado a partir do exemplo."
fi

echo ""
echo "============================================================"
echo " Setup concluído. Próximos passos:"
echo "   1) Edite as chaves:   nano .env   (deixe USE_TESTNET=true)"
echo "   2) Proteja o arquivo: chmod 600 .env"
echo "   3) Teste rápido:      ./venv/bin/python -m sniper.main --dry-run"
echo "   4) Rodar 24/7:        veja DEPLOY-AWS.md (serviço systemd)"
echo "============================================================"
