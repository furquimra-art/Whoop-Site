# whoop-dashboard

Dashboard pessoal local a partir dos dados da API oficial do WHOOP (OAuth2).
Nada roda em servidor: é um script Python e um arquivo HTML autocontido.

## Estrutura

```
.
├── whoop.py          # cliente OAuth2 + coletor da API
├── .env.example      # modelo de credenciais (o .env real nunca vai pro git)
├── .gitignore        # ignora .env, whoop_tokens.json e whoop_data.json
├── dashboard/        # o dashboard HTML autocontido
└── docs/             # anotações e notas de análise
```

## Pré-requisitos

Python 3.9+. Sem dependências externas — o script usa só a biblioteca padrão.

## Passo a passo

1. **Credenciais**

   ```bash
   cp .env.example .env
   ```

   Preencha `WHOOP_CLIENT_ID` e `WHOOP_CLIENT_SECRET` com os valores do seu app
   em https://developer-dashboard.whoop.com. O `.env` está no `.gitignore`.

2. **Gerar a URL de autorização**

   ```bash
   python3 whoop.py url
   ```

3. **Autorizar no navegador**

   Abra a URL, aprove o acesso. O navegador tentará ir para
   `https://localhost:8080/callback?code=...` e vai mostrar erro de conexão —
   isso é esperado, não há servidor local ouvindo. O que importa é o `code=`
   na barra de endereço.

4. **Trocar o código por tokens (em menos de 1 minuto)**

   ```bash
   python3 whoop.py login <code>
   ```

   O código de autorização expira muito rápido. Se der erro, volte ao passo 2.

5. **Baixar os dados**

   ```bash
   python3 whoop.py fetch
   ```

   Sem argumentos, baixa **todo o histórico** que a sua conta tiver. Use
   `--days 90` se quiser limitar a janela.

   Gera `whoop_data.json`. O access token é renovado sozinho pelo
   `refresh_token` (escopo `offline`), então os próximos `fetch` não exigem
   voltar ao navegador.

## Comandos

| Comando | O que faz |
|---|---|
| `python3 whoop.py url` | imprime a URL de autorização |
| `python3 whoop.py login <code>` | troca o código por access + refresh token |
| `python3 whoop.py refresh` | força a renovação do access token |
| `python3 whoop.py status` | mostra validade dos tokens |
| `python3 whoop.py digest` | resumo compacto e sem dados pessoais, para análise |
|  baixa os dados para `whoop_data.json` | baixa os dados para `whoop_data.json` |

## Escopos solicitados

`offline`, `read:recovery`, `read:cycles`, `read:sleep`, `read:workout`,
`read:profile`, `read:body_measurement`.

## Segurança

`.env`, `whoop_tokens.json` e `whoop_data.json` estão no `.gitignore` e nunca
devem ser commitados. O `whoop_tokens.json` é gravado com permissão `600`.

## Pré-requisito que o código não resolve

A API só devolve dados de quem tem **assinatura WHOOP ativa e strap com dados**.
Sem isso o fluxo inteiro funciona e todos os endpoints voltam vazios.

## Limite de membros

Um app novo atende até 10 membros do WHOOP sem aprovação de produção. Para um
dashboard pessoal isso é irrelevante: você é um membro.
