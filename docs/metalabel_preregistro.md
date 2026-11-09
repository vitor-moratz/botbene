# Meta-labeling da retração no comando: pré-registro

**Escrito em 08/11/2026, antes de qualquer treino.** Nada daqui muda depois de olhar os dados de validação ou de conferência. Mudar uma regra é começar um estudo novo, com datas novas.

## A ideia

A retração no comando (v1) continua decidindo a direção e o momento da entrada. Um segundo modelo, treinado só com entradas passadas, decide **pegar ou pular** cada entrada.

A v2 é um caso particular desse filtro: ela pula quando o comando é a 3ª vela seguida da mesma cor. Por isso a v2 é a **linha de base a vencer**.

## Dados

- **Origem:** replay das velas gravadas na base de pesquisa (`data/research.sqlite`: M1, 5 s e sentimento). O replay usa o código do bot (`app/research/metalabel.py`, `entries_for_asset`), com as mesmas entradas que o bot faria. Isso é conferido nos testes.
- **Ferramenta:** `python -m app.tools.metalabel montar` gera `data/metalabel/dataset.csv`.
- **Mercado principal:** pares `-op`, de 02/11 a 04/12/2026.
- **Entrada:** fechamento da vela de 5 s do toque, como o backtest do bot. **Rótulo:** ganhou = 1, perdeu = 0. Empate fica de fora.
- **Rótulo secundário (só relatório):** `result_5s`, com a entrada 5 s depois. Mede quanto o resultado depende de executar na hora.

## Variáveis (lista fixa, `FEATURES` em `app/research/metalabel.py`)

| Grupo | Variáveis |
|---|---|
| Vela de comando | `cmd_range_atr`, `cmd_body_ratio`, `cmd_wick_fav`, `cmd_wick_back`, `run_length`, `brk10_atr`, `brk10`, `atr_rel`, `ema_slope_fav`, `prev_range_atr`, `prev_same` |
| Toque | `touch_sec`, `gap_fav_atr`, `run_fav_atr`, `depth_extra_atr`, `price_vs_open_atr` |
| Tempo e mercado | `hour_sin`, `hour_cos`, `weekday`, `otc` |
| Sentimento | `mood_side`, `mood_chg_fav`, `mood_age` (vazios antes de 08/11 19:34) |
| Histórico | `recent_wr` (últimas 20 entradas do mesmo mercado, só as já vencidas no toque) |

O payout ficou de fora porque não há histórico dele por entrada. Ele só entra na conta do empate.

## Divisão por data (horário de Brasília)

| Parte | Datas | Uso |
|---|---|---|
| Treino | 02/11 a 22/11 | ajustar os modelos |
| Validação | 23/11 a 29/11 | escolher o modelo e o limiar |
| Conferência | 30/11 a 04/12 | vista **uma vez**, depois de tudo escolhido |

## Modelos

1. **Principal:** regressão logística com L2 (C = 1). Variáveis padronizadas pela média e desvio do treino. Vazios trocados pela mediana do treino, mais um indicador "sem sentimento".
2. **Comparação:** gradient boosting raso (`HistGradientBoostingClassifier`, profundidade máxima 3, taxa 0,05, 200 iterações, mínimo de 30 por folha).

O escolhido é o que tiver o maior limite inferior de Wilson (95%) na validação, cada um com o seu limiar.

## Limiar

- **Grade:** probabilidade de ganhar de 0,50 a 0,80, de 0,01 em 0,01. Entra quando a probabilidade fica acima do limiar.
- **Principal:** o limiar de maior limite inferior de Wilson com n ≥ 60 na validação.
- **Alta precisão (busca dos 70%):** o menor limiar com acerto ≥ 70% e n ≥ 40 na validação. Se não houver, a variante não existe.

## Critérios na conferência

- **Passa (vai para Observar no bot):** acerto ≥ v2 + 3 pontos nas mesmas datas, limite inferior de Wilson acima de 54,3% (empate com payout de 84%) e n ≥ 100.
- **Alta precisão:** só conta com ≥ 70% e n ≥ 60.
- **Não passa:** o filtro não entra no bot. O resultado fica anotado aqui.
- **Ao vivo (Observar → Operar):** ~61% em 200 entradas ou ~59% em 500, com o modelo congelado (regra de `docs/estrategia.md`).

## OTC (relatório à parte)

O mesmo procedimento nas entradas da v1 no OTC, com o sentimento como variável e as mesmas datas. Serve de evidência para a frente do sentimento dos traders. Não decide nada sozinho.

## Como rodar a Fase 2

Use o ambiente de pesquisa `backend/.venv-pesquisa`, que tem scikit-learn. O ambiente do bot não tem e não deve ter.

1. **A partir de 30/11:** `cd backend && .venv-pesquisa/bin/python -m app.tools.metalabel montar`, para atualizar o conjunto de dados com as velas gravadas. Depois, `.venv-pesquisa/bin/python -m app.tools.metalabel treinar`. Antes de 30/11, o comando recusa.
   - O modelo vai para `app/strategies/models/meta_retracao_op.npz`.
   - O relatório da validação vai para `data/metalabel/treino_op.json`.
2. **A partir de 05/12:** `montar` de novo e depois `.venv-pesquisa/bin/python -m app.tools.metalabel conferir`.
   - Roda **uma vez**: grava `data/metalabel/conferido_op.json` e escreve o resultado abaixo. Na segunda vez, recusa.
3. **OTC (relatório):** os mesmos comandos com `--mercado OTC`.

Para recriar o ambiente de pesquisa: `python3 -m venv backend/.venv-pesquisa`, depois instalar nele as dependências do `backend/pyproject.toml` mais o extra `research` (scikit-learn).

## Resultado

(preencher depois da conferência, sem apagar nada acima)
