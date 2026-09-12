# Plano — onde estamos

Baseado no passo a passo do usuário (guia WHOOP API + Prompt 1 + Prompt 2).

## Feito
- [x] Repositório e estrutura
- [x] `.env.example` com `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` vazios
- [x] `.gitignore` cobrindo `.env`, `whoop_tokens.json`, `whoop_data.json`, `whoop_digest.json`
- [x] `whoop.py`: OAuth2 com escopo `offline`, refresh automático, paginação de 25,
      coleta de recovery, cycles, sleep, workouts, profile e body measurement
- [x] Código do orbe guardado verbatim em `dashboard/orb-reference.html`
- [x] Servidor simulado da API + teste ponta a ponta (40 verificações, todas passando)
- [x] `build_dashboard.py`: dashboard HTML autocontido, com modo `--demo`
- [x] PDF com o passo a passo: `docs/WHOOP-dashboard-passo-a-passo.pdf`

## Bloqueado no usuário
- [ ] Preencher o `.env` com o Client Secret (só na máquina dele)
- [ ] Gerar o código de autorização no navegador e rodar `login` + `fetch`

## Depois
- [ ] Prompt 1: análise honesta do histórico (dias, campos vazios, atual vs média de 30d)
- [ ] Prompt 2: entrevista de 8 perguntas, uma por vez
- [ ] Confirmação das respostas em 5 linhas
- [ ] Dashboard HTML autocontido, com fórmulas visíveis e suposições configuráveis

## Respostas da entrevista (em andamento)

**1. Objetivo.** 76 kg até dezembro de 2026, com o máximo de músculo. Hoje 79,9 kg.
Já esteve em 76 kg em 2022, correndo todo dia. Recuperou todo o peso ao parar de
correr, chegando a 93,4 kg em agosto de 2025.

**2. Semana atual.** Musculação de segunda a sexta, 60 a 90 min, por volta das 16h.
Plano novo: cardio pela manhã às 8h30, zonas 1 a 3, 20 min nos próximos 30 dias,
subindo 5 min a cada 30 dias. Percepção de que segunda é o dia mais pesado; os
dados dizem terça (strain 14,0 contra 12,4).

**3. Histórico.** Um ciclo completo de perda e recuperação. O mecanismo que
segurou o peso foi volume aeróbico diário, não dieta. Correlações confirmam:
gasto energético explica FC de repouso (−0,70) e HRV (+0,60); o peso não explica
nenhum dos dois.

**4. A decisão de cada dia.**
> "Que horas eu preciso apagar a luz hoje para o plano de amanhã funcionar?"

É decisão de fim de dia, não de manhã. Ataca a restrição que os dados apontam
como principal: déficit de 1,55 h de sono por noite, com o usuário pegando no
sono à 00:23 e precisando apagar a luz por volta das 22:10.

Fórmula, só com campos medidos pelo WHOOP:

    apagar a luz = hora de acordar − sleep_need − awake_duration

- `sleep_need` e `awake_duration` vêm da API, variam todo dia
- a hora de acordar é o único parâmetro do usuário
- medianas atuais: sleep_need 9,02 h, awake_duration 20 min

## Regras do dashboard (do Prompt 2)
- Só números reais; nada de placeholder
- Fórmula de cada cálculo impressa na própria página
- Toda suposição vira um controle ajustável
- A decisão da pergunta 4 vai no topo, em uma frase, antes de qualquer gráfico
- Usar os nomes de campo reais do WHOOP no código
- Orbe: usar o código de referência, com `ORB_COLOR` derivado do valor
- Ao final, dizer o que é medido e o que é modelado
