# Visual Office Manager — Edição de Natal

Aplicativo multiplataforma em **Python + Flet** com quatro módulos integrados:
calendário de compromissos, calculadora, cadastro de pessoas com fotografia e
gestão financeira com demonstração de integração ao WhatsApp. Os dados ficam em
**SQLite** e as imagens são tratadas com **Pillow**.

![Calendário](docs/screenshots/01-calendario.png)

| Calculadora | Pessoas |
|---|---|
| ![](docs/screenshots/02-calculadora.png) | ![](docs/screenshots/03-pessoas.png) |
| **Finanças** | **Gráficos** |
| ![](docs/screenshots/04-financas.png) | ![](docs/screenshots/05-graficos.png) |
| **WhatsApp (sandbox)** | **Celular** |
| ![](docs/screenshots/06-whatsapp.png) | ![](docs/screenshots/07-celular.png) |

---

## 1. Como executar

Requisitos: Python 3.10+.

```bash
python -m pip install -r requirements.txt
```

```bash
python main.py
```

Outras formas:

```bash
python main.py --web          # abre no navegador (http://localhost:8550)
```

```bash
flet run main.py              # desktop com recarga automática ao salvar
```

```bash
python tools/seed_demo.py     # (opcional) dados de demonstração para a apresentação
```

```bash
python -m pip install -r requirements-dev.txt && python -m pytest   # testes
```

> **Linux desktop:** o seletor de arquivos do Flet usa o *Zenity*
> (`sudo apt-get install zenity`). No navegador ele não é necessário.

### Gerar o app para celular

```bash
flet build apk        # Android
```

```bash
flet build ipa        # iOS (requer macOS + Xcode)
```

O `pyproject.toml` já declara as dependências, a permissão de câmera e o ícone
(`assets/icon.png`, gerado com Pillow).

---

### Versão web (link para testar no celular e no desktop)

```bash
python tools/build_web.py
```

Gera `dist_web/`, um site estático em que o Python roda dentro do navegador
(Pyodide). Hospede a pasta em qualquer servidor estático (Netlify Drop,
GitHub Pages, Vercel) ou teste na rede local:

```bash
python -m http.server 8000 --directory dist_web
```

Nessa versão os dados ficam só na memória da aba (recarregar a página volta
aos dados de demonstração) e a conexão real com o WhatsApp não existe — use o
app instalado para isso.

## 2. Arquitetura

Camadas com dependência em um único sentido — a interface nunca escreve SQL e
as regras de negócio não conhecem o Flet:

```
 UI (Flet)                app/ui, app/modules/*/view.py
   │  chama
 Serviços (regras)        app/services/*   ← validação, cálculos, Pillow, WhatsApp
   │  usam
 Repositórios (SQL)       app/database/repositories.py
   │
 SQLite                   data/visual_office.db  (+ data/photos/)
```

* **Composição:** `app/services/container.py` monta banco → repositórios → serviços.
* **Contexto da UI:** `app/ui/context.py` entrega aos módulos o `page`, os
  serviços, as notificações e o layout atual (`mobile`, `tablet`, `desktop`).
  `run_safely()` padroniza o tratamento de erros (validação, banco, inesperados).
* **Telas reconstruíveis:** cada módulo guarda seu estado na instância e
  `build()` gera a interface a partir dele — assim a tela é refeita ao mudar de
  layout (ex.: girar o celular ou redimensionar a janela) sem perder o estado.

### Estrutura de arquivos

```
visual_office_manager/
├── main.py                       # ponto de entrada
├── requirements.txt / pyproject.toml
├── app/
│   ├── config.py                 # nome, versão, pastas de dados, breakpoints
│   ├── database/
│   │   ├── connection.py         # conexão, esquema, migração, erros amigáveis
│   │   ├── models.py             # dataclasses de domínio
│   │   └── repositories.py       # todo o SQL (parametrizado)
│   ├── services/
│   │   ├── container.py          # injeção de dependências
│   │   ├── appointment_service.py
│   │   ├── calculator_engine.py  # avaliação segura com ast + Decimal
│   │   ├── people_service.py
│   │   ├── image_service.py      # Pillow: EXIF, recorte, resize, JPEG, miniatura
│   │   ├── finance_service.py
│   │   └── whatsapp/
│   │       ├── gateway.py        # contrato do provedor + Sandbox + parser de webhook
│   │       ├── interpreter.py    # texto → sugestão de lançamento
│   │       └── automation.py     # fluxo webhook → sugestão → confirmação
│   ├── ui/
│   │   ├── theme.py              # paleta natalina e tema
│   │   ├── shell.py              # cabeçalho + navegação adaptativa + transições
│   │   ├── context.py
│   │   └── components/           # header (neve), navegação, widgets, feedback, câmera
│   ├── modules/
│   │   ├── calendar/view.py
│   │   ├── calculator/view.py
│   │   ├── people/view.py
│   │   └── finance/              # view, formulário, gráficos, painel WhatsApp
│   └── utils/                    # formatadores pt-BR e validadores
├── assets/                       # ícone (Pillow) e fonte Inter (licença OFL)
├── deploy/evolution/             # docker-compose da Evolution API
├── tests/                        # 44 testes automatizados
├── tools/                        # seed_demo.py, serve_web.py
└── docs/screenshots/
```

### Banco de dados

| Tabela | Conteúdo | Observações |
|---|---|---|
| `people` | nome, telefone, e-mail, nascimento, endereço, foto, miniatura | nome com `CHECK` de tamanho mínimo |
| `appointments` | título, descrição, data, hora, `person_id` | **FK** para `people` com `ON DELETE SET NULL` |
| `transactions` | tipo, descrição, valor em **centavos**, categoria, data, origem | `CHECK` de tipo, valor > 0, origem `manual`/`whatsapp` |
| `whatsapp_messages` | mensagens do sandbox, status, `transaction_id` | `external_id` único (webhook idempotente) |
| `calc_history` | expressões e resultados | mantém os 200 mais recentes |
| `settings` | preferências (neve ligada, último módulo) | |

Cada operação abre uma conexão curta com `commit`/`rollback` automáticos e
`PRAGMA foreign_keys = ON`. Os valores monetários são inteiros (centavos) para
evitar erros de ponto flutuante.

Local dos dados: `data/` no projeto; `FLET_APP_STORAGE_DATA` em apps
empacotados; ou a pasta definida em `VOM_DATA_DIR`.

---

## 3. Módulos

**Calendário** — grade mensal (segunda a domingo), navegação entre meses e
"Hoje", indicadores de compromissos (pontos) e de aniversários das pessoas
cadastradas (bolo), lista do dia com edição/exclusão, próximos compromissos,
seletores nativos de data e hora e vínculo opcional com uma pessoa.

**Calculadora** — teclado na tela e físico (Enter, Esc, Backspace, `* / ( ) ^ %`),
prévia do resultado enquanto digita, vírgula decimal, porcentagem, potência,
multiplicação implícita `2(3+1)`, histórico salvo no SQLite (toque para
reutilizar). A avaliação usa `ast` + `Decimal` (sem `eval()`), com mensagens
para divisão por zero, parênteses desbalanceados, expoentes enormes etc.

**Pessoas** — CRUD completo com busca (nome, e-mail, endereço, telefone),
detalhes com idade calculada, validação de e-mail/telefone/data, confirmação de
exclusão. Fotos: galeria (todas as plataformas) e câmera (Android/iOS/Web
empacotados). O Pillow corrige a orientação EXIF, converte para RGB, recorta em
quadrado (proporção padronizada), redimensiona para 512 px, comprime em JPEG e
gera miniatura de 128 px.

**Finanças** — entradas e despesas com categorias, filtros, busca, navegação por
mês, edição/exclusão; cartões de saldo acumulado, entradas, despesas e
resultado do mês; gráficos de despesas por categoria e entradas × despesas nos
últimos 6 meses (desenhados com controles nativos, sem dependências extras).

**WhatsApp (demonstração)** — veja a seção 5.

---

## 4. Responsividade e identidade visual

| Largura | Navegação | Listas |
|---|---|---|
| < 640 px (celular) | barra inferior, cabeçalho compacto | cartões, formulários empilhados, botões maiores |
| 640–1023 px (tablet) | trilho lateral só com ícones | cartões em grade |
| ≥ 1024 px (desktop) | barra lateral estilo macOS com translucidez | tabelas com todas as colunas |

Paleta: verde‑pinheiro `#1F4D3A`, vermelho‑vinho `#8C2434`, dourado suave
`#C9A55C`, branco‑gelo `#F4F6F5` e neutros. Detalhes natalinos discretos:
estrelas douradas e neve animada no cabeçalho (pode ser desligada — a
preferência fica salva), contagem regressiva para o Natal e o ícone com estrela.
Transições suaves entre módulos (`AnimatedSwitcher`), animações de hover e de
barras dos gráficos.

---

## 5. WhatsApp no seu número (Evolution API) — real

Escreva no seu WhatsApp, na conversa **"Mensagem para mim mesmo"**, algo como
*"Comprei um lanche foi 3 reais"*: o app registra a despesa, atualiza o saldo
na tela em tempo real e responde no próprio WhatsApp. Comandos: *saldo*,
*extrato*, *desfazer*, *ajuda* (e *sim*/*não* no modo com confirmação).

Passo a passo completo: **[docs/WHATSAPP_EVOLUTION.md](docs/WHATSAPP_EVOLUTION.md)**
(Docker em `deploy/evolution/`, QR Code direto no app).

Arquivos: `app/services/whatsapp/evolution.py` (cliente HTTP + filtro do
webhook), `webhook_server.py` (servidor local), `live.py` (ciclo de vida),
`automation.py` (assistente) e `app/modules/finance/evolution_card.py` (tela).
Só são lidas as mensagens que você escreve para o seu próprio número (ou de
números autorizados); as demais conversas são ignoradas sem serem gravadas.

## 5.1 Simulação (sem conexão) — reserva para a apresentação

O fluxo funciona de ponta a ponta **dentro do computador**, sem acessar o WhatsApp:

1. O texto digitado no painel vira um **payload no formato do webhook da
   WhatsApp Cloud API** (`SandboxGateway.build_incoming_payload`).
2. `parse_webhook()` extrai as mensagens de texto (o mesmo código serviria para
   um webhook real). Mensagens repetidas são ignoradas pelo `external_id`.
3. `interpreter.interpret()` identifica **valor** (R$ 45,00 · 3.500 · 2 mil),
   **tipo**, **categoria**, **data** (hoje, ontem, dia 15, 18/12) e
   **descrição**, com um índice de confiança.
4. A sugestão aparece no chat; o usuário **confirma, edita ou descarta**.
   Nada é gravado sem confirmação.
5. O lançamento é salvo com origem `whatsapp` e a resposta da automação é
   registrada localmente (o `SandboxGateway` nunca envia mensagens).

Exemplo: *"Gastei R$ 45,00 no mercado hoje."* → Despesa · Alimentação ·
R$ 45,00 · "Mercado" · data de hoje.

Para produção bastaria implementar outro `MessagingGateway` (envio via API
oficial) e um endpoint HTTPS que repasse o webhook a `handle_webhook()`. Isso
exige conta WhatsApp Business verificada, token da Cloud API, servidor público
e consentimento dos usuários — **não incluído** neste projeto acadêmico.

---

## 6. Limitações conhecidas

* **WhatsApp real:** a Evolution API usa o protocolo do WhatsApp Web (não
  oficial). Há risco de restrição do número pelos termos do WhatsApp, e o app
  precisa estar aberto para receber as mensagens. Veja os avisos no guia.
* **Câmera:** usa a extensão oficial `flet-camera`, disponível somente em apps
  gerados com `flet build` (Android, iOS ou Web). Em `python main.py`/`flet run`
  e no desktop o botão "Câmera" não aparece; use a galeria.
* **Interpretador do WhatsApp:** baseado em regras e palavras‑chave — cobre
  frases comuns em português, mas não entende qualquer frase. Por isso existe
  a etapa de confirmação/edição.
* **Gráficos:** desenhados com contêineres do Flet (barras), sem pizza/rosca.
* **Teclado da calculadora:** atalhos dependem de o aplicativo estar com foco.
* **Fonte:** Inter é empacotada; emojis dependem de fonte do sistema (o app
  evita emojis na interface por isso).
* **Saldo atual** considera lançamentos até a data de hoje (lançamentos
  futuros aparecem no mês correspondente, mas não no saldo).
* Não há login/criptografia: o banco é local. Para dados pessoais reais,
  proteja o acesso ao computador e faça cópias de segurança de `data/`.

---

## 7. Testes

`python -m pytest` executa 44 testes que cobrem: calculadora (válidos e
inválidos, segurança contra código), interpretador de mensagens (exemplo do
enunciado, salário, conta de ontem, datas explícitas, "mil"), CRUD de pessoas
com processamento real de imagem, validações, relacionamento
compromisso ↔ pessoa (`ON DELETE SET NULL`), finanças (saldos, categorias,
meses), fluxo completo do WhatsApp (confirmação obrigatória, idempotência do
webhook), integração Evolution (filtro de privacidade, servidor de webhook real,
salvar/desfazer/confirmar pelo chat, respostas) e persistência após "reabrir" o banco.

A interface foi verificada no navegador (Chromium) em 1366×860, 820×1000 e
390×844, incluindo troca de layout em tempo real.

## Créditos

Fonte Inter © The Inter Project Authors — SIL Open Font License
(`assets/fonts/Inter-OFL-LICENSE.txt`).
