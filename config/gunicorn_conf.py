"""Configuração do Gunicorn para orders_consult.

Estratégia:
  - 2 workers gthread × 4 threads cada (concorrência alvo: ~8 reqs simultâneos).
  - O scheduler horário (Timer) e a carga inicial são pesados e devem rodar UMA
    vez por instância. Resolvemos isso designando o PRIMEIRO worker forkado
    (worker.age == 0) como SCHEDULER_OWNER. Os demais apenas garantem schema.
  - GUNICORN_WORKER_BOOT=1 silencia o bootstrap automático embutido no app.py
    (`inicializar()` no import) — passa a ser chamado explicitamente no
    post_fork do worker dono.
"""
import os

# Bind / processos
bind          = '0.0.0.0:5000'
workers       = int(os.getenv('GUNICORN_WORKERS', '2'))
threads       = int(os.getenv('GUNICORN_THREADS', '4'))
worker_class  = 'gthread'
timeout       = int(os.getenv('GUNICORN_TIMEOUT', '120'))
graceful_timeout = 30
keepalive     = 5

# Logging
accesslog  = '-'
errorlog   = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sus "%(f)s" "%(a)s"'

# preload_app: importa o WSGI no master ANTES dos forks. Reduz uso de RAM
# (copy-on-write) e tempo de boot por worker. Como inicializar() está atrás
# de GUNICORN_WORKER_BOOT, não roda no master.
preload_app = True


# Contador de forks no master. Usamos para identificar o PRIMEIRO worker
# como SCHEDULER_OWNER. Variável só vive no master (pre_fork roda no master).
_fork_count = {'n': 0}


def on_starting(server):
    """Executado no master antes de qualquer fork (e antes do preload_app)."""
    # NB: GUNICORN_WORKER_BOOT também é setado no Dockerfile como ENV, o que é
    # mais robusto: a env já está no processo antes mesmo do master começar.
    os.environ.setdefault('GUNICORN_WORKER_BOOT', '1')
    server.log.info('orders_consult: master iniciando — workers=%s threads=%s', workers, threads)


def pre_fork(server, worker):
    """No master, antes de cada fork. Atribui o papel ao próximo worker."""
    n = _fork_count['n']
    worker._papel_orders = 'SCHEDULER_OWNER' if n == 0 else 'read-only'
    _fork_count['n'] = n + 1


def post_fork(server, worker):
    """Cada worker, após fork.

    - SCHEDULER_OWNER (primeiro forkado): inicializar() completa (carga +
      backup + agenda Timer horário).
    - Demais workers: apenas garantir_schemas() (idempotente, barato).
    """
    from app import garantir_schemas, inicializar

    papel = getattr(worker, '_papel_orders', 'read-only')
    if papel == 'SCHEDULER_OWNER':
        worker.log.info('orders_consult: worker %s = SCHEDULER_OWNER (carga + sync)', worker.pid)
        try:
            inicializar()
        except Exception as exc:
            worker.log.error('orders_consult: inicializar() falhou: %s', exc)
    else:
        worker.log.info('orders_consult: worker %s = read-only', worker.pid)
        try:
            garantir_schemas()
        except Exception as exc:
            worker.log.error('orders_consult: garantir_schemas() falhou: %s', exc)
