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
   python3 whoop.py login
   ```

   Sem nada depois de `login`. O script pede a URL e você cola. Isso evita que
   o terminal se confunda com os caracteres `&` e `?` que a URL contém.

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

6. **Gerar o dashboard**

   ```bash
   python3 build_dashboard.py
   ```

   Escreve `dashboard/index.html`, um arquivo só, que abre com dois cliques e
   não precisa de servidor nem internet.

   Para ver o layout antes de ter dados, com números falsos e um aviso no topo:

   ```bash
   python3 build_dashboard.py --demo
   ```

## Testes

```bash
python3 tests/test_e2e.py
```

Sobe um servidor que imita a API do WHOOP e roda o `whoop.py` de verdade contra
ele, num diretório temporário. Não toca na sua conta nem nos seus arquivos.

## Comandos

| Comando | O que faz |
|---|---|
| `python3 whoop.py url` | imprime a URL de autorização |
| `python3 whoop.py login` | pede a URL de callback e troca por access + refresh token |
| `python3 whoop.py refresh` | força a renovação do access token |
| `python3 whoop.py status` | mostra validade dos tokens |
| `python3 whoop.py digest` | resumo compacto e sem dados pessoais, para análise |
| `python3 whoop.py weight` | histórico de peso; `--kg 78.4 --date 2026-09-01` lança um valor |
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

## Sobre o peso

A API devolve apenas o peso **atual**, sem data e sem série. Não existe endpoint
de histórico. Por isso cada `fetch` carimba o valor do dia em
`whoop_weight.json`, construindo a curva que a API não entrega. Para lançar
pesos antigos que você tenha anotado:

```bash
python3 whoop.py weight --kg 81.2 --date 2026-06-01
```
