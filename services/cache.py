"""Camada de cache opt-in (Redis com fallback in-memory).

Habilitação: defina CACHE_REDIS_URL no ambiente (ex.:
`redis://intranet_redis:6379/0`). Sem essa variável, a camada degrada para um
dict em memória do worker — útil para desenvolvimento, mas sem invalidação
distribuída entre workers/instâncias.

Uso:
    from services.cache import cache_get, cache_set, cache_delete, cache_namespace

    val = cache_get('perm:user:42')
    if val is None:
        val = consultar_db()
        cache_set('perm:user:42', val, ttl=60)

    # Invalidar todas as chaves de um namespace (suporte tanto Redis quanto fallback)
    cache_namespace('perm:user').invalidate()

Boas práticas:
- TTL curto (30-300s) para dados de auth/permissões.
- TTL maior (1h+) para dados estáticos como catálogo de relatórios.
- Sempre tolere falha do cache: a chamada deve cair para a fonte original.
"""
import json
import os
import time
import threading

_REDIS_URL = os.getenv('CACHE_REDIS_URL', '').strip()
_REDIS_TIMEOUT = float(os.getenv('CACHE_REDIS_TIMEOUT', '0.5'))  # segundos

_redis_client = None
_redis_lock = threading.Lock()
_fallback_store = {}  # chave -> (expira_em_epoch, valor_serializado)
_fallback_lock = threading.Lock()


def _conectar_redis():
    """Tenta conectar ao Redis. Em caso de falha, cai para fallback silencioso."""
    global _redis_client
    if not _REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis  # type: ignore
            client = redis.Redis.from_url(
                _REDIS_URL,
                socket_connect_timeout=_REDIS_TIMEOUT,
                socket_timeout=_REDIS_TIMEOUT,
                decode_responses=False,
            )
            client.ping()
            _redis_client = client
        except Exception as exc:
            print(f'[CACHE] Redis indisponível ({exc}). Usando fallback in-memory.')
            _redis_client = False  # marca como tentado e falhou
    return _redis_client if _redis_client is not False else None


def _fallback_get(chave):
    with _fallback_lock:
        item = _fallback_store.get(chave)
        if not item:
            return None
        expira_em, valor = item
        if expira_em and expira_em < time.time():
            _fallback_store.pop(chave, None)
            return None
        return valor


def _fallback_set(chave, valor, ttl):
    expira = time.time() + ttl if ttl else 0
    with _fallback_lock:
        _fallback_store[chave] = (expira, valor)


def _fallback_delete(prefixo):
    with _fallback_lock:
        for k in list(_fallback_store):
            if k.startswith(prefixo):
                _fallback_store.pop(k, None)


def cache_get(chave):
    cli = _conectar_redis()
    if cli:
        try:
            raw = cli.get(chave)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    raw = _fallback_get(chave)
    return json.loads(raw) if raw else None


def cache_set(chave, valor, ttl=60):
    raw = json.dumps(valor, default=str)
    cli = _conectar_redis()
    if cli:
        try:
            cli.set(chave, raw, ex=ttl)
            return
        except Exception:
            pass
    _fallback_set(chave, raw, ttl)


def cache_delete(chave):
    cli = _conectar_redis()
    if cli:
        try:
            cli.delete(chave)
        except Exception:
            pass
    with _fallback_lock:
        _fallback_store.pop(chave, None)


class _Namespace:
    def __init__(self, prefixo):
        self.prefixo = prefixo

    def invalidate(self):
        cli = _conectar_redis()
        if cli:
            try:
                # SCAN é seguro para produção (não bloqueia como KEYS).
                for k in cli.scan_iter(match=f'{self.prefixo}*', count=200):
                    cli.delete(k)
            except Exception:
                pass
        _fallback_delete(self.prefixo)


def cache_namespace(prefixo):
    return _Namespace(prefixo)
