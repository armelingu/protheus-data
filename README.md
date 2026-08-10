# ProtheusData

Portal web interno para consulta e exportação de dados do ERP Protheus (TOTVS). Replica tabelas do SQL Server em caches SQLite locais e os expõe via interface web, API RESTful e endpoint OData v4 (compatível com Power BI).

---

## Visao geral

O sistema lê o banco Protheus em **modo somente leitura** (`READ UNCOMMITTED`, `ApplicationIntent=ReadOnly`), copia os dados para SQLite e serve as consultas a partir do cache local — isolando o ERP de queries pesadas.

**Componentes:**
- `web` — Flask + Gunicorn, serve a interface e a API
- `etl` — Worker Python independente, responsável por todo agendamento de sync

---

## Stack tecnica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11 |
| Framework web | Flask 3.1 + Gunicorn 25 (gthread) |
| Banco cache local | SQLite 3 (WAL mode, 3 arquivos) |
| Banco fonte (ERP) | Microsoft SQL Server 2019 (Protheus P12) |
| Driver SQL Server | ODBC Driver 17 for SQL Server (pyodbc 5.3) |
| E-mail | Microsoft Graph API (OAuth2 client_credentials) |
| Exportacao | openpyxl 3.1 (XLSX) |
| Compressao HTTP | Flask-Compress |
| Container | Docker + Docker Compose (2 servicos: `web` + `etl`) |
| Frontend | Jinja2 + CSS/JS vanilla |

---

## Estrutura de diretorios

```
protheusdata/
├── app.py                        # Aplicacao Flask principal
├── requirements.txt
├── Dockerfile
├── docker-compose.yml            # Servicos: web (porta 5005) + etl
├── .env                          # Variaveis de ambiente (nao comitar)
├── .env.example                  # Template documentado
│
├── config/
│   └── gunicorn_conf.py
│
├── etl/
│   └── worker.py                 # Agendador: full refresh 02:00 + sync horario 08-18h
│
├── services/
│   ├── database.py               # Conexoes SQLite, schemas, backup, WAL
│   ├── protheus_readonly.py      # Conexao pyodbc ao SQL Server com retry
│   ├── sync_engine.py            # Full refresh baseado em hash MD5
│   ├── catalogo_relatorios.py    # Catalogo de modulos e permissoes
│   ├── email_service.py          # Envio via Microsoft Graph API
│   └── relatorios/
│       ├── compras/
│       ├── estoque/
│       ├── financeiro/
│       └── energy/
│
├── templates/                    # Jinja2 (herdam de base_auth.html)
├── statics/                      # CSS e JS vanilla por secao
├── scripts/
│   └── criar_usuario.py          # CLI para criar o usuario admin inicial
└── data/                         # Volume Docker — gerado em runtime, nao comitar
    ├── users.db
    ├── pedidos.db
    ├── financeiro.db
    └── backups/
```

---

## Bancos de dados SQLite

O sistema usa 3 arquivos SQLite em `data/`, todos com WAL mode e os seguintes PRAGMAs:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-65536;    -- 64 MB por conexao
PRAGMA mmap_size=268435456;  -- 256 MB mmap
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
```

### users.db — Usuarios e controle de acesso

| Tabela | Descricao |
|---|---|
| `usuarios` | Login, nome, email, senha_hash, perfil, setor, ativo |
| `setores` | Grupos de usuarios |
| `permissoes_usuario` | Permissao individual por relatorio |
| `permissoes_setor` | Permissao por setor |
| `api_tokens` | Tokens Bearer para OData (Power BI) |
| `logs_acesso` | Auditoria de login/logout |
| `auditoria_admin` | Acoes administrativas |
| `rate_limit` | IPs com tentativas suspeitas |
| `logs_email` | Historico de e-mails enviados |

### pedidos.db — Compras, Estoque e Energy

| Tabela | Tabela Protheus | Estrategia sync |
|---|---|---|
| `pedidos` | SC7 | Hash MD5 |
| `pedidos_detalhado` | SC7 + CTT/CTD/CT1/SE4 | Hash MD5 |
| `pedidos_historico` | SC7 (visao historica) | Hash MD5 |
| `pendencia_aprovacao` | SC7 + SCR | Hash MD5 |
| `pedidos_energy` | SC7 filtrado por comprador + item | Hash MD5 |
| `pedidos_conta_05001` | SC7 filtrado por item contabil | Hash MD5 |
| `estoque_saldos` | SB2 | Hash MD5 |
| `_etl_hash_cache` | — | Cache interno de hashes |

### financeiro.db — Financeiro e Energy

| Tabela | Tabela Protheus | Estrategia sync |
|---|---|---|
| `nf_entrada_itens` | SD1 | Keyset pagination (R_E_C_N_O_) |
| `nf_saida_itens` | SD2 | Keyset pagination |
| `contas_receber` | SE1 | Keyset pagination |
| `contas_pagar` | SE2 | Keyset pagination |
| `mov_bancarios` | SE5 | Keyset pagination |
| `energy_contas_pagar` | SE2 filtrado por item | Keyset pagination |
| `energy_contas_receber` | SE1 filtrado por item | Keyset pagination |

---

## Arquitetura ETL

O container `etl` roda um processo Python independente (`etl/worker.py`) com agendamento proprio.

### Agendamento

| Horario | Operacao |
|---|---|
| Diario 02:00 | Full refresh de todas as tabelas |
| Horario (08-18h) | Sync incremental por janela de datas |

### Estrategias de sync

**Hash MD5 (tabelas de compras/estoque):**
1. Busca todos os registros do Protheus
2. Calcula MD5 de cada linha normalizada
3. Compara com cache local (`_etl_hash_cache`)
4. Faz UPSERT apenas nas linhas alteradas
5. Deleta registros que sumiram do Protheus

**Keyset pagination (tabelas financeiras):**
1. Pagina via `R_E_C_N_O_ > cursor` em batches de 5.000 registros
2. Full refresh: limpa tabela + cursor, recarrega tudo
3. Sync incremental: janela de datas (lookback configuravel)

### Alertas de e-mail

Ao final de cada full refresh o worker envia e-mail com:
- Status (sucesso ou falha)
- Numero de mutacoes por tabela
- Duracao total da operacao

---

## Modulos de relatorio

| Modulo | Relatorio | Tabela Protheus |
|---|---|---|
| Compras | Pedidos de Compra | SC7 |
| Compras | Pedidos de Compra Detalhado | SC7 + CTT/CTD/CT1/SE4 |
| Compras | Historico de Pedidos | SC7 |
| Compras | Pendencia de Aprovacao | SC7 + SCR |
| Estoque | Saldo em Estoque | SB2 |
| Financeiro | NF de Entrada | SD1 |
| Financeiro | NF de Saida | SD2 |
| Financeiro | Contas a Receber | SE1 |
| Financeiro | Contas a Pagar | SE2 |
| Financeiro | Movimentos Bancarios | SE5 |
| Energy | Pedidos de Compra | SC7 |
| Energy | Pedidos — Conta 05.001 | SC7 |
| Energy | Contas a Pagar | SE2 |
| Energy | Contas a Receber | SE1 |

---

## Rotas HTTP principais

### Paginas

| Rota | Descricao |
|---|---|
| `GET /login` | Pagina de login |
| `GET /relatorios` | Pagina inicial (catalogo de relatorios) |
| `GET /relatorios/<modulo>/<slug>` | Pagina de cada relatorio |
| `GET /admin/usuarios` | Gestao de usuarios (admin) |
| `GET /admin/setores` | Gestao de setores (admin) |
| `GET /admin/auditoria` | Log de auditoria (admin) |

### API de relatorio (padrao por modulo)

| Rota | Descricao |
|---|---|
| `GET /api/relatorios/<modulo>/<slug>/info` | Contagem e data do ultimo sync |
| `GET /api/relatorios/<modulo>/<slug>/historico-sync` | Historico de execucoes |
| `POST /api/relatorios/<modulo>/<slug>/sync` | Dispara sync incremental |
| `GET /api/relatorios/<modulo>/<slug>/download?formato=csv\|excel` | Download |

### Admin

| Rota | Descricao |
|---|---|
| `POST /api/admin/full-refresh` | Dispara full refresh manual |

### OData v4 (Power BI)

| Rota | Descricao |
|---|---|
| `GET /odata/$metadata` | Documento de metadados |
| `GET /odata/<entity>` | Dados paginados com suporte a $filter, $top, $skip |

---

## Variaveis de ambiente

Copie `.env.example` para `.env` e preencha antes de subir os containers.

### Banco de dados Protheus (SQL Server)

| Variavel | Descricao |
|---|---|
| `DB_SERVER` | Endereco IP ou hostname do SQL Server |
| `DB_DATABASE` | Nome do banco (ex: `P12_PRD`) |
| `DB_USERNAME` | Usuario SQL Server |
| `DB_PASSWORD` | Senha SQL Server |

### Flask

| Variavel | Descricao |
|---|---|
| `SECRET_KEY` | Chave secreta Flask (gere com `python3 -c "import secrets; print(secrets.token_hex(32))"`) |

### E-mail — Microsoft Graph API

| Variavel | Descricao |
|---|---|
| `EMAIL_ENABLED` | `true` para habilitar envio |
| `EMAIL_PROVIDER` | `msgraph` |
| `EMAIL_FROM` | Endereco remetente |
| `MS_TENANT_ID` | ID do tenant no Azure AD |
| `MS_CLIENT_ID` | ID do aplicativo registrado |
| `MS_CLIENT_SECRET` | Segredo do aplicativo |

### ETL

| Variavel | Descricao | Padrao |
|---|---|---|
| `ETL_FULL_REFRESH_HORA` | Hora do full refresh diario (0-23) | `2` |
| `ETL_ALERT_EMAILS` | Destinatarios de alerta (separados por virgula) | — |

### Janelas de sync incremental

| Variavel | Descricao | Padrao |
|---|---|---|
| `SYNC_LOOKBACK_DAYS` | Lookback padrao (dias) | `30` |
| `SYNC_LOOKBACK_PEDIDOS` | Lookback para pedidos de compra | `60` |
| `SYNC_LOOKBACK_NF` | Lookback para NF entrada/saida | `30` |
| `SYNC_LOOKBACK_TITULOS` | Lookback para titulos (SE1/SE2) | `365` |
| `SYNC_LOOKBACK_MOV_BANCARIOS` | Lookback para movimentos bancarios | `30` |

---

## Docker e deploy

### Subir em producao

```bash
cp .env.example .env
# edite .env com as credenciais reais
docker compose up -d
```

### Rebuild completo

```bash
docker compose build --no-cache && docker compose up -d --force-recreate
```

### Ver logs

```bash
docker logs orders_consult         # web
docker logs orders_consult_etl     # etl
```

### Criar usuario admin inicial

```bash
docker exec -it orders_consult python3 scripts/criar_usuario.py
```

### Disparar full refresh manual

```bash
curl -X POST http://localhost:5005/api/admin/full-refresh \
  -H "Content-Type: application/json" \
  -b "session=<cookie>" \
  -d '{"relatorio": "todos"}'
```

---

## Desenvolvimento

### Workflow de branches (Gitflow)

```
main      — producao estavel
develop   — integracao de features

feature/* — nova funcionalidade (sai de develop, volta para develop)
release/* — preparacao de versao (sai de develop, mergeia em main + develop)
hotfix/*  — correcao urgente (sai de main, mergeia em main + develop)
```

### Iniciar nova feature

```bash
git checkout develop
git checkout -b feature/nome-da-feature
# ... desenvolve e commita ...
git checkout develop
git merge feature/nome-da-feature
git push origin develop
```

### Convencoes de commit

```
feat:     nova funcionalidade
fix:      correcao de bug
docs:     alteracao em documentacao
refactor: refatoracao sem mudanca de comportamento
chore:    tarefas de manutencao (deps, config, ci)
```

---

## Requisitos do servidor

- Docker 24+ e Docker Compose v2
- ODBC Driver 17 for SQL Server instalado na imagem (via Dockerfile)
- Acesso de rede ao SQL Server Protheus (porta 1433)
- Porta 5005 disponivel para o container web

---

## Licenca

Uso interno. Todos os direitos reservados.
