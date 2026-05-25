# Design System — ProtheusData

> Documento gerado em 25/05/2026. Auditoria completa de tokens, componentes e padrões do sistema.

---

## Sumário

1. [Princípios](#1-princípios)
2. [Tokens de Design](#2-tokens-de-design)
3. [Tipografia](#3-tipografia)
4. [Componentes](#4-componentes)
5. [Padrões de Layout](#5-padrões-de-layout)
6. [Padrões de Página](#6-padrões-de-página)
7. [Acessibilidade](#7-acessibilidade)
8. [Issues e Inconsistências](#8-issues-e-inconsistências)

---

## 1. Princípios

| # | Princípio | Descrição |
|---|-----------|-----------|
| 1 | **Flat first** | Cantos retos (`border-radius: 0`) em todos os componentes. A única exceção permitida é o spinner de loading (precisa ser circular). |
| 2 | **Monocromático** | A paleta é quase inteiramente escala de cinza. Cor aparece apenas para status semântico (verde=ok, vermelho=erro, âmbar=aviso). |
| 3 | **Tipografia como hierarquia** | A hierarquia visual é comunicada por tamanho, peso e letter-spacing — não por cor ou ornamento. |
| 4 | **Espaço como separador** | Divisórias usam `border: 1px solid #efefef` e `gap` via flexbox/grid. Sombras são mínimas e só na camada de login. |
| 5 | **Animações discretas** | `fadeIn 0.35s ease` para entrada de painéis. Transições de estado em `0.15–0.2s ease`. `prefers-reduced-motion` respeitado. |

---

## 2. Tokens de Design

### 2.1 Cores

#### Base

| Token | Valor | Uso |
|-------|-------|-----|
| `color-ink` | `#1a1a1a` | Texto primário, botões primários, accent |
| `color-ink-soft` | `#3a3a3a` | Texto de código/pre |
| `color-ink-mid` | `#5a5a5a` | Texto de dados em tabela |
| `color-ink-light` | `#6a6a6a` | Texto secundário, labels de menu |
| `color-ink-muted` | `#7b7b7b` | Tabs inativas, nav desabilitada |
| `color-ink-subtle` | `#8a8a8a` | Subtítulos, meta-texto |
| `color-ink-faint` | `#adadad` | Kicker labels, texto auxiliar |
| `color-ink-ghost` | `#b8b8b8` | Scrollbar, prefixo de accordions |
| `color-surface` | `#ffffff` | Background de painéis e cards |
| `color-surface-body` | `#f6f6f6` | Background do body autenticado |
| `color-surface-login` | `#f8f8f8 → #f2f2f2` | Gradient de fundo do login |
| `color-border` | `#e7e7e7` | Border de painéis (externa) |
| `color-border-inner` | `#efefef` | Border divisória interna |
| `color-border-faint` | `#f0f0f0` | Separadores de lista |

#### Status Semântico

| Token | Valor (texto) | Valor (borda) | Valor (fundo) | Uso |
|-------|---------------|---------------|---------------|-----|
| `status-ok` | `#2a7a2a` | `#c3e0cb` | `#f2faf4` | Sucesso, ativo, ok |
| `status-ok-strong` | `#2f8a2f` | `#b6ddb6` | `#f4fbf4` | Toast de sucesso |
| `status-ok-deep` | `#2a6b3a` | — | — | Badge "ok" em admin |
| `status-erro` | `#c0392b` | — | — | Status de erro inline |
| `status-erro-toast` | `#b32b2b` | `#f0b8b8` | `#fdf4f4` | Toast de erro |
| `status-erro-badge` | `#6b3333` | `#e1cece` | `#fdf2f2` | Badge "danger" em admin |
| `status-aviso` | `#c07a00` | — | — | Status de aviso inline |
| `status-aviso-badge` | `#7a5510` | `#e4cfa0` | `#fdf8ed` | Badge "warn" em admin |
| `status-processando` | `#4a6abf` | `#c0c8d8` | `#f4f6fb` | Toast de processamento |
| `status-neutro` | `#1a1a1a` | `#d0d0d0` | — | Badge "strong" neutro |

#### Badges de Auditoria

| Categoria | Texto | Fundo |
|-----------|-------|-------|
| `criacao` | `#2d7d46` | `#e6f4ea` |
| `edicao` | `#1a5cb8` | `#e8f0fe` |
| `remocao` | `#c5221f` | `#fce8e6` |
| `seguranca` | `#b06000` | `#fff4e0` |
| `email` | `#6633cc` | `#f0eaff` |
| `erro` | `#c5221f` | `#fce8e6` |
| `aviso` | `#9a6e00` | `#fff8e1` |
| `acesso` | `#1b5e20` | `#e8f5e9` |
| `download` | `#0d47a1` | `#e3f2fd` |
| `sync` | `#880e4f` | `#fce4ec` |
| `outro` | `#555555` | `#f1f1f1` |

### 2.2 Tipografia

| Token | Valor | Uso |
|-------|-------|-----|
| `font-family-base` | `'Segoe UI', Arial, Helvetica, sans-serif` | Todo o sistema |
| `font-family-display` | `'Sora', 'Segoe UI', Arial, sans-serif` | H1 da página de login |
| `font-family-mono` | `'Consolas', 'Courier New', monospace` | Preview de SQL, código |
| `font-size-kicker` | `9px` | Labels kicker (uppercase) |
| `font-size-nav` | `11px` | Links de menu, tabs, labels |
| `font-size-body` | `12px` | Texto corrido, subtítulos, inputs |
| `font-size-ui` | `13px` | Toast, campos de formulário |
| `font-size-h2` | `17px` | Títulos de painéis secundários |
| `font-size-h1` | `24px` | Títulos principais de painel |
| `font-size-brand` | `28px` | H1 da tela de login |
| `font-weight-normal` | `500` | Texto de interface padrão |
| `font-weight-semi` | `600` | Títulos, kickers, botões |
| `font-weight-bold` | `700` | Login brand, kicker de login |
| `letter-spacing-kicker` | `1.1px` | Kickers (uppercase micro-text) |
| `letter-spacing-heading` | `-0.7px` | H1 e H2 (tight heading) |
| `letter-spacing-nav` | `0.2–0.7px` | Tabs e nav links |
| `line-height-body` | `1.7` | Subtítulos e textos corridos |
| `line-height-tight` | `1.12` | Títulos H1 |

### 2.3 Espaçamento

| Token | Valor | Uso típico |
|-------|-------|------------|
| `space-2` | `2px` | Ajustes finos |
| `space-4` | `4px` | Gap de marca/legenda |
| `space-6` | `6px` | Gap de radio, subtítulo h1 |
| `space-8` | `8px` | Padding de botão (vertical), gap de toast, margin kicker |
| `space-10` | `10px` | Padding de summary/accordion |
| `space-12` | `12px` | Gap de menu home, margin kicker login |
| `space-14` | `14px` | Gap entre radio options, padding query, gap admin shell |
| `space-16` | `16px` | Padding botão (horizontal), padding módulo dashboard |
| `space-18` | `18px` | Padding top/bottom do app-shell, gap de grid de módulos |
| `space-22` | `22px` | Gap do app-shell, top do menu sticky |
| `space-24` | `24px` | Margin-bottom painel-topo, gap painel |
| `space-26` | `26px` | Padding bottom de painel |
| `space-28` | `28px` | Posição do toast (bottom/right) |
| `space-30` | `30px` | Padding principal de painel |
| `space-32` | `32px` | Padding horizontal do login |
| `space-34` | `34px` | Padding top do login |

### 2.4 Bordas

| Token | Valor | Uso |
|-------|-------|-----|
| `border-radius` | `0` | Padrão em todo o sistema (flat) |
| `border-radius-spinner` | `50%` | Única exceção — spinner circular |
| `border-width` | `1px` | Todas as bordas |
| `border-color-panel` | `#e7e7e7` | Borda externa de painéis |
| `border-color-inner` | `#efefef` | Divisórias internas |
| `border-color-faint` | `#f0f0f0` | Separadores de lista |
| `border-color-input` | `#ddd` | Campos de formulário |
| `border-color-input-btn` | `#e2e2e2` | Botão secundário |

### 2.5 Sombras

| Token | Valor | Uso |
|-------|-------|-----|
| `shadow-login` | `0 14px 36px rgba(0,0,0,0.04)` | Caixa de login |
| `shadow-toast` | `0 2px 12px rgba(0,0,0,0.08)` | Notificações toast |
| `shadow-input-focus` | `0 0 0 3px rgba(0,0,0,0.06)` | Focus ring em inputs |

### 2.6 Animações e Transições

| Token | Valor | Uso |
|-------|-------|-----|
| `animation-enter` | `fadeIn 0.35s ease` | Entrada de painéis e shells |
| `animation-enter-login` | `fadeIn 0.4s ease` | Entrada do card de login |
| `transition-color` | `color 0.2s ease` | Links de menu, tabs |
| `transition-bg` | `background 0.15s ease` | Summary/accordion hover |
| `transition-state` | `opacity 0.22s ease, transform 0.22s ease` | Toast aparecer/sumir |
| `transition-page` | `opacity 0.14s ease, filter 0.14s ease, transform 0.14s ease` | Transição entre páginas |
| `animation-spin` | `0.9s linear infinite` | Spinner de processamento |
| `duration-spin-btn` | `0.8s linear infinite` | Spinner de botão de login |

### 2.7 Breakpoints

| Breakpoint | Valor | Contexto |
|------------|-------|----------|
| `bp-tablet-lg` | `1080px` | Layout principal — colapsa sidebar |
| `bp-tablet` | `920px` | Layout e admin — ajustes de painel |
| `bp-tablet-sm` | `860px` | Admin — stack vertical |
| `bp-mobile-lg` | `760px` | Dashboard — single column |
| `bp-mobile` | `640px` | Geral — mobile otimization |
| `bp-mobile-sm` | `480px` | Admin — ajustes finais |

---

## 3. Tipografia

### Escala de Títulos

```
Kicker     9px / 600 / uppercase / ls:1.1px / #adadad
Nav/Tab   11px / 600 / uppercase / ls:0.7px / #7b7b7b
Body      12px / 500            / lh:1.7   / #8a8a8a
UI        13px / 500            / lh:1.45  / #2a2a2a
H2        17px / 600            / ls:-0.7px
H1        24px / 600            / ls:-0.7px / lh:1.12
Brand     28px / 600–700 (Sora) / ls:-0.5px
```

### Padrão Kicker + Título + Subtítulo

Usado em todo painel de relatório, admin e dashboard:

```html
<p class="painel-kicker">Módulo · Relatório</p>
<h1>Nome do Relatório</h1>
<p class="subtitulo">Descrição breve com orientação de uso.</p>
```

---

## 4. Componentes

### 4.1 Button

Três variantes. Todos com `border-radius: 0`, `font-weight: 600`, `font-size: 12px`.

| Variante | Background | Cor | Borda | Hover |
|----------|------------|-----|-------|-------|
| **Primário** | `#1a1a1a` | `#ffffff` | `1px solid #1a1a1a` | bg `#2d2d2d` |
| **Secundário** | `#ffffff` | `#555555` | `1px solid #e2e2e2` | cor `#1a1a1a`, borda `#c8c8c8` |
| **Danger** | `#ffffff` | `#8b3333` | `1px solid #e8d0d0` | bg `#fff5f5`, borda `#d4a0a0` |

**Estados:**
- `disabled`: `opacity: 0.48`, `cursor: not-allowed`
- `focus-visible`: `outline: 2px solid #1a1a1a`, `outline-offset: 2px`

**Padding:** `8px 16px`

**Classes:** `.admin-btn-primario`, `.admin-btn-secundario`, `.admin-btn-danger`  
Em relatórios: `.painel button` (primário), `.btn-secundario`

---

### 4.2 Input / Campo de Formulário

```css
font-size: 12–13px
border: 1px solid #ddd
background: #fff
padding: 7–9px 10–12px
color: #1a1a1a
border-radius: 0
transition: border-color 0.15s ease, box-shadow 0.15s ease
```

**Focus:**
```css
border-color: #aaaaaa
box-shadow: 0 0 0 3px rgba(0,0,0,0.06)
outline: none
```

**Padrão de campo com label:**
```html
<div class="admin-field">
  <label class="admin-field-label" for="id">Label</label>
  <input id="id" type="text" …>
  <p class="admin-field-hint">Texto auxiliar opcional.</p>
</div>
```

---

### 4.3 Toggle (Switch)

Usado para flags booleanas em formulários de usuário (`is_admin`, `is_gerente`, `pode_ver_query`).

**Estrutura:**
```html
<label class="admin-toggle">
  <input type="checkbox" id="is_admin">
  <span class="admin-toggle-track">
    <span class="admin-toggle-thumb"></span>
  </span>
  <span class="admin-toggle-label">Administrador</span>
</label>
```

**Visual:** track cinza → verde quando checked; thumb desliza com `transition: left 0.15s ease`.

---

### 4.4 Badge / Tag

Usado para status de usuário, tipo de evento de auditoria, e módulos ativos.

**Variantes de status (admin):**

| Classe | Uso |
|--------|-----|
| `.admin-badge.is-ok` | Ativo, habilitado |
| `.admin-badge.is-warn` | Atenção, pendente |
| `.admin-badge.is-danger` | Inativo, bloqueado |
| `.admin-badge.is-strong` | Neutro destacado |

**Variantes de auditoria (`.audit-badge--{tipo}`):**  
`criacao`, `edicao`, `remocao`, `seguranca`, `email`, `erro`, `aviso`, `acesso`, `download`, `sync`, `outro`

**Visual base:**
```css
display: inline-flex;
align-items: center;
padding: 2px 7px;
border: 1px solid;
font-size: 10px;
font-weight: 600;
letter-spacing: 0.3px;
text-transform: uppercase;
border-radius: 0;
```

---

### 4.5 Toast / Notificação

Posicionado fixo no canto inferior direito (`bottom: 28px; right: 28px`). Animação de entrada via `opacity` + `translateY`.

| Variante | Borda esquerda | Fundo | Texto | Ícone |
|----------|----------------|-------|-------|-------|
| **Sucesso** | `#2f8a2f` | `#f4fbf4` | `#1e5c1e` | `✓` |
| **Erro** | `#b32b2b` | `#fdf4f4` | `#8a1a1a` | `✕` |
| **Processando** | `#4a6abf` | `#f4f6fb` | `#2a3a5a` | spinner CSS |
| **Neutro** | `#888` | `#ffffff` | `#2a2a2a` | — |

**Classe base:** `.mensagem`  
**Ativas:** `.mensagem.visivel`  
**Tipos:** `.mensagem.sucesso`, `.mensagem.erro`, `.mensagem.processando`

**Estrutura HTML:**
```html
<div class="toast-area">
  <div id="msg-sucesso" class="mensagem sucesso" role="status" aria-live="polite">
    Operação concluída com sucesso.
  </div>
</div>
```

---

### 4.6 Tabs de Navegação

Usada no painel admin (Usuários / Setores / Auditoria).

```css
.admin-tab {
  min-height: 46px;
  font-size: 11px; font-weight: 600;
  letter-spacing: 0.7px; text-transform: uppercase;
  color: #7b7b7b;
  transition: color 0.2s ease;
}
.admin-tab.ativo {
  color: #1a1a1a;
  /* linha inferior via ::after: 2px solid #1a1a1a */
}
```

---

### 4.7 Accordion / Detalhes (Details + Summary)

Usado para "Ver SQL da query" e "Histórico de sync".

```html
<details class="query-details">
  <summary>Ver detalhes da query</summary>
  <div class="details-content">
    <div class="details-content-inner">
      <pre>SELECT …</pre>
    </div>
  </div>
</details>
```

**Prefixo visual:** `+ ` quando fechado, `– ` quando aberto — via `::before` no `summary`.

---

### 4.8 Info Box (Painel de Metadados)

Exibe métricas de sincronização: registros, última atualização, próximo sync, status.

```html
<div class="info-grid">
  <div class="info-item">
    <span class="info-label">Registros</span>
    <span class="info-valor" id="info-registros">—</span>
  </div>
  <div class="info-item">
    <span class="info-label">Status</span>
    <span class="info-valor status-sync ok" id="info-status">Atualizado</span>
  </div>
</div>
```

**Status colors (`.status-sync.{estado}`):**
- `.ok` → `#2a7a2a`
- `.erro` → `#c0392b`
- `.aviso` → `#c07a00`
- Default → `#8a8a8a`

---

### 4.9 Histórico de Sync

Lista de execuções com status visual por item.

| Ícone | Classe CSS | Significado |
|-------|------------|-------------|
| `✓` | `.historico-item.ok` | Sincronização com registros novos |
| `–` | `.historico-item.neutro` | Sem novos registros |
| `✗` | `.historico-item.erro` | Erro na sincronização |

**Paginação:** botão "Ver mais" com offset incremental.

---

### 4.10 Tabela de Dados (Grid de usuários / auditoria)

```css
display: grid;
grid-template-columns: [definido por contexto];
border: 1px solid #e7e7e7;
```

- **Header:** `font-size: 10px`, uppercase, `letter-spacing: 0.5px`, `color: #888`, `border-bottom: 2px solid #ebebeb`
- **Rows:** `border-bottom: 1px solid #f2f2f2`, hover `background: #fafafa`
- **Cells:** `font-size: 12px`, `color: #3a3a3a`

---

### 4.11 Scrollbar Customizada

```css
html { scrollbar-width: thin; scrollbar-color: #b8b8b8 #f1f1f1; }
::-webkit-scrollbar { width: 12px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #b8b8b8; border: 3px solid #f1f1f1; }
::-webkit-scrollbar-thumb:hover { background: #969696; }
```

---

## 5. Padrões de Layout

### 5.1 App Shell (Autenticado)

```
┌──────────────────────────────────────────────┐
│ app-shell  (max-width: 1280px, grid)         │
│ ┌────────────┐  ┌───────────────────────────┐│
│ │menu-flutuante│ │ page-shell (slot dinâmico)││
│ │ 236px sticky│ │                           ││
│ └────────────┘  └───────────────────────────┘│
└──────────────────────────────────────────────┘
```

```css
.app-shell {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 22px;
  padding: 18px;
}
```

**Colapso responsivo:**
- `@1080px`: sidebar colapsa, layout em coluna
- `@920px`: menu passa para topo

---

### 5.2 Menu Lateral

```
ProtheusData           ← .menu-marca (16px/600/-0.4px)
CENTRAL DE RELATÓRIOS  ← .menu-legenda (9px/uppercase/ls:1.1px/#aaa)
───────────────────────
Visão Geral            ← .menu-home
───────────────────────
FINANCEIRO             ← .menu-modulo-label (9px/uppercase)
  Contas a Pagar       ← .menu-link (11px/500)
  Contas a Receber
  …
───────────────────────
COMPRAS / ESTOQUE / …  ← outros módulos
───────────────────────
[Gerência]             ← condicional: is_gerente
[Administração]        ← condicional: is_admin
Meu Perfil & Power BI
───────────────────────
Sair                   ← .menu-logout
HBR Aviação            ← .menu-rodape (9px/#b8b8b8)
```

---

### 5.3 Painel de Relatório

```
┌─────────────────────────────────────────────────────┐
│ .painel (max-width: 930px, border: #e7e7e7)         │
│ ┌──────────────────────────────────────────────────┐│
│ │ .painel-topo                                     ││
│ │ ┌──────────────────┐ ┌────────────────────────┐  ││
│ │ │.painel-cabecalho │ │.painel-controles       │  ││
│ │ │  kicker          │ │  filtro de datas       │  ││
│ │ │  h1              │ │  formato (CSV/Excel)   │  ││
│ │ │  subtitulo       │ │  [Baixar] [Atualizar]  │  ││
│ │ └──────────────────┘ └────────────────────────┘  ││
│ └──────────────────────────────────────────────────┘│
│ .info-grid (registros, atualização, próx. sync)     │
│ .query-details (accordion — só superadmin)          │
│ .historico-sync (accordion — últimas execuções)     │
└─────────────────────────────────────────────────────┘
```

---

### 5.4 Admin Shell

```
┌──────────────────────────────────────────────────┐
│ .admin-shell (max-width: 980px)                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ .admin-header                                │ │
│ │   kicker + h1 + subtitulo + tabs            │ │
│ └──────────────────────────────────────────────┘ │
│ ┌──────────────────┐ ┌────────────────────────┐  │
│ │ .admin-panel     │ │ .admin-panel           │  │
│ │ (criar/editar)   │ │ (lista/tabela)         │  │
│ └──────────────────┘ └────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 6. Padrões de Página

### 6.1 Login

- Fonte display: `Sora` (Google Fonts), apenas nesta página
- Container centrado: `max-width: 420px`
- Card com `box-shadow: 0 14px 36px rgba(0,0,0,0.04)` — única sombra elevada no sistema
- Border-top decorativa via `::before` com gradient branco

### 6.2 Primeiro Acesso

- Container simples com gradient de fundo
- Sem sidebar; layout autônomo
- `fadeIn 0.35s ease`

### 6.3 Acesso Negado

- Herda `base_auth.html` (com sidebar)
- Painel simples: kicker + título + mensagem + instrução

### 6.4 Perfil / Power BI

- CSS inline encapsulado (não compartilhado com o sistema)
- Seções: informações da conta, tokens OData, instruções Power BI/Excel
- Tags `GET` como badges de endpoint

### 6.5 Dashboard (Home)

```
Dashboard          ← kicker + h1 + subtitulo
─────────────────
FINANCEIRO         ← .dashboard-modulo-label
  Contas a Pagar → ← cards lado a lado (2 colunas)
  Contas a Receber
─────────────────
COMPRAS            ← próximo módulo
  …
```

Grid de módulos: `2 colunas` em desktop → `1 coluna` em `@760px`.

---

## 7. Acessibilidade

| Recurso | Implementação |
|---------|---------------|
| `focus-visible` | Outline `2px solid #1a1a1a` com `outline-offset: 2px` em botões e links |
| `aria-live="polite"` | Mensagens de erro em formulários de login e primeiro acesso |
| `role="status"` | Toast de notificações |
| `prefers-reduced-motion` | Desativa `fadeIn`, `blur` e `transform` em transições de página e spinner |
| `user-select: none` | Labels de radio e summary/accordion |
| Sem `outline: none` isolado | Focus ring sempre preservado para navegação por teclado |
| `autocomplete` correto | Login: `username` + `current-password`; primeiro acesso: `current-password` + `new-password` |

---

## 8. Issues e Inconsistências

### Crítico

| # | Issue | Localização | Recomendação |
|---|-------|-------------|--------------|
| C1 | CSS inline extenso em `perfil/index.html` (~200 linhas) não compartilha tokens com o sistema | `templates/perfil/index.html` | Extrair para `statics/css/perfil/perfil.css` |
| C2 | Fonte `Sora` carregada via Google Fonts apenas no login — dependência externa de rede | `login/login.css` | Hospedar localmente ou usar `Segoe UI` com ajuste de peso |

### Moderado

| # | Issue | Localização | Recomendação |
|---|-------|-------------|--------------|
| M1 | Espaçamentos hardcoded sem padrão de escala consistente (valores ímpares: 7px, 9px, 13px, 14px, 26px) | Vários CSS | Definir escala de 4px: 4, 8, 12, 16, 20, 24, 32 |
| M2 | Tokens de cor duplicados entre `admin.css` e `consulta.css` (`#e7e7e7`, `#adadad`, `#8a8a8a`) sem fonte única | Ambos | Criar `tokens.css` com variáveis CSS (`--color-border`, `--color-muted`) |
| M3 | Nomes de classes não unificados: `.painel-kicker` vs `.admin-kicker` vs `.dashboard-kicker` — mesmo estilo, 3 nomes | 3 arquivos CSS | Unificar em `.kicker` no arquivo base |
| M4 | Responsividade com breakpoints diferentes por arquivo (860px em admin, 920px em layout, 760px em home) | 3 arquivos | Padronizar breakpoints e documentar no design system |

### Baixo

| # | Issue | Localização | Recomendação |
|---|-------|-------------|--------------|
| L1 | `border-radius: 0` declarado explicitamente em muitos componentes individualmente | Vários | Setar `* { border-radius: 0 }` no reset global |
| L2 | Largura máxima inconsistente: `.painel` usa `930px`, `.admin-shell` usa `980px` | 2 arquivos | Definir `--max-width-content: 960px` como token único |
| L3 | Classe `.mensagem` mistura estilos base com variantes no mesmo bloco | `consulta.css` | Separar base de modificadores |
| L4 | `@keyframes fadeIn` definido em múltiplos arquivos CSS separados | `consulta.css`, `admin.css`, `home.css` | Centralizar em `layout.css` ou `tokens.css` |

---

## Score de Auditoria

| Dimensão | Pontuação | Observação |
|----------|-----------|------------|
| Consistência visual | 8/10 | Paleta e tipografia altamente coesas |
| Cobertura de tokens | 5/10 | Sem variáveis CSS; valores hardcoded em todo lugar |
| Componentização | 7/10 | Componentes bem definidos, mas sem arquivo de base compartilhado |
| Documentação | 2/10 | Nenhuma documentação existia antes deste arquivo |
| Acessibilidade | 7/10 | Focus e aria presentes; faltam alguns roles e labels |
| Responsividade | 7/10 | Breakpoints funcionam, mas não estão padronizados |
| **Total** | **6/10** | Sistema maduro visualmente, carente de formalização técnica |

---

### Top 3 Ações de Maior Impacto

1. **Criar `statics/css/tokens.css`** com variáveis CSS (`--color-ink`, `--color-border`, `--space-4`, etc.) e importar em todos os outros CSS — elimina a duplicação de valores hardcoded e facilita mudanças globais.

2. **Extrair CSS do `perfil/index.html`** para arquivo próprio — o único arquivo que ainda mistura HTML com estilos inline extensos, violando o padrão do resto do sistema.

3. **Unificar classes de kicker, painel e subtítulo** — `.painel-kicker`, `.admin-kicker` e `.dashboard-kicker` têm exatamente o mesmo CSS. Uma única classe `.kicker` num arquivo base resolveria a triplicação.
