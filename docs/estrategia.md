# BotBene · Estratégias em uso e como operar

> **Parte 1** (esta) explica as estratégias que o bot usa e como operar com ele. **Parte 2** mostra como cada regra da apostila virou código, com as páginas.
> Fonte de verdade: **"Estudos e anotações sobre a Lógica do Preço"**. As páginas citadas são as do PDF da apostila.

## Resumo

| Estratégia | Papel no bot | Quando entra | Acerto em dados que ela nunca viu |
|---|---|---|---|
| **Apostila · retração no comando** | **Principal.** Mostra o pedido no painel e manda a ordem (no modo recomendado, sozinha, com direito a veto) | Dentro da vela seguinte ao comando, nos primeiros 15 s | **~54%** (440 entradas) · empate 54,3% |
| Apostila · marcações | Comparação: só registra, não manda ordem | Dentro da vela, nos primeiros 15 s | 48% (562) |
| LDP v1.3 (script da IQ) | Comparação | Abertura da vela seguinte ao sinal | 49,1% (97 mil) |
| LDP v1.3 + regra das linhas | Comparação | Abertura da vela seguinte | 48,8% (64 mil) |
| WIKI PRO V2.1 (script da IQ) | Comparação | Abertura da vela seguinte | 49,3% (56 mil) |

Termos usados aqui:
- **M1**: velas de 1 minuto. O bot só opera M1.
- **Binária turbo**: opção de 1 minuto da IQ. Ganha se o preço fechar a favor do preço de entrada.
- **Payout**: quanto a vitória paga. Nos pares `-op` é ~84%: ganha US$ 1,68 numa entrada de US$ 2 e perde US$ 2 no erro.
- **Empate**: acerto mínimo para não perder dinheiro, que é 1 ÷ (1 + payout). Com 84%, dá **54,3%**.
- **ATR**: a régua do tamanho normal da vela naquele momento. É a média da amplitude (máxima − mínima) das 14 velas antes da vela analisada. Muda com o horário: de madrugada é bem menor que no horário de Londres e Nova York.
- **Pares `-op`**: na IQ, a binária dos pares normais é o instrumento com final `-op` (ex.: `EURUSD-op`). É ele que o bot lê e opera.

## A. Retração no comando (estratégia principal)

### A ideia, na apostila

Depois de um comando, o preço que volta para dentro dele tende a ser repelido: *"caso o candle atual entre na região do Comando ele será repelido"* (pág. 27). A entrada boa é a **retração na própria vela**, nos primeiros 10 a 15 segundos (págs. 27 e 162). Vela que abre em GAP é abortada (pág. 28).

### A regra exata

1. **Vela de comando.** A vela que acabou de fechar tem **corpo de pelo menos 60% da amplitude** e **amplitude de pelo menos 1,5 ATR**. Ou seja, é uma vela cheia e maior que o normal: comando ou vela de força com pouco pavio.
2. **Sentido.** Comando verde = **CALL**. Comando vermelho = **PUT**.
3. **Sem GAP.** A vela seguinte precisa abrir colada no fechamento do comando: a distância não pode passar de 10% da amplitude do comando. Se passar, o setup é abortado.
4. **Gatilho (a retração).** Nos **primeiros 15 s** da vela seguinte, o preço precisa ir **contra o comando** e chegar a pelo menos **0,8 ATR** de distância da abertura. No CALL o preço tem que descer até o gatilho; no PUT, subir até ele.
5. **Entrada.** No momento do toque, a favor do comando, com **vencimento no fechamento dessa mesma vela** (binária turbo de 1 min).
6. **Sem toque nos 15 s, não entra.** *"Passado esse tempo sem ter ido buscar a marcação, não faça nada"* (pág. 162).

### Exemplo (EURUSD-op, M1)

- ATR das 14 velas anteriores: **2,0 pips** (0,00020).
- Vela das 10:31 (comando): abre 1,11900, mínima 1,11898, máxima 1,11942, fecha 1,11938.
  - Amplitude: 4,4 pips = 2,2 ATR. Passa, porque o mínimo é 1,5 ATR.
  - Corpo: 3,8 pips = 86% da amplitude. Passa, porque o mínimo é 60%.
  - Resultado: **arma CALL** e aparece o pedido de aprovação.
- Vela das 10:32 abre em 1,11938, sem GAP. O GAP máximo seria 0,44 pip.
- Gatilho: 1,11938 − 0,8 × 2,0 pips = **1,11922**.
  - Se até 10:32:15 o preço descer a 1,11922: entra **CALL** no preço do toque, com vencimento às **10:33:00**. Ganha se a vela das 10:32 fechar acima do preço de entrada.
  - Se não descer até lá: não faz nada. No painel aparece "não disparou".

### O que os números dizem

| Teste | Entradas | Acerto |
|---|---|---|
| Período usado para escolher a regra (ajuste) | 192 | 62,0% |
| Período que a escolha não viu (conferência) | 140 | 56,4% |
| 6 pares que a pesquisa nunca viu (AUDJPY, NZDUSD, GBPJPY, AUDCAD, EURNZD, GBPAUD) | 303 | 53,8% |
| **Tudo fora da amostra, somado** | **440** | **~54%** |

É a melhor estratégia que encontramos e é muito melhor que os scripts. Mesmo assim, **ainda não está provado que ela ganhe do payout**: fora da amostra ela fica no empate. Por isso a recomendação é operar só na conta demo até haver cerca de 200 entradas ao vivo com acerto acima do empate mesmo no pior caso: na prática, ~61% em 200 entradas ou ~59% em 500. O bot deixa escolher a conta real, mas pede confirmação.

**Filtros extras.** A maioria **não se sustentou**: RSI entre 30 e 70, tendência pela EMA 21 e toque só depois de 5 s chegaram a 65-70% no ajuste e caíram para ~52% na conferência. Por isso a regra é simples de propósito.

Um filtro foi bem nos dois períodos: só operar quando o comando **não** rompeu a máxima (no CALL) ou a mínima (no PUT) das 10 velas anteriores. Deu 69% no ajuste e 63% na conferência, mas com só ~50 entradas em cada. Faz sentido pela apostila (comando dentro da região, não esticado). Fica como **candidato** a testar nas próximas semanas de dados, que nenhuma regra viu, antes de entrar no bot.

## B. Como operar no BotBene

### 1. Configuração (uma vez)

Na tela **Configuração**:
- **Modo**, um dos quatro:
  - **Só sinais:** registra as entradas e não manda ordem.
  - **Aprovação:** cada entrada aparece na tela e só vai para a conta demo se você aprovar.
  - **Automático:** o bot entra sozinho na conta demo, sem perguntar e sem cartão na tela. Bom para deixar rodando e juntar resultado.
  - **Automático com veto:** entra sozinho, mas o cartão aparece com bipe já aprovado. Se você não fizer nada, a ordem sai no gatilho; se clicar em "Cancelar esta entrada", não sai.
- **Estratégias que operam:** só **retração no comando**.
- **Scripts de comparação:** desligados por padrão. Ligados, o bot também anota o que o LDP v1.3, a regra das linhas, o WIKI PRO e as marcações teriam feito. Eles nunca mandam ordem e servem só para comparar no Desempenho.
- **Pares:** os `-op`, até 8. Hoje são EURUSD, GBPUSD, USDJPY, AUDUSD, EURJPY e EURGBP.
- **Gestão de risco:**
  - valor da entrada (US$ 2 na demo);
  - stop win e stop loss;
  - máximo de entradas por sessão;
  - pausa depois de X perdas seguidas;
  - **martingale desligado** (veja o item 5).
- **Conta:** escolha **Demo** ou **Real** na barra lateral, com o bot parado.
  - A real pede que você digite REAL para confirmar.
  - Ela só inicia com stop loss definido.
  - A tela fica marcada em vermelho enquanto a real estiver ativa.
  - **A recomendação é ficar na demo** até a estratégia provar vantagem ao vivo (veja o item 6).

### 2. Ligue e deixe rodando

Clique em **Iniciar bot** e **não fique ligando e desligando**. A cada início o bot recarrega o histórico, e a estratégia precisa de tempo. Com 6 pares, ela arma várias vezes por hora, mas **só ~8% dos armados viram entrada**: na pesquisa, foram 355 entradas em 4.411 vezes que ela armou. Em 92% das vezes o recuo não vem nos 15 s, e o pedido termina em "não disparou", sem ordem. Por isso, no modo Aprovação, espere muitos pedidos para poucas entradas. O modo **Automático com veto** evita esse clique: o cartão aparece, mas você só precisa agir se quiser cancelar. Nas 8 horas anteriores ao último início, foram cerca de **4 entradas por hora** somando os 6 pares; em horários parados, são menos.

### 3. O pedido de aprovação

Quando um comando fecha, aparece no topo da tela, em qualquer página, um cartão grande com **bipe**. Isso vale nos modos aprovação e automático com veto.
- **O gráfico é o centro:**
  - as últimas 60 velas do par, com zoom e cursor;
  - a **vela de comando marcada**;
  - a **linha tracejada do gatilho** e a linha da **abertura** da vela da entrada;
  - a vela da entrada se mexendo ao vivo.
- **Ao lado:**
  - a direção, em destaque;
  - a contagem regressiva dos 15 s;
  - o preço do gatilho;
  - o **preço agora e quantos pips faltam** até o gatilho;
  - o valor, o vencimento e o botão grande **Aprovar CALL** ou **Aprovar PUT**.
- **Vários pedidos ao mesmo tempo** viram abas no topo, cada uma com a sua contagem. O mais urgente abre primeiro.
- O botão **Tela cheia** fica na barra lateral (ou use F11).

O que cada estado quer dizer:

| Estado no cartão | Significa |
|---|---|
| Aguardando sua decisão | Armou e ainda não tocou o gatilho |
| Aprovado (ou "Automático" no modo com veto) | A ordem sai sozinha se o preço tocar o gatilho dentro dos 15 s. Dá para cancelar até lá |
| O gatilho disparou! | Tocou antes de você aprovar. Aprovar agora entra **no preço do momento** |
| Ordem enviada | A ordem foi para a conta demo |
| Não disparou | O recuo não veio nos 15 s: nenhuma ordem sai, mesmo aprovado |
| Expirou sem resposta | Tocou e a janela fechou sem você aprovar |
| Rejeitado / Cancelado por você | Você recusou antes ou cancelou depois de aprovado: nenhuma ordem sai |
| Bloqueada | A gestão de risco barrou, com o motivo |

### 4. Quando aprovar (e por que o modo recomendado é o automático com veto)

- **A vantagem está nos primeiros segundos depois do toque.** Medido em 12 pares (~640 entradas):

  | Quando a ordem sai | Acerto |
  |---|---|
  | No exato toque | **56,2%** |
  | 5 s depois | 52,6% |
  | 10 s depois | 52,4% |
  | 15 s depois | 53,2% |

  Entrar depois do toque cai para abaixo do empate (54,3%). Por isso o pedido aparece **antes**, quando a estratégia arma, e não depois que o gatilho dispara.
- **Modo recomendado: Automático com veto.** O cartão aparece quando arma, já aprovado, e a ordem sai no exato toque. Você só clica se quiser **cancelar**. Como só ~8% dos armados viram entrada, isso evita ficar aprovando pedidos que não vão disparar.
- **No modo Aprovação, aprove assim que o cartão aparecer.** Aprovar é dizer "se o recuo vier, entre". Se aprovar depois do toque, a entrada sai num preço pior que o medido.
- **Os números medidos supõem aprovar todas as entradas.** Rejeitar por leitura própria é um filtro novo, que ainda não foi medido. Se quiser filtrar, os motivos que a apostila dá e que o bot **não** checa nesta estratégia são:
  - notícia de alto impacto no horário;
  - gráfico claramente consolidado (pág. 223);
  - marcação contrária forte logo à frente, sem espaço até a barreira (págs. 177, 199 e 201).

  Anote quando e por quê, para medirmos se ajuda.
- **Par fechado para binária**, como o EURGBP-op de madrugada, não pede aprovação. O bot só registra o sinal.

### 5. Depois da ordem e gestão de risco

- O resultado chega cerca de 1 s depois do vencimento, no card **Ordens na conta demo** do Painel. Lá aparecem o resultado da sessão, o número de ordens e os acertos e erros.
- **Desempenho:** filtre por "Apostila · retração no comando" e origem "Ao vivo" para ver o acerto com o intervalo de confiança.
- A gestão de risco bloqueia novas ordens quando:
  - chega no stop win;
  - mais uma perda poderia passar do stop loss (contando o pior caso das ordens abertas);
  - atinge o limite de entradas;
  - ou encosta em X perdas seguidas.
- **Martingale com análise.** Fica desligado por padrão e a recomendação é manter assim:
  - depois de uma perda, só a próxima entrada **válida e aprovada** vale mais (nunca entra às cegas na vela seguinte);
  - o valor é calculado para recuperar o ciclo, com até 2 gales;
  - ele não melhora o acerto, só concentra a perda. Com US$ 2 e 1 gale, perder o ciclo custa US$ 6,39 e apaga quase 4 vitórias de US$ 1,68.

### 6. Quando reavaliar

Com 10 ou 30 entradas o resultado é sorte, para o bem ou para o mal: há dias de 40% e dias de 66% com a mesma regra. Reavalie com **~200 entradas da retração no comando**. Nos números de cima do Painel, conte só ela; os scripts de comparação ficam separados.

## C. Estratégias de comparação (não mandam ordem)

Elas só rodam se a opção **"Rodar também os scripts de comparação"** estiver ligada na Configuração (vem desligada). Aí ficam no placar do Painel e na tela Desempenho, marcadas como "comparação".

### Apostila · marcações

- **Mapa de marcações da apostila:**
  - comandos N1, N2 e N3 (abertura, 50% e fechamento);
  - vela de força e pavio grande;
  - taxas divididas (N1, N2, N3, intermediária, de topo e de fundo) e divisão de preço;
  - nova alta e nova baixa, nova posição, nano-lote e defesas.
- **Papel das marcações:** abaixo do preço a marcação é suporte, acima é resistência. Ela troca de papel quando uma vela fecha com o corpo além dela, e perde a validade no segundo rompimento.
- **Setup:** arma na marcação forte mais próxima, a até 0,6 ATR do fechamento, do lado certo (suporte para CALL, resistência para PUT). Pode ser de três tipos:
  - **retração** até a marcação;
  - **reversão**, quando a vela fechou travada na marcação;
  - **throwback**, quando a marcação acabou de ser rompida e trocou de papel.
- **Confluências:** precisa de pelo menos 3 de 5, e cada uma vale 1 ponto:
  - o próprio gatilho;
  - marcação forte;
  - contexto de nova alta ou baixa com nova posição;
  - espaço até a próxima barreira;
  - tendência pela EMA 9/21.
- **Vetos:**
  - regra das linhas;
  - suporte e resistência espremidos (zona de conflito);
  - indecisão, dupla ou tripla posição;
  - consolidação;
  - pernada íngreme demais para retração (pág. 131);
  - CALL e PUT ao mesmo tempo.
- **Gatilho:** tocar a marcação nos primeiros 15 s.
- **Resultado:** 48% na conferência. Mais confluências não melhoraram o acerto: com 4 ou mais, ficou em ~48%.

### LDP v1.3 (script da IQ)

- **Comando de alta:** vela verde sem pavio na abertura (até 2% da amplitude) que vem depois de uma vermelha ou fecha acima da máxima das 3 anteriores. O comando de baixa é o espelho.
- **Linhas:**
  - **linha verde** = 50% do corpo do último comando de alta;
  - **linha vermelha** = 50% do corpo do último comando de baixa.
- **Setups, avaliados na vela que fechou:**
  - **CALL reteste:** vela verde cuja mínima tocou a linha verde e fechou acima dela.
  - **CALL reversão (trava):** vela vermelha que desceu até a linha verde e fechou travada nela, a até 12% da amplitude.
  - **CALL rompimento:** vela verde que fechou acima da linha vermelha, com o fechamento anterior abaixo dela.
  - **PUT:** o espelho de cada um.
  - CALL e PUT na mesma vela se anulam.
- **Entrada:** na abertura da vela seguinte, com vencimento no fechamento dela.

### LDP v1.3 + regra das linhas

Os mesmos sinais do v1.3, mas o **CALL só vale se fechar acima das duas linhas** e o **PUT só se fechar abaixo das duas**. Sinal no meio das linhas é descartado.

### WIKI PRO V2.1 (script da IQ)

- **Cinco pontos possíveis:**
  - **tendência:** EMA 9 > 21 > 50, com a 21 subindo;
  - **momento:** RSI entre 52 e 68 para CALL, ou entre 32 e 48 para PUT;
  - **força:** ADX ≥ 18 com +DI > −DI;
  - **ação do preço:** rompimento da máxima das 5 anteriores, pullback na EMA 9 ou dupla posição com força;
  - **vela de força ou comando.**
- **Para dar CALL**, precisa de tudo isto ao mesmo tempo:
  - ação do preço;
  - vela de força ou comando;
  - ATR ativo (pelo menos 85% da média);
  - preço não esticado (no máximo 1,25 ATR da EMA 9);
  - 3 dos 5 pontos.
- **PUT** é o espelho. A entrada é na abertura da vela seguinte.

### Por que os de fechamento ficam em ~49%

Eles só confirmam o sinal quando a vela **fecha**, e entram na **abertura da seguinte**. Nesse ponto, o que o sinal viu já está no preço, e o minuto seguinte fica praticamente no cara ou coroa. Foram 217 mil entradas em 42 dias, com o resultado inteiro abaixo do empate. Fibonacci, MHI, RSI, Bollinger, engolfo e pin bar, testados da mesma forma, ficaram entre 48% e 52%.

---

# Parte 2 · Como a apostila vira código

A apostila tem direitos reservados e não vai para este repositório: guarde o PDF em `docs/materiais/` (pasta ignorada pelo git).

## 1. Classificação das velas (`backend/app/ldp/candles.py`)

Pavio de **abertura** = o lado onde a vela nasce (embaixo na verde, em cima na vermelha). Pavio de **fechamento** = o oposto.
"Sem pavio" = pavio ≤ 2% da amplitude (mesmo padrão do script v1.3; configurável).

| Abertura | Fechamento | Classe | Páginas |
|---|---|---|---|
| sem | sem | **C1**: comando nível 1 / controle de região | 17-19, 24 |
| sem | com | **C2**: comando único (nível 2) | 6-9, 24 |
| com | sem | **C3**: expirado / fim de taxa (nível 3) | 21-24 |
| com | com | **Vela de força** (corpo ≥ 40% ou rompe máx./mín. anterior) ou **indecisão** | 11-16 |

Corpo menor que 5% da amplitude = doji (sem cor). Também ficam registrados GAP (pág. 28) e o contexto do comando: reversão, rompimento ou fracionamento (pág. 6-7).

## 2. Estruturas e marcações (`backend/app/ldp/structures.py`, `engine.py`)

| Estrutura | Como é detectada | Marcações | Páginas |
|---|---|---|---|
| Comando C1 / C2 / C3 | classe da vela | C1: abertura, 50%, fechamento · C2: abertura, 50% · C3: 50%, fechamento | 26-27 |
| Vela de força | classe da vela | abertura, 50%, fechamento | 138 |
| Pavio grande | pavio ≥ 50% da amplitude | ponta e 50% do pavio | 138, 143 |
| TD nível 1 | C1 + C1, mesma cor, sem GAP | 5 linhas (defesa, 50%, TD, 50%, defesa) | 39, 41 |
| TD nível 2 | expirado + vela de força | junção + pavio da vela seguinte | 39, 41 |
| TD nível 3 | vela de força + comando único (ou o contrário) | abertura do comando único + pavio | 39, 42 |
| TD intermediária | expirado + comando único | junção | 40, 43 |
| TD forte / média / fraca | outras duplas da mesma cor, pela limpeza da junção | só a forte marca a junção | 37-38 |
| Divisão de preço | duas velas de força seguidas | junção + pavios | 54 |
| TD de topo / fundo N1, N2 | reversão no extremo local, cores opostas | junção + 50% (N2: + ponta e 50% do pavio) | 50-53 |
| Dupla posição / futuro | corpo fecha dentro do pavio da vela anterior | pavios + fracionamento | 106-110 |
| Tripla posição | duas duplas seguidas do mesmo lado | idem | 111-112 |
| Nova alta / nova baixa | corpo rompe as máx./mín. recentes (ou a anterior, na reversão) e deixa pavio | pavio + fechamento | 96-104 |
| Nova posição | vela que continua após nova alta/baixa, ou que rompe a indecisão | projeção (pavio oposto) ou abertura, se nasceu careca | 113-120, 129-130 |
| Nano-lote | X X Y X (uma vela de cor diferente no meio do fluxo) | corpo da vela Y | 126, 130 |
| Defesa | X Y Y (reversão confirmada) | corpo do 1º candle da reversão (+50% se for vela de força) | 149-152 |

## 3. Mapa de níveis (`backend/app/ldp/levels.py`)

- **Papel pela posição:** marcação abaixo do fechamento é suporte, acima é resistência.
- **Rompimento só com o corpo:** a vela precisa *fechar* além do nível (pág. 115). Pavio que passa e volta é defesa (pág. 148).
- **Nível rompido troca de papel** (pág. 95: "a demanda de venda rompida vira demanda de compra"). Rompido de novo, perde a validade.
- Marcações muito próximas viram um nível só, com a maior força. Níveis expiram depois de 180 velas sem reforço.
- Força inicial de 1 a 3 ("os pontos fortes de defesa são as aberturas", pág. 149). Os pesos serão calibrados pelas estatísticas.

## 4. Suas regras das linhas, conferidas

Linha verde = 50% do último comando de alta; linha vermelha = 50% do último comando de baixa (script v1.3).

| Regra | Veredito |
|---|---|
| CALL acima da linha verde | **Certo** (pág. 27 "bate estaca"; pág. 162), com o preço voltando à linha e a linha intacta |
| PUT abaixo da linha vermelha | **Certo** |
| Descartar PUT acima da verde / CALL abaixo da vermelha | **Certo** enquanto a linha estiver intacta. Se uma vela **fechar com o corpo** além dela, a linha troca de papel (pág. 95; throwback, pág. 31 e 45) |
| Evitar sinal no meio das duas linhas | **Certo** (indecisão, pág. 106; consolidação, pág. 223). Vira o filtro "zona de conflito" na Fase 2 |

O que a apostila acrescenta: outras marcações além do 50% (aberturas são as mais fortes), espaço até a próxima barreira (pág. 177, 199, 201), gatilho de retração nos 10-15 s iniciais da vela (pág. 27, 162), cenário (topos e fundos sim, consolidação não, pág. 223; pernada de 60° não aceita retração, pág. 131) e GAP = abortar (pág. 28).

## 5. Scripts da plataforma (portados em `backend/app/strategies/`)

- **LDP v1.3:** usa só o 50% do último comando (C1/C2). Calcula TD e expirado, mas não usa nos sinais. Sem filtro de espaço ou de indecisão. Entra na abertura da vela seguinte.
- **WIKI PRO V2.1:** dos 3 pontos exigidos, 2 já são condições obrigatórias, então basta 1 indicador concordar. A "vela de força" dele é "corpo grande", não a da apostila. Serve como filtro de tendência.
- Num teste com 800 velas sintéticas, os dois juntos deram sinal em 292 velas e às vezes se contradisseram na mesma vela. Isso mostra a falta de seletividade; não diz nada sobre acerto.

## 6. Estratégias de dentro da vela (`backend/app/strategies/`)

As duas entram DENTRO da vela, como manda a apostila: no fechamento da vela k armam um setup para a vela k+1; a entrada só acontece se o gatilho disparar nos primeiros 15 s dela ("passado esse tempo sem ter ido buscar a marcação, não faça nada", pág. 162), com vencimento no fim da k+1. Vela k+1 aberta em GAP = abortar (pág. 28).

**Apostila · retração no comando** (`retracao_comando.py`) — a principal.
- Vela k forte: corpo >= 60% da amplitude e amplitude >= 1,5 × ATR (média das amplitudes das 14 velas anteriores a ela).
- Gatilho: nos 15 s iniciais da k+1 o preço recua pelo menos 0,8 × ATR a partir da abertura. Entra a favor da vela k ("caso o candle atual entre na região do comando ele será repelido", pág. 27).

**Apostila · marcações** (`ldp_apostila.py`) — mantida para comparação.
- Arma na marcação mais próxima do mapa de níveis (retração, reversão ou throwback), com confluências (gatilho, força, contexto, espaço, tendência; mínimo 3) e vetos (regra das linhas, zona de conflito, indecisão, consolidação, pernada íngreme).
- Na pesquisa ficou abaixo do empate (ver seção 7).

## 7. Pesquisa: como medimos e o que deu

**Método.** Base separada (`data/research.sqlite`, ferramenta `python -m app.tools.research`): 6 pares (EURUSD, GBPUSD, USDJPY, AUDUSD, EURJPY, EURGBP), velas de 1 min e de 5 s. A IQ guarda as de 5 s só por ~1 semana; elas servem para ver o que aconteceu DENTRO de cada minuto (o bot continua operando em 1 min). Cada teste usa os 60% iniciais do tempo para ajustar e os 40% finais para **conferir uma vez só**. Entrada no fechamento da vela de 5 s em que o gatilho disparou; resultado no fechamento do minuto. Mínimo para empatar com payout de 85%: **54,1%**.

**Resultados (26/10 a 02/11/2026; entre parênteses, número de entradas):**

| Estratégia | Ajuste | Conferência |
|---|---|---|
| Apostila · marcações (seção 6) | 51,2% (777) | 48,0% (562) |
| Retração genérica: preço vai contra 0,5 ATR nos 15 s, entra na volta | 52,4% (8714) | — |
| Seguir o ataque (o contrário) | 47,6% (8714) | — |
| **Retração no comando** (vela 1,5 ATR, recuo 0,8 ATR) | 62,0% (192) | **56,4% (140)**, positiva nos 4 dias |
| Retração no comando, vela 1,0 ATR | 58,1% (353) | 54,2% (262) |
| Retração no comando + RSI 30-70 | 65,4% (136) | 52,9% (104) |
| Retração no comando + RSI 30-70 + toque após 5 s | **70,2%** (84) | **52,0%** (75) |
| Fibonacci 61,8% tocado nos 15 s | 49,8% (624) | 47,0% (385) |
| Fibonacci 50% tocado nos 15 s | 50,2% (849) | 49,8% (528) |
| Bollinger tocada nos 15 s | 50-52% | 48-51% |

**Scripts e estratégias de fechamento em ~42 dias** (velas de 1 min, 03/09 a 02/11/2026, mesmos 6 pares; sinal no fechamento, entrada na abertura da vela seguinte):

| Estratégia | Entradas | Acerto |
|---|---|---|
| LDP v1.3 (script da IQ) | 97.008 | 49,1% |
| LDP v1.3 + regra das linhas | 64.117 | 48,8% |
| WIKI PRO V2.1 (script da IQ) | 55.737 | 49,3% |
| Fibonacci 50% / 61,8% / 78,6% (toque ou rejeição) | 3 mil a 17 mil cada | 48,8% a 50,2% |
| MHI 1 (minoria) / MHI maioria | 60 mil cada | 50,2% / 49,8% (conferência) |
| RSI 14 e RSI 2 nos extremos | 4 mil a 52 mil | 50% a 52% |
| Bollinger (fechou fora, pavio fora, + RSI) | 14 mil a 41 mil | 49,7% a 51% |
| Engolfo, pin bar, 3 velas da mesma cor | 16 mil a 73 mil | 47,8% a 51% |

Nenhuma estratégia que entra na abertura da vela seguinte passou de 52% em nenhum dos dois períodos.

**Conferência no instrumento que o bot opera.** Na IQ, a binária dos pares normais é o instrumento `-op` (ex.: `EURUSD-op`), com preço um pouco diferente do `EURUSD` usado acima (décimos de pip). Repetindo a retração no comando nos mesmos dias com os dados `-op`: vela 1,5 ATR = 60,1% no ajuste (193) e **55,5% na conferência (137)**; vela 1,0 ATR = 59,3% (366) e 55,4% (258). Com payout de 84% (o dos `-op`), o empate é 54,3%. O resultado se mantém, com a mesma ressalva: vantagem pequena, a confirmar ao vivo. O EURGBP foi o par mais fraco nas duas conferências (~36% em ~18 entradas); é pouco para tirar o par, mas fica de olho.

**Teste em pares que a pesquisa nunca viu (03/11/2026).** Regra fixa do bot (vela 1,5 ATR, recuo 0,8 ATR), sem nenhum ajuste, em AUDJPY, NZDUSD, GBPJPY, AUDCAD, EURNZD e GBPAUD (`-op`, 26/10 a 03/11): **53,8% em 303 entradas** (IC 48,2-59,3%); cinco pares entre 55% e 58,5% e o EURNZD em 39,6%. A versão de vela 1,0 ATR deu 51,3% em 567. Somando tudo o que foi medido fora da amostra (conferência + pares novos): **~54,3% em 440 entradas, igual ao empate com payout de 84%**. Conclusão honesta: a retração no comando é a melhor coisa que encontramos, mas **não está comprovado que ela ganhe do payout**. Os 58-62% vinham do período usado para escolher a regra.

O que isso mostra:
1. O princípio da retração da apostila (entrar CONTRA o ataque inicial da vela) tem uma vantagem pequena e real; seguir o ataque perde.
2. A vantagem fica maior quando a vela anterior é forte (o "comando"): é a única combinação que ficou acima do empate nos dois períodos.
3. Filtros extras que pareciam levar a 65-70% no ajuste caíram para ~52% na conferência. É o mesmo efeito que faz scripts "de 70-90%" falharem: ajustados ao passado, com poucas entradas.
4. Nada disso é garantia. Fora da amostra, a retração no comando ficou no empate (~54% em 440 entradas). A confirmação de verdade é o resultado ao vivo, que o painel acompanha; a conta real continua bloqueada.

## 8. Ainda não implementado (próximas fases)

- Cenário (topos e fundos / tendência / consolidação) e macro-lote como filtros medidos na pesquisa.
- Bot olhando vários pares ao mesmo tempo (a retração no comando dá poucas entradas por par).
- Transferência de preço e desinstalação (pág. 134-135) — a definir com exemplos reais.
