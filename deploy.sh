#!/usr/bin/env bash
# deploy.sh — Gerenciamento de deploy para produção e homologação
# Uso: ./deploy.sh [prod|homolog|status|logs|refresh-data]

set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERRO]${NC}  $*"; exit 1; }

BRANCH=$(git rev-parse --abbrev-ref HEAD)
COMPOSE_PROD="docker compose -f docker-compose.yml"
COMPOSE_HOMOLOG="docker compose -f homolog/docker-compose.yml"

deploy_prod() {
    if [ "$BRANCH" != "main" ]; then
        error "Deploy de produção só pode ser feito a partir da branch 'main'. Branch atual: '$BRANCH'."
    fi
    info "Iniciando deploy de PRODUÇÃO (branch: main)..."
    warn "Produção será reiniciada brevemente."
    $COMPOSE_PROD build --no-cache
    $COMPOSE_PROD up -d
    success "Produção deployada com sucesso em :5005"
}

deploy_homolog() {
    if [ "$BRANCH" != "develop" ]; then
        warn "Branch atual é '$BRANCH' (esperado: 'develop'). Continuando assim mesmo..."
    fi
    info "Iniciando deploy de HOMOLOGAÇÃO (branch: $BRANCH)..."
    mkdir -p homolog/data
    $COMPOSE_HOMOLOG build --no-cache
    $COMPOSE_HOMOLOG up -d
    success "Homologação deployada com sucesso em :5006"
}

show_status() {
    info "=== Produção (:5005) ==="
    $COMPOSE_PROD ps 2>/dev/null || warn "Produção não está rodando."
    echo ""
    info "=== Homologação (:5006) ==="
    $COMPOSE_HOMOLOG ps 2>/dev/null || warn "Homologação não está rodando."
}

show_logs() {
    local env="${2:-homolog}"
    if [ "$env" = "prod" ]; then
        $COMPOSE_PROD logs --tail=100 -f
    else
        $COMPOSE_HOMOLOG logs --tail=100 -f
    fi
}

refresh_homolog_data() {
    info "Copiando dados de produção → homolog/data/..."
    warn "Os dados atuais de homologação serão substituídos."
    read -r -p "Confirmar? [s/N] " resp
    if [[ "$resp" =~ ^[Ss]$ ]]; then
        cp data/users.db      homolog/data/
        cp data/pedidos.db    homolog/data/
        cp data/financeiro.db homolog/data/
        success "Dados copiados com sucesso."
    else
        info "Operação cancelada."
    fi
}

case "${1:-}" in
    prod)          deploy_prod ;;
    homolog)       deploy_homolog ;;
    status)        show_status ;;
    logs)          show_logs "$@" ;;
    refresh-data)  refresh_homolog_data ;;
    *)
        echo ""
        echo "  Uso: ./deploy.sh <comando>"
        echo ""
        echo "  Comandos:"
        echo "    prod           Deploy de produção  (requer branch: main)"
        echo "    homolog        Deploy de homologação (branch: develop)"
        echo "    status         Status dos dois ambientes"
        echo "    logs [prod]    Logs ao vivo (padrão: homolog)"
        echo "    refresh-data   Copia dados de prod → homolog/data/"
        echo ""
        ;;
esac
