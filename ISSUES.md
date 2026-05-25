# Issues — ProtheusData

> Problemas identificados na auditoria de 25/05/2026. Ordenados por prioridade.

---

## Crítico

### C1 — CSS inline extenso no template de Perfil
**Arquivo:** `templates/perfil/index.html`  
~200 linhas de CSS estão embutidas diretamente no HTML via `<style>`, quebrando o padrão do restante do sistema que mantém estilos em arquivos separados. Qualquer alteração visual no perfil é invisível para quem busca no diretório CSS.  
**Correção:** Extrair para `statics/css/perfil/perfil.css` e referenciar via `<link>`.

---

### C2 — Dependência de fonte externa (Google Fonts)
**Arquivo:** `statics/css/login/login.css`  
A fonte `Sora` é carregada via `@import url('https://fonts.googleapis.com/...')`. Se o servidor não tiver acesso à internet (rede interna/intranet) ou o Google Fonts estiver indisponível, o login exibe com fonte de fallback sem aviso.  
**Correção:** Hospedar os arquivos `.woff2` da Sora localmente em `statics/fonts/`, ou substituir pela `Segoe UI` com ajuste de peso — que já é a fonte padrão do sistema.

---

## Moderado

### M1 — Sem variáveis CSS — valores hardcoded duplicados em 6 arquivos
**Arquivos:** todos os CSS em `statics/css/`  
Valores como `#e7e7e7`, `#adadad`, `#8a8a8a`, `0.35s ease` e `border: 1px solid` aparecem repetidos dezenas de vezes sem fonte única. Uma mudança de cor de borda, por exemplo, exige editar 6 arquivos manualmente.  
**Correção:** Criar `statics/css/tokens.css` com variáveis CSS (`--color-border`, `--color-muted`, `--transition-base`, etc.) e importar nos demais arquivos.

---

### M2 — Mesma classe com três nomes diferentes
**Arquivos:** `consulta.css`, `admin.css`, `home.css`  
`.painel-kicker`, `.admin-kicker` e `.dashboard-kicker` têm exatamente o mesmo CSS:
```css
font-size: 9px; font-weight: 600; letter-spacing: 1.1px;
text-transform: uppercase; color: #adadad;
```
Triplicação sem razão — qualquer ajuste precisa ser feito nos três lugares.  
**Correção:** Unificar em uma única classe `.kicker` num arquivo base compartilhado.

---

### M3 — Breakpoints inconsistentes entre arquivos
**Arquivos:** `layout.css` (1080px, 920px), `admin.css` (860px, 480px), `home.css` (760px, 640px)  
Cada arquivo define seus próprios breakpoints sem padronização. Isso torna impossível prever o comportamento responsivo sem abrir cada CSS individualmente.  
**Correção:** Definir breakpoints canônicos no design system e documentar: `sm=640px`, `md=768px`, `lg=1024px`, `xl=1280px`.

---

## Baixo

### L1 — `@keyframes fadeIn` definido 3 vezes
**Arquivos:** `consulta.css`, `admin.css`, `home.css`  
A mesma animação de entrada é redeclarada em cada arquivo separadamente. Sem impacto funcional, mas gera manutenção duplicada.  
**Correção:** Mover para `layout.css` ou `tokens.css` e remover das cópias.

---

### L2 — Largura máxima de conteúdo inconsistente
**Arquivos:** `consulta.css` (`max-width: 930px`), `admin.css` (`max-width: 980px`)  
Painéis de relatório e painéis admin têm larguras máximas ligeiramente diferentes sem justificativa visual. O conteúdo da página "dança" ao navegar entre seções.  
**Correção:** Definir `--max-width-content: 960px` como token único e aplicar em ambos.

---

### L3 — `border-radius: 0` declarado individualmente em muitos componentes
**Arquivos:** vários  
O princípio "flat" (sem bordas arredondadas) é um pilar do sistema, mas é imposto declarando `border-radius: 0` componente a componente em vez de no reset global.  
**Correção:** Adicionar `*, *::before, *::after { border-radius: 0 }` no reset em `layout.css`. A única exceção necessária (spinner) já usa `border-radius: 50%` explicitamente.

---

## Resumo

| # | Prioridade | Issue | Esforço |
|---|------------|-------|---------|
| C1 | 🔴 Crítico | CSS inline no perfil | Baixo |
| C2 | 🔴 Crítico | Fonte externa (Google Fonts) | Baixo |
| M1 | 🟡 Moderado | Sem variáveis CSS | Médio |
| M2 | 🟡 Moderado | Classe kicker triplicada | Baixo |
| M3 | 🟡 Moderado | Breakpoints sem padrão | Médio |
| L1 | 🟢 Baixo | fadeIn declarado 3x | Trivial |
| L2 | 🟢 Baixo | max-width inconsistente | Trivial |
| L3 | 🟢 Baixo | border-radius no reset | Trivial |
