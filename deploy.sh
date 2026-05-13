#!/usr/bin/env bash
set -euo pipefail

APP="orders_consult"
PORTA="5005"
DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$DIR"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        ProtheusData — Deploy         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Pré-requisitos ──────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[ERRO] Docker não encontrado. Instale o Docker e tente novamente."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "[ERRO] Arquivo .env não encontrado em $DIR"
    echo "       Copie o .env.example, preencha as variáveis e rode novamente."
    exit 1
fi

# ── Verificar se a porta está livre ─────────────────────────────────────────
if ss -tln | grep -q ":${PORTA} " && ! docker ps --format "{{.Ports}}" | grep -q "${PORTA}->"; then
    echo "[ERRO] Porta ${PORTA} está ocupada por outro processo."
    echo "       Verifique com: ss -tlnp | grep :${PORTA}"
    exit 1
fi

# ── Build e subida ───────────────────────────────────────────────────────────
echo "[1/3] Construindo imagem Docker..."
docker compose build --no-cache

echo ""
echo "[2/3] Parando versão anterior (se existir)..."
docker compose down --remove-orphans 2>/dev/null || true

echo ""
echo "[3/3] Subindo container em segundo plano..."
docker compose up -d

# ── Aguardar healthcheck ─────────────────────────────────────────────────────
echo ""
echo "Aguardando a aplicação ficar disponível..."
TENTATIVAS=0
MAX=18  # 18 × 5s = 90s de espera máxima
until curl -sf "http://localhost:${PORTA}/health" &>/dev/null; do
    TENTATIVAS=$((TENTATIVAS + 1))
    if [ "$TENTATIVAS" -ge "$MAX" ]; then
        echo ""
        echo "[ERRO] A aplicação não respondeu em 90 segundos."
        echo "       Verifique os logs com: docker logs ${APP}"
        exit 1
    fi
    printf "."
    sleep 5
done

echo ""
echo ""
echo "✔ ProtheusData rodando em http://10.0.253.100:${PORTA}"
echo ""
echo "Comandos úteis:"
echo "  Logs em tempo real : docker logs -f ${APP}"
echo "  Parar              : docker compose down"
echo "  Reiniciar          : docker compose restart"
echo ""
