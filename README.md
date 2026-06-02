# ProtheusData — README interno

> Documento de referência para LLMs e agentes. Descreve a arquitetura completa,
> convenções de código, rotas, banco de dados, serviços e estado atual do projeto.
> **Atualizado em:** Mai/2026

---

## 1. Visão geral

**ProtheusData** é um portal web interno que **replica dados do ERP Protheus (SQL Server) em um banco SQLite local** e os expõe via:

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
| Cache de permissões | Redis (opcional; fallback em memória se indisponível) |
| Exportação | openpyxl 3.1 (XLSX) |
| Compressão HTTP | Flask-Compress |
| Container | Docker + Docker Compose |
| Frontend (atual) | Jinja2 templates + CSS/JS vanilla |
| Frontend (mockup futuro) | React 18 + Material UI v9 + Vite 5 (pasta `mockup/`) |

---

## 3. Estrutura de diretórios

```
orders_consult/
├── app.py                        # Aplicação Flask monolítica (~4100 linhas)
├── requirements.txt              # Dependências Python
├── Dockerfile                    # Imagem python:3.11-slim + ODBC Driver 17
├── docker-compose.yml            # Produção: porta 5005→5000, volume ./data
├── deploy.sh                     # Script de deploy
├── .env                          # Variáveis de ambiente (NÃO comitar)
├── .env.example                  # Template documentado de todas as variáveis
├── .gitignore
│
├── config/
│   └── gunicorn_conf.py          # 2 workers × 4 threads; scheduler no worker 0
│
├── services/
│   ├── database.py               # Conexões SQLite, schemas, backup, pragmas WAL
│   ├── protheus_readonly.py      # Conexão pyodbc ao SQL Server; retry; validação SELECT
│   ├── catalogo_relatorios.py    # Catálogo de módulos/relatórios e permissões
│   ├── cache.py                  # Cache Redis opcional (permissões de usuário)
│   ├── email_service.py          # Envio de e-mail via SMTP (Gmail)
│   ├── time_utils.py             # Timezone America/Sao_Paulo, helpers de data
│   └── relatorios/               # Queries SQL por módulo
│       ├── compras/              # pedidos.py, historico.py
│       ├── estoque/              # saldos.py
│       ├── financeiro/           # nf_entrada.py, nf_saida.py, contas_receber.py,
│       │                         #   contas_pagar.py, mov_bancarios.py
│       └── energy/               # contas_pagar.py, pedidos.py
│
├── templates/                    # Jinja2 (herdam de base_auth.html)
│   ├── base_auth.html
│   ├── login/, auth/, perfil/
│   ├── admin/                    # usuarios.html, setores.html, auditoria.html
│   ├── gerente/
│   └── relatorios/               # 1 template por relatório
│
├── statics/
│   ├── css/                      # CSS vanilla por seção (admin, auth, financeiro, etc.)
│   └── js/                       # JS vanilla por seção
│
├── scripts/
│   └── criar_usuario.py          # Script CLI para criar usuário admin inicial
│
├── docs/
│   ├── ISSUES.md                 # Issues de CSS/frontend identificadas em Mai/2026
│   └── DESIGN_SYSTEM.md          # Tokens e guia de estilo atual
│
├── data/                         # Volume Docker (NÃO comitar — gerado em runtime)
│   ├── users.db                  # Usuários, sessões, permissões, logs de acesso
│   ├── pedidos.db                # Cache: pedidos de compra + estoque + energy pedidos
│   ├── financeiro.db             # Cache: NF, títulos, movimentos bancários
│   └── backups/                  # Backups automáticos diários dos .db
│
├── homolog/                      # Ambiente de homologação independente
│   ├── docker-compose.yml        # Porta 5005→5000
│   ├── .env
│   └── data/
│
└── mockup/                       # Protótipo React + MUI (referência futura de UI)
    ├── src/
    │   ├── App.jsx
    │   ├── theme.js              # Tema MUI customizado (paleta HBR)
    │   ├── components/           # Layout, Sidebar, Topbar, StatusChip
    │   └── pages/                # Dashboard, ContasReceber, ContasPagar,
    │                             #   MovBancarios, Energy, Placeholder
    ├── start-mockup.sh           # Inicia dev server na porta 8888
    └── package.json              # React 18, MUI v9, Vite 5
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
| `sync_status` | Estado do último sync por módulo (usado pelo scheduler) |
| `logs_email` | Histórico de e-mails enviados pelo sistema |

### 4.2 `pedidos.db` — Compras e estoque

| Tabela | Tabela Protheus origem |
|---|---|
| `pedidos` | SC7 (Pedidos de Compra) |
| `historico_pedidos` | SC7 (visão histórica sem filtro de comprador) |
| `estoque_saldos` | SB2 (Saldo em Estoque) |
| `energy_pedidos` | SC7 filtrado por compradores Energy |

### 4.3 `financeiro.db` — Financeiro

| Tabela | Tabela Protheus origem |
|---|---|
| `nf_entrada` | SD1 (Itens NF Entrada) |
| `nf_saida` | SD2 (Itens NF Saída) |
| `contas_receber` | SE1 (Títulos a Receber) |
| `contas_pagar` | SE2 (Títulos a Pagar) |
| `mov_bancarios` | SE5 (Movimentos Bancários) |
| `energy_contas_pagar` | SE2 filtrado por E2_ITEMD = '05.001' |

---

## 5. Mecanismo de sincronização (Sync)

O sync é executado **a cada hora** por um `threading.Timer` gerenciado pelo **SCHEDULER_OWNER** (primeiro worker do Gunicorn).

### Fluxo

1. `inicializar()` → chamado no `post_fork` do worker 0
2. Executa `rotina_sync()` imediatamente (carga inicial)
3. Agenda `rotina_sync()` novamente para a próxima hora cheia
4. A cada ciclo: para cada módulo, executa o `SELECT` no Protheus, faz `upsert` no SQLite local

### Janelas de lookback (quanto retroativo o sync reprocessa)

| Variável `.env` | Módulo | Padrão |
|---|---|---|
| `SYNC_LOOKBACK_PEDIDOS` | Pedidos de Compra (compras + energy) | 60 dias |
| `SYNC_LOOKBACK_HISTORICO` | Histórico de Pedidos | 30 dias |
| `SYNC_LOOKBACK_NF` | NF Entrada e NF Saída | 30 dias |
| `SYNC_LOOKBACK_MOV_BANCARIOS` | Movimentos Bancários | 30 dias |
| `SYNC_LOOKBACK_TITULOS` | Contas a Pagar, Receber, Energy C. Pagar | **365 dias** |
| `SYNC_LOOKBACK_DAYS` | Fallback global | 30 dias |

> **Por que 365 dias nos títulos?** Títulos vencidos há meses podem ser baixados a qualquer momento. Um lookback curto faria o sync ignorar essas baixas, deixando saldos desatualizados.

---

## 6. Conexão com o Protheus

**Arquivo:** `services/protheus_readonly.py`

- Driver: `ODBC Driver 17 for SQL Server`
- Modo: `ApplicationIntent=ReadOnly`, `READ UNCOMMITTED`
- `TrustServerCertificate=yes` (contorna problemas de certificado na rede interna)
- Validação de query: só aceita `SELECT`, bloqueia palavras como `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.
- Retry automático em erros transientes (rede, timeout): até `PROTHEUS_MAX_RETRIES` tentativas com backoff linear de 5s

**Timeouts:**

| Variável | Significado | Padrão |
|---|---|---|
| `PROTHEUS_CONNECT_TIMEOUT` | Tempo para estabelecer conexão TCP + login | 10s (prod: 30s) |
| `PROTHEUS_QUERY_TIMEOUT` | Tempo máximo de execução de cada SELECT | 60s |
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
- Sessão com `SESSION_LIFETIME_SECONDS` (padrão: 8h)
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
| `/relatorios/compras/historico` | Perm. | Histórico de Pedidos |
| `/relatorios/estoque/saldos` | Perm. | Saldo em Estoque |
| `/relatorios/financeiro/nf-entrada` | Perm. | NF de Entrada |
| `/relatorios/financeiro/nf-saida` | Perm. | NF de Saída |
| `/relatorios/financeiro/contas-receber` | Perm. | Contas a Receber |
| `/relatorios/financeiro/contas-pagar` | Perm. | Contas a Pagar |
| `/relatorios/financeiro/mov-bancarios` | Perm. | Movimentos Bancários |
| `/relatorios/energy/contas-pagar` | Perm. | Energy — Contas a Pagar |
| `/relatorios/energy/pedidos` | Perm. | Energy — Pedidos de Compra |

### API REST (JSON)

Cada relatório tem 4 endpoints no padrão `/api/relatorios/<modulo>/<id>/`:

| Sufixo | Método | Descrição |
|---|---|---|
| `/info` | GET | Metadados: total de registros, último sync, status |
| `/historico-sync` | GET | Últimos N syncs do módulo |
| `/sync` | POST | Dispara sync manual imediato |
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
| `/api/admin/logs` | GET | Logs de acesso paginados |
| `/api/gerente/usuarios` | GET | Usuários do setor (gerente) |
| `/health` | GET | Health check (Docker) |

### OData v4 (Power BI)

Requer header `Authorization: Bearer <api_token>`.

| Endpoint | Tabela |
|---|---|
| `/odata/pedidos` | Pedidos de Compra |
| `/odata/energy-pedidos` | Energy — Pedidos |
| `/odata/historico-pedidos` | Histórico de Pedidos |
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
SESSION_LIFETIME_SECONDS=28800
SESSION_COOKIE_SECURE=false        # true em HTTPS
TRUST_PROXY_HEADERS=false          # true se houver Nginx na frente

# Timeouts Protheus
PROTHEUS_CONNECT_TIMEOUT=10
PROTHEUS_QUERY_TIMEOUT=60
PROTHEUS_MAX_RETRIES=2

# Janelas de sync por módulo (dias retroativos)
SYNC_LOOKBACK_TITULOS=365          # Crítico — não reduzir
SYNC_LOOKBACK_PEDIDOS=60
SYNC_LOOKBACK_HISTORICO=30
SYNC_LOOKBACK_NF=30
SYNC_LOOKBACK_MOV_BANCARIOS=30

# E-mail (Gmail SMTP)
EMAIL_ENABLED=true
EMAIL_PROVIDER=gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail>
SMTP_PASSWORD=<app-password>
```

---

## 10. Docker e deploy

### Build e subida (produção)

```bash
cd /home/hbradmin/orders_consult
docker compose up -d --build
```

### Estrutura do container

- Imagem base: `python:3.11-slim`
- ODBC Driver 17 instalado via APT (Microsoft repo)
- Gunicorn: 2 workers gthread × 4 threads, bind `0.0.0.0:5000`
- Porta host: `5005` → container `5000`
- Volume: `./data:/app/data` (bancos SQLite persistentes)
- Health check: `GET /health` a cada 60s

### Gunicorn — estratégia de workers

- `SCHEDULER_OWNER` = primeiro worker forkado (`worker.age == 0`)
- Apenas ele roda `inicializar()` (carga inicial + agendamento do sync horário)
- Os demais workers só executam `garantir_schemas()` (idempotente)
- `preload_app=True` economiza RAM via copy-on-write

### Criar usuário admin inicial

```bash
docker exec -it orders_consult python scripts/criar_usuario.py
```

---

## 11. Módulos de relatório — resumo

| Chave | Módulo | Relatório | Tabela Protheus | Tabela SQLite |
|---|---|---|---|---|
| `compras.pedidos` | Compras | Pedidos de Compra | SC7 | `pedidos` |
| `compras.historico` | Compras | Histórico de Pedidos | SC7 | `historico_pedidos` |
| `estoque.saldos` | Estoque | Saldo em Estoque | SB2 | `estoque_saldos` |
| `financeiro.nf_entrada` | Financeiro | NF de Entrada | SD1 | `nf_entrada` |
| `financeiro.nf_saida` | Financeiro | NF de Saída | SD2 | `nf_saida` |
| `financeiro.contas_receber` | Financeiro | Contas a Receber | SE1 | `contas_receber` |
| `financeiro.contas_pagar` | Financeiro | Contas a Pagar | SE2 | `contas_pagar` |
| `financeiro.mov_bancarios` | Financeiro | Mov. Bancários | SE5 | `mov_bancarios` |
| `energy.contas_pagar` | Energy | Contas a Pagar | SE2 (E2_ITEMD=05.001) | `energy_contas_pagar` |
| `energy.pedidos` | Energy | Pedidos de Compra | SC7 (compradores Energy) | `energy_pedidos` |

---

## 12. Issues conhecidas (CSS/Frontend)

Levantadas em 25/05/2026. Ver `docs/ISSUES.md` para detalhes completos.

| # | Prioridade | Problema | Arquivo |
|---|---|---|---|
| C1 | Crítico | ~200 linhas de CSS inline no template de Perfil | `templates/perfil/index.html` |
| C2 | Crítico | Fonte externa Google Fonts (falha em rede interna) | `statics/css/login/login.css` |
| M1 | Moderado | Sem variáveis CSS — valores hardcoded em 6 arquivos | `statics/css/**` |
| M2 | Moderado | Classe `.kicker` com 3 nomes diferentes | `consulta.css`, `admin.css`, `home.css` |
| M3 | Moderado | Breakpoints inconsistentes entre arquivos | vários |
| L1 | Baixo | `@keyframes fadeIn` declarado 3 vezes | vários |
| L2 | Baixo | `max-width` de conteúdo inconsistente (930px vs 980px) | vários |
| L3 | Baixo | `border-radius:0` por componente em vez de no reset | vários |

---

## 13. Mockup de redesign (referência futura)

Pasta `mockup/` contém um protótipo completo em **React 18 + Material UI v9**
que representa a direção visual futura do sistema.

**Como iniciar:**

```bash
cd mockup
./start-mockup.sh        # porta 8888
# ou o mockup estático (HTML puro, sem build):
python3 -m http.server 8888 --bind 0.0.0.0
# acesso: http://10.0.253.100:8888/mockup_reformulacao.html
```

**Seções implementadas no mockup React:**
- Dashboard com KPIs, gráfico de barras e donut
- Contas a Receber (tabela + filtros + paginação)
- Contas a Pagar (com alertas de vencimento)
- Movimentos Bancários (timeline agrupada por data)
- Energy — Contas a Pagar (hero escuro + tabela + barras de progresso)
- Placeholders: Pedidos, NF, Estoque, Admin

---

## 14. Convenções de código

### Python (`app.py` e `services/`)

- Funções utilitárias antes das rotas no `app.py`
- Decorators de proteção: `@login_requerido`, `@admin_requerido`, `@gerente_requerido`, `@acesso_relatorio_requerido(modulo_id, relatorio_id)`
- Todos os retornos de API usam `jsonify({})` com campo `ok: bool`
- Queries SQL no Protheus ficam nos arquivos dentro de `services/relatorios/`
- **Nunca** executar INSERT/UPDATE/DELETE no Protheus — a função `validar_query_somente_leitura()` bloqueia automaticamente

### Templates Jinja2

- Herdam de `templates/base_auth.html`
- Bloco `{% block conteudo %}` para o conteúdo de cada página
- Bloco `{% block scripts %}` para JS específico da página

### CSS/JS vanilla (estado atual)

- CSS por seção em `statics/css/<seção>/`
- JS por seção em `statics/js/<seção>/`
- Sem bundler; arquivos referenciados diretamente nos templates

---

## 15. Arquivos que NÃO devem ser modificados sem cuidado

| Arquivo | Risco |
|---|---|
| `services/protheus_readonly.py` | Qualquer mudança pode afetar TODOS os syncs |
| `services/database.py` — funções de schema | Mudança em schema exige migração do SQLite existente |
| `config/gunicorn_conf.py` | Erros aqui impedem o boot do container |
| `.env` | Contém credenciais de produção |
| `data/*.db` | Bancos de produção — nunca editar manualmente |

---

## 16. Comandos úteis

```bash
# Ver logs em tempo real
docker logs -f orders_consult

# Entrar no container
docker exec -it orders_consult bash

# Reiniciar sem rebuild
docker compose restart

# Rebuild completo
docker compose up -d --build

# Verificar saúde
curl http://localhost:5005/health

# Testar sync manual via API (requer cookie de sessão admin)
curl -X POST http://localhost:5005/api/relatorios/financeiro/contas-receber/sync \
  -H "Cookie: session=..." \
  -H "X-CSRF-Token: ..."

# Ver bancos SQLite
sqlite3 data/financeiro.db ".tables"
sqlite3 data/users.db "SELECT login, perfil, ativo FROM usuarios;"
```
