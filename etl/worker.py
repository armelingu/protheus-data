"""
ETL Worker — Processo dedicado de sincronização e full refresh.

Agenda (horário de Brasília):
  02:00  Full refresh de TODOS os relatórios (hash-based para pedidos/estoque,
         carga completa para financeiro — garante consistência total diária)
  08:00–18:00 (horas cheias)
         Sync incremental de todos os relatórios (janela de lookback,
         mesmo comportamento do scheduler anterior no app.py)

Por que separado do app.py?
  - O web server não compete com operações pesadas de I/O
  - O agendamento fica explícito e fácil de auditar
  - Workers Gunicorn duplicados não criam timers duplicados
  - Reiniciar o ETL sem derrubar a UI (e vice-versa)

Execução:
  python3 -u etl/worker.py
  (ou via docker-compose service 'etl')
"""
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# Garante que o path /app (raiz do projeto) esteja no sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# ── Timezone ──────────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo('America/Sao_Paulo')
    def _agora():
        return datetime.now(tz=_TZ).replace(tzinfo=None)
except Exception:
    def _agora():
        return datetime.now()


# ── Imports de serviços ───────────────────────────────────────────────────────

from services.database import criar_tabelas, criar_backup_diario

# Compras
from services.relatorios.compras.pedidos import (
    carga_completa          as full_refresh_pedidos,
    sincronizar             as sync_pedidos,
    carga_inicial           as carga_inicial_pedidos,
    registrar_sync_event    as log_pedidos,
)
from services.relatorios.compras.pedidos_detalhado import (
    carga_completa          as full_refresh_pedidos_det,
    sincronizar             as sync_pedidos_det,
    carga_inicial           as carga_inicial_pedidos_det,
    registrar_sync_event    as log_pedidos_det,
)
from services.relatorios.compras.historico_pedidos import (
    carga_completa_historico as full_refresh_historico,
    sincronizar_historico    as sync_historico,
    carga_inicial_historico  as carga_inicial_historico,
    registrar_sync_event_historico as log_historico,
)
from services.relatorios.compras.pendencia_aprovacao import (
    carga_completa          as full_refresh_pendencia,
    sincronizar             as sync_pendencia,
    carga_inicial           as carga_inicial_pendencia,
    _registrar_sync         as log_pendencia,
)

# Energy
from services.relatorios.energy.pedidos import (
    carga_completa          as full_refresh_pedidos_energy,
    sincronizar             as sync_pedidos_energy,
    carga_inicial           as carga_inicial_pedidos_energy,
    registrar_sync_event    as log_pedidos_energy,
)
from services.relatorios.energy.pedidos_conta_05001 import (
    carga_completa          as full_refresh_pedidos_05001,
    sincronizar             as sync_pedidos_05001,
    carga_inicial           as carga_inicial_pedidos_05001,
    registrar_sync_event    as log_pedidos_05001,
)
from services.relatorios.energy.contas_pagar import (
    full_refresh_energy_contas_pagar,
    sincronizar_energy_contas_pagar,
    carga_inicial_energy_contas_pagar,
)

# Estoque
from services.relatorios.estoque.saldos import (
    carga_completa          as full_refresh_estoque,
    sincronizar             as sync_estoque,
    carga_inicial           as carga_inicial_estoque,
    registrar_sync_event    as log_estoque,
)

# Financeiro
from services.relatorios.financeiro.nf_entrada import (
    full_refresh_nf_entrada,
    sincronizar_nf_entrada,
    carga_inicial_nf_entrada,
)
from services.relatorios.financeiro.nf_saida import (
    full_refresh_nf_saida,
    sincronizar_nf_saida,
    carga_inicial_nf_saida,
)
from services.relatorios.financeiro.contas_receber import (
    full_refresh_contas_receber,
    sincronizar_contas_receber,
    carga_inicial_contas_receber,
)
from services.relatorios.financeiro.contas_pagar import (
    full_refresh_contas_pagar,
    sincronizar_contas_pagar,
    carga_inicial_contas_pagar,
)
from services.relatorios.financeiro.mov_bancarios import (
    full_refresh_mov_bancarios,
    sincronizar_mov_bancarios,
    carga_inicial_mov_bancarios,
)

# ── Locks (evita sobreposição de jobs) ───────────────────────────────────────
_full_refresh_lock = threading.Lock()
_sync_lock         = threading.Lock()

# ── Definição dos jobs ────────────────────────────────────────────────────────

# Módulos que usam hash-based full refresh (pedidos / estoque)
_JOBS_HASH = [
    ('Pedidos de Compra',           full_refresh_pedidos),
    ('Pedidos de Compra Detalhado', full_refresh_pedidos_det),
    ('Histórico de Pedidos',        full_refresh_historico),
    ('Pendência de Aprovação',      full_refresh_pendencia),
    ('Pedidos Energy',              full_refresh_pedidos_energy),
    ('Pedidos Conta 05.001',        full_refresh_pedidos_05001),
    ('Estoque - Saldos',            full_refresh_estoque),
]

# Módulos que usam carga paginada por R_E_C_N_O_ (financeiro + energy CP)
# Esses rodam em paralelo (thread pool) pois são independentes
_JOBS_FINANCEIRO = [
    ('NF Entrada',            full_refresh_nf_entrada),
    ('NF Saída',              full_refresh_nf_saida),
    ('Contas a Receber',      full_refresh_contas_receber),
    ('Contas a Pagar',        full_refresh_contas_pagar),
    ('Movimentos Bancários',  full_refresh_mov_bancarios),
    ('Energy - Contas Pagar', full_refresh_energy_contas_pagar),
]

_JOBS_SYNC_INCREMENTAL = [
    ('Pedidos de Compra',           sync_pedidos),
    ('Pedidos de Compra Detalhado', sync_pedidos_det),
    ('Histórico de Pedidos',        sync_historico),
    ('Pendência de Aprovação',      sync_pendencia),
    ('Pedidos Energy',              sync_pedidos_energy),
    ('Pedidos Conta 05.001',        sync_pedidos_05001),
    ('Estoque - Saldos',            sync_estoque),
]

_JOBS_SYNC_FINANCEIRO = [
    ('NF Entrada',            sincronizar_nf_entrada),
    ('NF Saída',              sincronizar_nf_saida),
    ('Contas a Receber',      sincronizar_contas_receber),
    ('Contas a Pagar',        sincronizar_contas_pagar),
    ('Movimentos Bancários',  sincronizar_mov_bancarios),
    ('Energy - Contas Pagar', sincronizar_energy_contas_pagar),
]

_JOBS_CARGA_INICIAL = [
    ('Pedidos de Compra',           carga_inicial_pedidos),
    ('Pedidos de Compra Detalhado', carga_inicial_pedidos_det),
    ('Histórico de Pedidos',        carga_inicial_historico),
    ('Pendência de Aprovação',      carga_inicial_pendencia),
    ('Pedidos Energy',              carga_inicial_pedidos_energy),
    ('Pedidos Conta 05.001',        carga_inicial_pedidos_05001),
    ('Estoque - Saldos',            carga_inicial_estoque),
    ('NF Entrada',                  carga_inicial_nf_entrada),
    ('NF Saída',                    carga_inicial_nf_saida),
    ('Contas a Receber',            carga_inicial_contas_receber),
    ('Contas a Pagar',              carga_inicial_contas_pagar),
    ('Movimentos Bancários',        carga_inicial_mov_bancarios),
    ('Energy - Contas Pagar',       carga_inicial_energy_contas_pagar),
]


# ── Carga inicial (startup) ────────────────────────────────────────────────────

def executar_carga_inicial():
    """Executa carga inicial para tabelas vazias. Chama carga_inicial() que é no-op se já populada."""
    print('[ETL] Verificando e executando carga inicial...')
    for nome, fn in _JOBS_CARGA_INICIAL:
        try:
            total = fn()
            if total:
                print(f'[ETL] Carga inicial — {nome}: {total} registros.')
        except Exception as exc:
            print(f'[ETL] Carga inicial — {nome}: ERRO: {exc}')
    print('[ETL] Carga inicial concluída.')


# ── Full refresh diário ────────────────────────────────────────────────────────

def executar_full_refresh():
    """Full refresh completo de todos os módulos."""
    if not _full_refresh_lock.acquire(blocking=False):
        print('[ETL] Full refresh já em andamento. Ignorando.')
        return

    inicio = _agora()
    print(f'[ETL] ══════ FULL REFRESH INICIADO ({inicio:%d/%m/%Y %H:%M}) ══════')

    erros = []

    try:
        # Fase 1: Módulos hash-based (sequencial — evita pico no Protheus)
        for nome, fn in _JOBS_HASH:
            try:
                mutacoes = fn()
                print(f'[ETL] Full refresh — {nome}: {mutacoes} mutação(ões).')
            except Exception as exc:
                erros.append(f'{nome}: {exc}')
                print(f'[ETL] Full refresh — {nome}: ERRO: {exc}')

        # Fase 2: Financeiro sequencial no full refresh.
        # Todos os módulos financeiros compartilham o mesmo financeiro.db;
        # rodar em paralelo provoca "database is locked" porque cada full_refresh
        # executa múltiplas transações de escrita (DELETE + batches de INSERT).
        # No sync incremental (fase rápida) continuamos usando threads.
        for nome, fn in _JOBS_FINANCEIRO:
            try:
                total = fn()
                print(f'[ETL] Full refresh — {nome}: {total} registros.')
            except Exception as exc:
                erros.append(f'{nome}: {exc}')
                print(f'[ETL] Full refresh — {nome}: ERRO: {exc}')

        # Backup diário após full refresh bem-sucedido
        if not erros:
            try:
                if criar_backup_diario():
                    print('[ETL] Backup diário criado com sucesso.')
            except Exception as exc:
                print(f'[ETL] Backup diário falhou: {exc}')

    finally:
        _full_refresh_lock.release()

    duracao = int((_agora() - inicio).total_seconds())
    status  = 'com erros' if erros else 'concluído'
    print(f'[ETL] ══════ FULL REFRESH {status.upper()} em {duracao}s ══════')
    if erros:
        for e in erros:
            print(f'[ETL]   → {e}')


# ── Sync incremental ───────────────────────────────────────────────────────────

def executar_sync_incremental():
    """Sync incremental de todos os módulos (janela de lookback)."""
    if not _sync_lock.acquire(blocking=False):
        print('[ETL] Sync incremental já em andamento. Ignorando.')
        return

    inicio = _agora()
    print(f'[ETL] Sync incremental ({inicio:%H:%M})...')

    try:
        # Módulos principais (sequencial)
        for nome, fn in _JOBS_SYNC_INCREMENTAL:
            try:
                n = fn()
                if n:
                    print(f'[ETL] Sync — {nome}: {n} registro(s) alterado(s).')
            except Exception as exc:
                print(f'[ETL] Sync — {nome}: ERRO: {exc}')

        # Financeiro em paralelo
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix='etl-fin-sync') as pool:
            futs = {pool.submit(fn): nome for nome, fn in _JOBS_SYNC_FINANCEIRO}
            for fut in as_completed(futs):
                nome = futs[fut]
                try:
                    n = fut.result()
                    if n:
                        print(f'[ETL] Sync — {nome}: {n} registro(s) alterado(s).')
                except Exception as exc:
                    print(f'[ETL] Sync — {nome}: ERRO: {exc}')

    finally:
        _sync_lock.release()

    duracao = int((_agora() - inicio).total_seconds())
    print(f'[ETL] Sync incremental concluído em {duracao}s.')


# ── Scheduler loop ─────────────────────────────────────────────────────────────

def _proxima_execucao(hora_alvo: int, minuto_alvo: int = 0) -> datetime:
    """Calcula o próximo datetime para a hora/minuto alvo (hoje ou amanhã)."""
    agora = _agora()
    candidato = agora.replace(hour=hora_alvo, minute=minuto_alvo, second=0, microsecond=0)
    if candidato <= agora:
        candidato += timedelta(days=1)
    return candidato


def _segundos_ate(dt: datetime) -> float:
    return max(0.0, (_agora() - dt).total_seconds() * -1)


def scheduler_loop():
    """Loop principal: agenda full refresh às 02:00 e sync incremental nas horas cheias."""
    # Horário do full refresh (configurável via env)
    hora_full_refresh = int(os.getenv('ETL_FULL_REFRESH_HORA', '2'))

    print(f'[ETL] Scheduler iniciado. Full refresh diário às {hora_full_refresh:02d}:00.')
    print(f'[ETL] Sync incremental nas horas cheias (08:00–18:00).')

    while True:
        agora_local = _agora()
        hora    = agora_local.hour
        minuto  = agora_local.minute
        segundo = agora_local.second

        # Full refresh às HH:00 (hora configurada)
        if hora == hora_full_refresh and minuto == 0 and segundo < 30:
            t = threading.Thread(target=executar_full_refresh, daemon=True, name='full-refresh')
            t.start()

        # Sync incremental nas horas cheias entre 08:00 e 18:00
        elif 8 <= hora <= 18 and minuto == 0 and segundo < 30:
            t = threading.Thread(target=executar_sync_incremental, daemon=True, name='sync-incremental')
            t.start()

        # Dorme até o próximo minuto (± 1s para compensar drift)
        tempo_para_prox_minuto = 60 - agora_local.second
        time.sleep(max(1, tempo_para_prox_minuto))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('[ETL] ══════ ETL WORKER INICIADO ══════')

    # Garante schemas e faz carga inicial das tabelas vazias
    criar_tabelas()
    executar_carga_inicial()

    # Inicia o loop de agendamento
    scheduler_loop()
