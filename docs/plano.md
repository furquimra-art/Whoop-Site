# Plano — onde estamos

Baseado no passo a passo do usuário (guia WHOOP API + Prompt 1 + Prompt 2).

## Feito
- [x] Repositório e estrutura
- [x] `.env.example` com `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` vazios
- [x] `.gitignore` cobrindo `.env`, `whoop_tokens.json`, `whoop_data.json`, `whoop_digest.json`
- [x] `whoop.py`: OAuth2 com escopo `offline`, refresh automático, paginação de 25,
      coleta de recovery, cycles, sleep, workouts, profile e body measurement
- [x] Código do orbe guardado verbatim em `dashboard/orb-reference.html`

## Bloqueado no usuário
- [ ] Preencher o `.env` com o Client Secret (só na máquina dele)
- [ ] Gerar o código de autorização no navegador e rodar `login` + `fetch`

## Depois
- [ ] Prompt 1: análise honesta do histórico (dias, campos vazios, atual vs média de 30d)
- [ ] Prompt 2: entrevista de 8 perguntas, uma por vez
- [ ] Confirmação das respostas em 5 linhas
- [ ] Dashboard HTML autocontido, com fórmulas visíveis e suposições configuráveis

## Regras do dashboard (do Prompt 2)
- Só números reais; nada de placeholder
- Fórmula de cada cálculo impressa na própria página
- Toda suposição vira um controle ajustável
- A decisão da pergunta 4 vai no topo, em uma frase, antes de qualquer gráfico
- Usar os nomes de campo reais do WHOOP no código
- Orbe: usar o código de referência, com `ORB_COLOR` derivado do valor
- Ao final, dizer o que é medido e o que é modelado
