# Conectar o seu WhatsApp (Evolution API)

Com isto, você escreve no **seu WhatsApp de verdade** — na conversa
**"Mensagem para mim mesmo"** (o chat com o seu próprio número) — e o
Visual Office registra o lançamento, atualiza o saldo e responde no próprio
WhatsApp:

```
Você:        Comprei um lanche foi 3 reais
Assistente:  🤖 ✅ Despesa registrada
             • Lanche — R$ 3,00
             • Alimentação · 24/11/2026
             💰 Saldo atual: R$ 17.873,28
             Errou? Responda desfazer.
```

Comandos no chat: **saldo**, **extrato**, **desfazer**, **ajuda**.
No modo com confirmação, responda **sim** ou **não**.

## Como funciona

```
Seu celular (WhatsApp)
      │  (sessão "Aparelho conectado", igual ao WhatsApp Web)
      ▼
Evolution API  ── Docker no seu PC, porta 8080
      │  webhook messages.upsert
      ▼
Visual Office  ── servidor local na porta 8765 (/webhook/evolution?token=...)
      │  interpreta → salva no SQLite → atualiza a tela
      └─► responde pelo /message/sendText da Evolution
```

**Privacidade:** o app só lê mensagens que **você** escreveu na conversa com
o seu próprio número (e, se quiser, de números que você autorizar). Todas as
outras conversas são descartadas sem serem gravadas. A URL do webhook tem um
token secreto, então ninguém da sua rede consegue injetar mensagens.

## Passo a passo

### 1. Instalar o Docker
Instale o **Docker Desktop** (Windows/macOS) ou Docker Engine (Linux).

### 2. Subir a Evolution API
```bash
cd deploy/evolution
```
```bash
cp .env.example .env
```
Abra o `.env` e troque `AUTHENTICATION_API_KEY` por uma senha forte. Depois:
```bash
docker compose up -d
```
Teste no navegador: <http://localhost:8080> deve mostrar
`"Welcome to the Evolution API, it is working!"`.

### 3. Conectar pelo app
1. Abra o Visual Office (`python main.py`) → **Finanças** → aba **WhatsApp**.
2. Em **Configurações da Evolution API**, cole a API key do `.env`
   (os outros campos já vêm prontos).
3. Clique em **Conectar meu WhatsApp**.
4. No celular: **WhatsApp › Aparelhos conectados › Conectar aparelho** e
   aponte para o QR Code. (Ou digite seu número com DDD e use
   **Gerar código** para conectar por código.)
5. Ao conectar, você recebe uma mensagem de boas-vindas na conversa
   "Mensagem para mim mesmo". Pronto!

O app guarda a configuração; nas próximas aberturas o recebimento liga sozinho.

### 4. Usar
Abra a conversa com **você mesmo** no WhatsApp e escreva:
- `Comprei um lanche foi 3 reais`
- `Paguei 120,50 de luz ontem`
- `Recebi 3.500 de salário`
- `saldo` · `extrato` · `desfazer`

A tela de Finanças atualiza na hora, e a conversa aparece espelhada no painel.

## Opções

| Opção | Para quê |
|---|---|
| **Salvar automaticamente** (padrão) | Registra direto; responda *desfazer* para cancelar o último. |
| Desligado | O assistente mostra a sugestão e só salva após *sim*. |
| **Outros números autorizados** | Permite que outro número (ex.: um segundo chip ou um familiar) mande lançamentos para o número conectado. |
| **Endereço deste computador** | `host.docker.internal` quando a Evolution roda no Docker do mesmo PC. Se ela rodar em outro servidor, use o IP do seu PC na rede. |

## Problemas comuns

| Sintoma | Solução |
|---|---|
| "Evolution API inacessível" | `docker compose ps` — o contêiner `evolution_api` precisa estar `running`. |
| "API key recusada" | A chave no app deve ser igual a `AUTHENTICATION_API_KEY` do `.env`. |
| QR Code não aparece | Aguarde alguns segundos (o app tenta de novo) ou reinicie: `docker compose restart evolution-api`. |
| Conectado, mas nada acontece | Escreva na conversa com **o seu próprio número**. Veja se o status mostra "Recebendo na porta 8765". O firewall do Windows pode pedir permissão para o Python na primeira vez — permita em rede privada. |
| Porta 8765 ocupada | Troque a porta nas configurações e clique em Salvar. |
| Teste rápido | <http://localhost:8765/health> deve responder `{"status": "ok"}` com o app aberto. |

## Avisos importantes

- A Evolution API usa o protocolo do **WhatsApp Web** (biblioteca Baileys), que
  **não é oficial**. O uso não é permitido pelos termos do WhatsApp e existe
  risco de o número ser restringido. Esse risco é baixo para uso pessoal e de
  pouco volume, mas existe. Para a apresentação, considere usar um **chip secundário**.
- O app precisa estar **aberto** para receber as mensagens.
- A API key fica salva localmente no banco SQLite do app (`data/`).
- Para algo oficial em produção, o caminho é a WhatsApp Cloud API (Meta). O
  código já tem a camada `MessagingGateway` pronta para essa troca.
