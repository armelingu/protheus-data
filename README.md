# ProtheusData — README interno

> Documento de referência para LLMs e agentes. Descreve a arquitetura completa,
> convenções de código, rotas, banco de dados, serviços e estado atual do projeto.
> **Atualizado em:** Ago/2026

---

## 1. Visão geral

**ProtheusData** é um portal web interno que **replica dados do ERP Protheus (SQL Server) em bancos SQLite locais** e os expõe via:

- Interface web com autenticação por sessão (Flask + Jinja2)
- API RESTful para operações de sync e download
- Endpoint OData v4 compatível com Power BI

O ERP Protheus é da TOTVS, rodando em SQL Server 2019. O sistema lê o banco do Protheus em **modo somente leitura** (`ApplicationIntent=ReadOnly`, `READ UNCOMMITTED`), copia os dados para SQLite e serve as consultas a partir do cache local — isolando o ERP de queries pesadas dos usuários.

**Empresa:** HBR Aviação  
**Produção:** `http://10.0.10.104:5005`  
**Homologação:** `http://10.0.253.100:5005` (pasta `homolog/`)

---

## 2. Stack técnica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11 |
| Framework web | Flask 3.1 + Gunicorn 25 (gthread) |
| Banco cache (local) | SQLite 3 (WAL mode, 3 arquivos) |
| Banco fonte (ERP) | Microsoft SQL Server 2019 (Protheus P12_PRD) |
| Driver SQL Server | ODBC Driver 17 for SQL Server (via pyodbc 5.3) |
| E-mail | Microsoft Graph API (OAuth2 client_credentials) |
| Exportação | openpyxl 3.1 (XLSX) |
| Compressão HTTP | Flask-Compress |
| Container | Docker + Docker Compose (2 serviços: `web` + `etl`) |
| Frontend | Jinja2 templates + CSS/JS vanilla |
| Frontend (mockup futuro) | React 18 + Material UI v9 + Vite 5 (pasta `mockup/`) |

---

## 3. Estrutura de diretórios

```
orders_consult/
├── app.py                        # Aplicação Flask monolítica (~4600 linhas)
├── requirements.txt              # Dependências Python
├── Dockerfile                    # Imagem python:3.11-slim + ODBC Driver 17
├── docker-compose.yml            # 2 serviços: web (porta 5005) + etl
├── deploy.sh                     # Script de deploy
├── .env                          # Variáveis de ambiente (NÃO comitar)
├── .env.example                  # Template documentado de todas as variáveis
├── .gitignore
│
├── config/
│   └── gunicorn_conf.py          # 2 workers × 4 threads; sem scheduler (delegado ao ETL)
│
├── etl/                          # Processo ETL dedicado (roda em container separado)
│   ├── __init__.py
│   └── worker.py                 # Scheduler: full refresh diário 02:00 + sync horário 08-18h
│
├── services/
│   ├── database.py               # Conexões SQLite, schemas, backup, pragmas WAL
│   ├── protheus_readonly.py      # Conexão pyodbc ao SQL Server; retry; validação SELECT
│   ├── sync_engine.py            # Engine de full refresh baseado em hash MD5
│   ├── catalogo_relatorios.py    # Catálogo de módulos/relatórios e permissões
│   ├── cache.py                  # Cache Redis opcional (permissões de usuário)
│   ├── email_service.py          # Envio de e-mail via Microsoft Graph API (OAuth2)
│   ├── time_utils.py             # Timezone America/Sao_Paulo, helpers de data
│   └── relatorios/               # Queries SQL + lógica de sync por módulo
│       ├── compras/
│       │   ├── pedidos.py                  # Pedidos de Compra
│       │   ├── pedidos_detalhado.py        # Pedidos de Compra Detalhado (CC, conta, cond. pgto)
│       │   ├── historico_pedidos.py        # Histórico de Pedidos
│       │   └── pendencia_aprovacao.py      # Pendência de Aprovação
│       ├── estoque/
│       │   └── saldos.py                   # Saldo em Estoque
│       ├── financeiro/
│       │   ├── base.py                     # Engine compartilhada (keyset pagination, sync window)
│       │   ├── nf_entrada.py
│       │   ├── nf_saida.py
│       │   ├── contas_receber.py
│       │   ├── contas_pagar.py
│       │   └── mov_bancarios.py
│       └── energy/
│           ├── pedidos.py                  # Pedidos Energy (filtro por comprador + item 05.001)
│           ├── pedidos_conta_05001.py      # Pedidos Conta 05.001 (todos os compradores)
│           └── contas_pagar.py
│
├── templates/                    # Jinja2 (herdam de base_auth.html)
│   ├── base_auth.html
│   ├── login/, auth/, perfil/, gerente/
│   ├── admin/                    # usuarios.html, setores.html, auditoria.html
│   └── relatorios/               # 1 template por relatório
│
├── statics/
│   ├── css/                      # CSS vanilla por seção
│   └── js/                       # JS vanilla por seção
│
├── scripts/
│   └── criar_usuario.py          # Script CLI para criar usuário admin inicial
│
├── docs/
│   ├── ISSUES.md                 # Issues de CSS/frontend
│   └── DESIGN_SYSTEM.md          # Tokens e guia de estilo
│
├── data/                         # Volume Docker (NÃO comitar — gerado em runtime)
│   ├── users.db                  # Usuários, sessões, permissões, logs de acesso
│   ├── pedidos.db                # Cache: pedidos de compra + estoque + energy
│   ├── financeiro.db             # Cache: NF, títulos, movimentos bancários
│   └── backups/                  # Backups automáticos diários dos .db
│
├── homolog/                      # Ambiente de homologação independente
│   ├── docker-compose.yml
│   ├── .env
│   └── data/
│
└── mockup/                       # Protótipo React + MUI (referência futura de UI)
    ├── src/
    │   ├── App.jsx
    │   ├── theme.js              # Tema MUI customizado (paleta HBR)
    │   ├── components/
    │   └── pages/
    ├── start-mockup.sh
    └── package.json
```

---

## 4. Bancos de dados SQLite

O sistema usa **3 arquivos SQLite** no diretório `data/`, todos com WAL mode e os seguintes PRAGMAs aplicados em toda conexão:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-65536;    -- 64 MB por conexão
PRAGMA mmap_size=268435456;  -- 256 MB mmap
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;    -- 5s antes de SQLITE_BUSY
```

### 4.1 `users.db` — Usuários e controle de acesso

| Tabela | Descrição |
|---|---|
| `usuarios` | id, login, nome, email, senha_hash, perfil, setor_id, ativo, ... |
| `setores` | id, nome, ativo |
| `permissoes_usuario` | usuario_id → chave de relatório (ex: `financeiro.contas_receber`) |
| `permissoes_setor` | setor_id → chave de relatório |
| `api_tokens` | Tokens Bearer para acesso OData (Power BI) |
| `logs_acesso` | Auditoria de login/logout/ações |
| `auditoria_admin` | Ações administrativas de usuários admin/gerente |
| `rate_limit` | IPs com tentativas de login suspeitas |
| `logs_email` | Histórico de e-mails enviados pelo sistema |

### 4.2 `pedidos.db` — Compras, Estoque e Energy

| Tabela | Tabela Protheus | Estratégia sync |
|---|---|---|
| `pedidos` | SC7 (Pedidos de Compra) | Hash MD5 (full_refresh_com_hash) |
| `pedidos_detalhado` | SC7 + CTT/CTD/CT1/SE4 (com CC, conta, cond. pgto) | Hash MD5 |
| `pedidos_historico` | SC7 (visão histórica, sem filtro de comprador) | Hash MD5 |
| `pendencia_aprovacao` | SC7 + SCR (nível de aprovação) | Hash MD5 |
| `pedidos_energy` | SC7 filtrado por compradores Energy + item 05.001 | Hash MD5 |
| `pedidos_conta_05001` | SC7 filtrado por C7_ITEMCTA = '05.001' (todos compradores) | Hash MD5 |
| `estoque_saldos` | SB2 (Saldo em Estoque) | Hash MD5 |
| `_etl_hash_cache` | — | Cache interno de hashes MD5 por tabela (usado pelo sync_engine) |
| `*_sync_log` | — | Log de execuções de sync por módulo |

### 4.3 `financeiro.db` — Financeiro

| Tabela | Tabela Protheus | Estratégia sync |
|---|---|---|
| `nf_entrada_itens` | SD1 (Itens NF Entrada) | Keyset pagination (R_E_C_N_O_) |
| `nf_saida_itens` | SD2 (Itens NF Saída) | Keyset pagination |
| `contas_receber` | SE1 (Títulos a Receber) | Keyset pagination |
| `contas_pagar` | SE2 (Títulos a Pagar) | Keyset pagination |
| `mov_bancarios` | SE5 (Movimentos Bancários) | Keyset pagination |
| `energy_contas_pagar` | SE2 filtrado por E2_ITEMD = '05.001' | Keyset pagination |
| `sync_cursor` | — | Último R_E_C_N_O_ processado por tabela |
| `*_sync_log` | — | Log de execuções de sync por módulo |

---

## 5. Arquitetura ETL

### 5.1 Visão geral

O sistema usa **dois containers independentes** para separar o servidor web do processamento ETL:

```
┌──────────────────────┐       SQLite WAL        ┌──────────────────────┐
│   Container: web     │ ←───── shared volume ──→ │   Container: etl     │
│   Flask + Gunicorn   │       ./data/*.db         │   etl/worker.py      │
│   Serve relatórios   │                           │   Scheduler + sync   │
└──────────────────────┘                           └──────────────────────┘
        ↑                                                    ↓
   Leitura SQLite                                   Escrita Protheus → SQLite
```

O SQLite com **WAL mode** permite leituras concorrentes enquanto o ETL escreve — usuários não percebem impacto durante o sync.

### 5.2 Agenda do ETL worker

| Horário | Job | Descrição |
|---|---|---|
| **startup** | Carga inicial | `carga_inicial()` para qualquer tabela vazia (no-op se já populada) |
| **02:00** (diário) | Full refresh | Recarrega **todos** os 13 relatórios do Protheus |
| **08:00–18:00** (horas cheias) | Sync incremental | Janela de lookback para cada módulo |

Horário do full refresh configurável via `ETL_FULL_REFRESH_HORA` (padrão: `2`).

### 5.3 Estratégias de sincronização

#### Hash MD5 — `services/sync_engine.py` (pedidos, estoque)

Usado pelos 7 módulos que têm chave única clara (pedidos/estoque):

```
Protheus → normaliza linha → calcula MD5 → compara com _etl_hash_cache
  → hash igual   : ignora (zero escrita no SQLite)
  → hash diferente: upsert apenas essa linha
  → linha sumiu  : delete real (orphan eliminado)
```

**Vantagens:**
- Escreve somente o que mudou → lock de escrita mínimo
- Detecta deletions reais (sem dependência de lookback)
- Idempotente e atômico

#### Keyset pagination — `services/relatorios/financeiro/base.py` (financeiro)

Usado pelos 6 módulos financeiros que não têm chave única simples e têm volume alto (100k–135k registros):

- **Carga inicial**: itera por `R_E_C_N_O_` em batches de 5.000 registros
- **Sync incremental**: date-window (`max_data_local - lookback_dias`)
- **Full refresh**: `DELETE FROM tabela` + `DELETE FROM sync_cursor` + reexecuta carga inicial

### 5.4 Janelas de lookback (sync incremental)

| Variável `.env` | Módulo | Padrão |
|---|---|---|
| `SYNC_LOOKBACK_PEDIDOS` | Pedidos de Compra (compras + energy) | 60 dias |
| `SYNC_LOOKBACK_HISTORICO` | Histórico de Pedidos | 30 dias |
| `SYNC_LOOKBACK_NF` | NF Entrada e NF Saída | 30 dias |
| `SYNC_LOOKBACK_MOV_BANCARIOS` | Movimentos Bancários | 30 dias |
| `SYNC_LOOKBACK_TITULOS` | Contas a Pagar, Receber, Energy C. Pagar | **365 dias** |
| `SYNC_LOOKBACK_DAYS` | Fallback global | 30 dias |

> **Por que 365 dias nos títulos?** Títulos vencidos há meses podem ser baixados a qualquer momento. Um lookback curto faria o sync ignorar essas baixas, deixando saldos desatualizados.

### 5.5 Adicionar um novo módulo de relatório

Para criar um novo módulo que usa hash-based full refresh:

1. Criar `services/relatorios/<modulo>/<nome>.py` com:
   - `QUERY_COMPLETA` — SQL que retorna todos os registros
   - `INSERT_*` — UPSERT SQL com `ON CONFLICT DO UPDATE`
   - `_norm(v)` — normalizador de valor
   - `registrar_sync_event(...)` — logger de sync
   - `carga_completa()` chamando `full_refresh_com_hash()`
   - `carga_inicial()` — no-op se tabela populada
   - `sincronizar()` — sync incremental (date-window)

2. Registrar no `services/catalogo_relatorios.py`

3. Adicionar imports e rota em `app.py`

4. Adicionar ao `etl/worker.py` (`_JOBS_HASH` e `_JOBS_SYNC_INCREMENTAL`)

---

## 6. Conexão com o Protheus

**Arquivo:** `services/protheus_readonly.py`

- Driver: `ODBC Driver 17 for SQL Server`
- Modo: `ApplicationIntent=ReadOnly`, `READ UNCOMMITTED`
- `TrustServerCertificate=yes` (contorna problemas de certificado na rede interna)
- Validação de query: só aceita `SELECT`; bloqueia `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.
- Retry automático em erros transientes: até `PROTHEUS_MAX_RETRIES` tentativas com backoff linear de 5s

**Timeouts:**

| Variável | Significado | Padrão |
|---|---|---|
| `PROTHEUS_CONNECT_TIMEOUT` | Tempo para estabelecer conexão TCP + login | 30s |
| `PROTHEUS_QUERY_TIMEOUT` | Tempo máximo de execução de cada SELECT | 60s (ETL: 120s) |
| `PROTHEUS_MAX_RETRIES` | Tentativas em erro transiente | 2 |

---

## 7. Autenticação e autorização

### Perfis de usuário

| Perfil | Acesso |
|---|---|
| `admin` | Tudo: usuários, setores, auditoria, todos os relatórios |
| `gerente` | Usuários do próprio setor; relatórios do setor |
| `usuario` | Somente relatórios com permissão explícita |

### Hierarquia de permissões

1. **Admin** → acesso total automático
2. **Permissões do usuário** (`permissoes_usuario`) → específicas por usuário
3. **Permissões do setor** (`permissoes_setor`) → herdadas pelo setor

### Autenticação via API Token (OData / Power BI)

- Tokens Bearer criados pelo próprio usuário na página "Meu Perfil"
- Cada token tem permissões de relatório independentes
- Usados no header `Authorization: Bearer <token>`

### Proteções

- Rate limit por IP em `/api/login` (bloqueio progressivo)
- CSRF token em todos os formulários/POSTs
- Sessão com `SESSION_LIFETIME_SECONDS` (padrão: 7 dias)
- `SESSION_COOKIE_SECURE=true` em produção HTTPS

---

## 8. Rotas HTTP

### Páginas (GET — retornam HTML)

| Rota | Acesso | Descrição |
|---|---|---|
| `/` | Público | Redirect para `/login` ou `/relatorios` |
| `/login` | Público | Tela de login |
| `/primeiro-acesso` | Público | Definição de senha no primeiro acesso |
| `/relatorios` | Autenticado | Home dos relatórios (cards por módulo) |
| `/meu-perfil` | Autenticado | Perfil do usuário e gerenciamento de tokens |
| `/admin/usuarios` | Admin | Lista e gerenciamento de usuários |
| `/admin/setores` | Admin | Setores e permissões coletivas |
| `/admin/auditoria` | Admin | Logs de auditoria |
| `/gerente` | Gerente | Usuários do setor |
| `/relatorios/compras/pedidos` | Perm. | Pedidos de Compra |
| `/relatorios/compras/pedidos-detalhado` | Perm. | Pedidos de Compra Detalhado |
| `/relatorios/compras/historico` | Perm. | Histórico de Pedidos |
| `/relatorios/compras/pendencia-aprovacao` | Perm. | Pendência de Aprovação |
| `/relatorios/estoque/saldos` | Perm. | Saldo em Estoque |
| `/relatorios/financeiro/nf-entrada` | Perm. | NF de Entrada |
| `/relatorios/financeiro/nf-saida` | Perm. | NF de Saída |
| `/relatorios/financeiro/contas-receber` | Perm. | Contas a Receber |
| `/relatorios/financeiro/contas-pagar` | Perm. | Contas a Pagar |
| `/relatorios/financeiro/mov-bancarios` | Perm. | Movimentos Bancários |
| `/relatorios/energy/contas-pagar` | Perm. | Energy — Contas a Pagar |
| `/relatorios/energy/pedidos` | Perm. | Energy — Pedidos de Compra |
| `/relatorios/energy/pedidos-conta-05001` | Perm. | Energy — Pedidos Conta 05.001 |

### API REST (JSON)

Cada relatório tem 4 endpoints no padrão `/api/relatorios/<modulo>/<id>/`:

| Sufixo | Método | Descrição |
|---|---|---|
| `/info` | GET | Metadados: total de registros, último sync, status |
| `/historico-sync` | GET | Últimos N syncs do módulo |
| `/sync` | POST | Dispara sync incremental manual imediato |
| `/download` | GET | Retorna arquivo XLSX |

**Outros endpoints relevantes:**

| Rota | Método | Descrição |
|---|---|---|
| `/api/login` | POST | Autenticação (retorna cookie de sessão) |
| `/api/logout` | POST | Encerra sessão |
| `/api/csrf-token` | GET | Retorna CSRF token atual |
| `/api/meu-perfil/tokens` | GET/POST | Listar/criar API tokens |
| `/api/meu-perfil/tokens/<id>` | DELETE | Revogar token |
| `/api/admin/usuarios` | GET/POST | CRUD usuários (admin) |
| `/api/admin/usuarios/<id>/configuracao` | POST | Alterar perfil/setor/permissões |
| `/api/admin/usuarios/<id>/status` | POST | Ativar/desativar usuário |
| `/api/admin/usuarios/<id>/reset-senha` | POST | Forçar reset de senha |
| `/api/admin/setores` | GET/POST/DELETE | CRUD setores |
| `/api/admin/setores/<id>/configuracao` | POST | Permissões do setor |
| `/api/admin/full-refresh` | POST | Dispara full refresh manual (body: `{"relatorio": "todos"}`) |
| `/api/admin/logs` | GET | Logs de acesso paginados |
| `/api/gerente/usuarios` | GET | Usuários do setor (gerente) |
| `/health` | GET | Health check (Docker) |

### OData v4 (Power BI)

Requer header `Authorization: Bearer <api_token>`.

| Endpoint | Tabela |
|---|---|
| `/odata/pedidos` | Pedidos de Compra |
| `/odata/pedidos-detalhado` | Pedidos de Compra Detalhado |
| `/odata/energy-pedidos` | Energy — Pedidos |
| `/odata/historico-pedidos` | Histórico de Pedidos |
| `/odata/pendencia-aprovacao` | Pendência de Aprovação |
| `/odata/estoque` | Saldo em Estoque |
| `/odata/nf-entrada` | NF de Entrada |
| `/odata/nf-saida` | NF de Saída |
| `/odata/contas-receber` | Contas a Receber |
| `/odata/contas-pagar` | Contas a Pagar |
| `/odata/mov-bancarios` | Movimentos Bancários |
| `/odata/energy-contas-pagar` | Energy — Contas a Pagar |
| `/odata/$metadata` | Schema EDMX (descoberta pelo Power BI) |

---

## 9. Variáveis de ambiente (.env)

Ver `.env.example` para documentação completa. Resumo:

```dotenv
# Banco Protheus (SQL Server)
DB_SERVER=<IP>
DB_DATABASE=P12_PRD
DB_USERNAME=sa
DB_PASSWORD=<senha>

# Flask
SECRET_KEY=<hex-32-bytes>
SESSION_LIFETIME_SECONDS=604800     # 7 dias
SESSION_COOKIE_SECURE=false         # true em HTTPS
TRUST_PROXY_HEADERS=false           # true se houver Nginx na frente

# Timeouts Protheus
PROTHEUS_CONNECT_TIMEOUT=30
PROTHEUS_QUERY_TIMEOUT=60
PROTHEUS_MAX_RETRIES=2

# Janelas de sync incremental por módulo (dias retroativos)
SYNC_LOOKBACK_TITULOS=365           # Crítico — não reduzir
SYNC_LOOKBACK_PEDIDOS=60
SYNC_LOOKBACK_HISTORICO=30
SYNC_LOOKBACK_NF=30
SYNC_LOOKBACK_MOV_BANCARIOS=30
SYNC_LOOKBACK_DAYS=30               # Fallback global

# E-mail — Microsoft Graph API (OAuth2 client_credentials)
EMAIL_ENABLED=true
EMAIL_PROVIDER=msgraph
EMAIL_FROM=totvs@hbraviacao.com.br
MS_TENANT_ID=<guid-do-tenant>
MS_CLIENT_ID=<guid-do-app-no-entra>
MS_CLIENT_SECRET=<segredo-do-app>

# URL base para links nos e-mails
APP_BASE_URL=http://10.0.253.100:5005

# ETL — Agendamento e alertas
ETL_FULL_REFRESH_HORA=2             # Hora do full refresh diário (0–23)
ETL_ALERT_EMAILS=ti@hbraviacao.com.br  # Destinatários de alertas de sucesso/falha (CSV)
```

---

## 10. Docker e deploy

### Serviços

O `docker-compose.yml` define **dois serviços** que compartilham o volume `./data`:

| Serviço | Container | Função |
|---|---|---|
| `web` | `orders_consult` | Servidor Flask (Gunicorn) — porta 5005 |
| `etl` | `orders_consult_etl` | ETL worker — sync + full refresh agendados |

### Build e subida (produção)

```bash
cd /home/hbradmin/orders_consult

# Primeira vez ou após mudanças no código/dependências:
docker compose build --no-cache && docker compose up -d

# Rebuild só do ETL (mais rápido, não derruba o web):
docker compose build etl && docker compose up -d etl

# Reiniciar sem rebuild:
docker compose restart
```

### Estrutura dos containers

- Imagem base: `python:3.11-slim`
- ODBC Driver 17 instalado via APT (Microsoft repo)
- **web**: Gunicorn 2 workers gthread × 4 threads, bind `0.0.0.0:5000`
- **etl**: `python3 -u etl/worker.py` (processo standalone, sem Gunicorn)
- Volume compartilhado: `./data:/app/data` (bancos SQLite persistentes)
- Health check (web): `GET /health` a cada 60s

### Criar usuário admin inicial

```bash
docker exec -it orders_consult python scripts/criar_usuario.py
```

### Forçar full refresh manual

```bash
docker exec orders_consult_etl python3 -c "
import sys; sys.path.insert(0, '/app')
from dotenv import load_dotenv; load_dotenv()
from etl.worker import executar_full_refresh
executar_full_refresh()
"
```

Ou via API (requer cookie de sessão admin):
```bash
curl -X POST http://localhost:5005/api/admin/full-refresh \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -H "X-CSRF-Token: ..." \
  -d '{"relatorio": "todos"}'
```

---

## 11. Módulos de relatório

| Chave | Módulo | Relatório | Tabela Protheus | Tabela SQLite |
|---|---|---|---|---|
| `compras.pedidos` | Compras | Pedidos de Compra | SC7 | `pedidos` |
| `compras.pedidos_detalhado` | Compras | Pedidos de Compra Detalhado | SC7+CTT+CTD+CT1+SE4 | `pedidos_detalhado` |
| `compras.historico` | Compras | Histórico de Pedidos | SC7 | `pedidos_historico` |
| `compras.pendencia_aprovacao` | Compras | Pendência de Aprovação | SC7+SCR | `pendencia_aprovacao` |
| `estoque.saldos` | Estoque | Saldo em Estoque | SB2 | `estoque_saldos` |
| `financeiro.nf_entrada` | Financeiro | NF de Entrada | SD1 | `nf_entrada_itens` |
| `financeiro.nf_saida` | Financeiro | NF de Saída | SD2 | `nf_saida_itens` |
| `financeiro.contas_receber` | Financeiro | Contas a Receber | SE1 | `contas_receber` |
| `financeiro.contas_pagar` | Financeiro | Contas a Pagar | SE2 | `contas_pagar` |
| `financeiro.mov_bancarios` | Financeiro | Mov. Bancários | SE5 | `mov_bancarios` |
| `energy.contas_pagar` | Energy | Contas a Pagar | SE2 (E2_ITEMD=05.001) | `energy_contas_pagar` |
| `energy.pedidos` | Energy | Pedidos de Compra | SC7 (compradores Energy) | `pedidos_energy` |
| `energy.pedidos_conta_05001` | Energy | Pedidos Conta 05.001 | SC7 (todos compradores, item 05.001) | `pedidos_conta_05001` |

### Colunas extras em `pedidos_detalhado`

Além de todas as colunas de `pedidos`, esse relatório inclui:

| Coluna | Tabela Protheus | Descrição |
|---|---|---|
| `centro_custo` / `centro_custo_desc` | CTT010 (chave: C7_CC) | Centro de Custo e descrição |
| `item_conta` / `item_conta_desc` | CTD010 (chave: C7_ITEMCTA) | Item Orçamentário e descrição |
| `conta_contabil` / `conta_contabil_desc` | CT1010 (chave: C7_CONTA) | Conta Contábil e descrição |
| `cond_pagamento` / `cond_pagamento_desc` | SE4010 (chave: C7_COND) | Condição de Pagamento e descrição |

> As tabelas auxiliares são consultadas via `OUTER APPLY (SELECT TOP 1 ...)` para evitar multiplicação de linhas causada pela separação por filial no Protheus.

---

## 12. E-mail — Microsoft Graph API

O sistema envia e-mails via **Microsoft Graph API** usando OAuth2 `client_credentials` (sem MFA, sem interação do usuário).

**Configuração necessária no Microsoft Entra (Azure AD):**
1. Criar um **Registro de Aplicativo** no Entra
2. Tipo de conta: *Somente minha organização*
3. Permissão de **aplicativo** (não delegada): `Mail.Send`
4. Conceder **consentimento de administrador** para a permissão
5. Criar um **segredo do cliente** e preencher `MS_CLIENT_SECRET` no `.env`

**E-mails enviados pelo sistema:**
- Boas-vindas / primeiro acesso do usuário
- Reset de senha solicitado por admin
- **ETL full refresh concluído** (tabela com resumo por módulo)
- **ETL full refresh com falha** (lista de módulos que falharam)

---

## 13. Alertas do ETL

Quando configurado `ETL_ALERT_EMAILS`, o ETL worker envia e-mail após cada full refresh:

| Situação | Assunto | Conteúdo |
|---|---|---|
| **Sucesso** | `[ProtheusData] ETL — Full refresh concluído (DD/MM às HH:MM)` | Tabela com módulo + registros/mutações + duração |
| **Com erros** | `[ProtheusData] ETL — Falha no full refresh (DD/MM às HH:MM)` | Lista dos módulos que falharam + instrução de diagnóstico |

Para múltiplos destinatários, separar por vírgula:
```
ETL_ALERT_EMAILS=ti@hbraviacao.com.br,gerencia@hbraviacao.com.br
```

---

## 14. Convenções de código

### Python (`app.py` e `services/`)

- Funções utilitárias antes das rotas no `app.py`
- Decorators de proteção: `@login_requerido`, `@admin_requerido`, `@gerente_requerido`, `@acesso_relatorio_requerido(modulo_id, relatorio_id)`
- Todos os retornos de API usam `jsonify({})` com campo `ok: bool`
- Queries SQL no Protheus ficam nos arquivos dentro de `services/relatorios/`
- **Nunca** executar INSERT/UPDATE/DELETE no Protheus — `validar_query_somente_leitura()` bloqueia automaticamente
- Novos módulos de relatório devem exportar `carga_completa()` usando `sync_engine.full_refresh_com_hash()`

### Templates Jinja2

- Herdam de `templates/base_auth.html`
- Bloco `{% block conteudo %}` para o conteúdo de cada página
- Bloco `{% block scripts %}` para JS específico da página

### CSS/JS vanilla

- CSS por seção em `statics/css/<seção>/`
- JS por seção em `statics/js/<seção>/`
- Sem bundler; arquivos referenciados diretamente nos templates
- `border-radius: 0` como padrão de design (flat, monochromatic)

---

## 15. Arquivos que NÃO devem ser modificados sem cuidado

| Arquivo | Risco |
|---|---|
| `services/protheus_readonly.py` | Qualquer mudança pode afetar TODOS os syncs |
| `services/database.py` — funções de schema | Mudança em schema exige migração do SQLite existente |
| `services/sync_engine.py` | Afeta o full refresh de 7 módulos simultaneamente |
| `config/gunicorn_conf.py` | Erros aqui impedem o boot do container |
| `etl/worker.py` — scheduler_loop | Lógica de agendamento crítica |
| `.env` | Contém credenciais de produção |
| `data/*.db` | Bancos de produção — nunca editar manualmente |

---

## 16. Comandos úteis

```bash
# Ver logs em tempo real
docker compose logs -f web
docker compose logs -f etl

# Entrar no container web
docker exec -it orders_consult bash

# Reiniciar sem rebuild
docker compose restart

# Rebuild completo (ambos os containers)
docker compose build --no-cache && docker compose up -d

# Rebuild só do ETL (web continua no ar)
docker compose build etl && docker compose up -d etl

# Verificar saúde
curl http://localhost:5005/health

# Ver status dos containers
docker compose ps

# Forçar full refresh agora
docker exec orders_consult_etl python3 -c "
import sys; sys.path.insert(0, '/app')
from dotenv import load_dotenv; load_dotenv()
from etl.worker import executar_full_refresh
executar_full_refresh()
"

# Ver bancos SQLite
sqlite3 data/pedidos.db ".tables"
sqlite3 data/financeiro.db ".tables"
sqlite3 data/users.db "SELECT login, perfil, ativo FROM usuarios;"

# Contar registros por tabela (pedidos.db)
sqlite3 data/pedidos.db "
  SELECT 'pedidos', COUNT(*) FROM pedidos
  UNION ALL SELECT 'pedidos_detalhado', COUNT(*) FROM pedidos_detalhado
  UNION ALL SELECT 'estoque_saldos', COUNT(*) FROM estoque_saldos;
"

# Testar sync manual via API (requer cookie de sessão admin)
curl -X POST http://localhost:5005/api/relatorios/compras/pedidos/sync \
  -H "Cookie: session=..." \
  -H "X-CSRF-Token: ..."
```
