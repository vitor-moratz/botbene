# BotBene · Estratégias em uso e como operar

> **Parte 1** (esta) explica as estratégias que o bot usa e como operar com ele. **Parte 2** mostra como cada regra da apostila virou código, com as páginas.
> Fonte de verdade: **"Estudos e anotações sobre a Lógica do Preço"**. As páginas citadas são as do PDF da apostila.

## Resumo

| Estratégia | Papel no bot | Quando entra | Acerto em dados que ela nunca viu |
|---|---|---|---|
| **Score LDP v1 (combo)** | **Principal desde 06/11/2026.** Junta as cinco estratégias de dentro da vela e quatro padrões; entra com 3 de 4 sobre a retração no comando e, quando pula, diz na tela o que faltou (seção 2d) | Dentro da vela seguinte ao comando, nos primeiros 15 s | Em validação a partir de 07/11. Antes de congelar: 62,9% em 89 entradas fora do período de escolha |
| Apostila · retração no comando v2 | **Nova (08/11/2026), em validação.** A mesma regra, mas pula a pernada esticada: comando que é a 3ª vela seguida da mesma cor (seção A2) | Dentro da vela seguinte ao comando, nos primeiros 15 s | 54,2% (107) nos `-op` e 54,8% (42) nos OTC, contra 53,7% e 48,1% da v1 nos mesmos dias |
| Apostila · retração no comando | Base do score. Sozinha, fica em Observar | Dentro da vela seguinte ao comando, nos primeiros 15 s | **~54%** (440 entradas) · empate 54,3% |
| Apostila · marcações | Desligada por padrão; pode observar ou operar, mas não é recomendada | Dentro da vela, nos primeiros 15 s | 48% (562); revisão de 08/11: 51% (2.293) |
| Estudo · retração no lote, reversão A e B | Só observar, ou desligar: nenhuma passou na revisão de 08/11 (Parte 2, seção 7b) | Dentro da vela, nos primeiros 15 s | 50% a 53% |
| Pesquisa · esticão rápido | **Nova (08/11/2026), só Observar** (a configuração não deixa operar). Saiu dos dados, não da apostila: depois de vela grande, entra contra o disparo do início do minuto (seção A3) | Dentro da vela seguinte à vela grande, nos primeiros 10 s | 61,1% (18) nos `-op`, poucas entradas; no OTC não funciona |
| Pesquisa · Bollinger + RCI | **Nova (09/11/2026), a pedido do dono.** Bollinger 20/2 tocada com RCI 9 em ±80, entra contra. Pode Observar ou Operar (seção A5) | No início da vela seguinte ao sinal, ~1 vez a cada 8 min por par | 50,0% (33.841) nos `-op` e 50,1% (33.388) no OTC: cara ou coroa |
| Pesquisa · Bollinger + RCI v2 | **Nova (09/11/2026), só Observar.** A v1 só quando Gator dormindo, MACD virando e (nos pares normais) Weis Wave mais fraca (seção A6) | No início da vela seguinte ao sinal; rara (~1% dos sinais da v1) | Medindo no ao vivo a partir de 09/11 |
| Pesquisa · DeepLOB (IA) | **Nova (08/11/2026), só Observar.** Rede do artigo DeepLOB treinada nas velas de 5 s; reprovada no estudo, fica para conferir ao vivo (seção A4) | No início da vela seguinte, quando a probabilidade passa do limiar | 48,2% (1.787) no dia de seleção dos `-op`; OTC sem sinal (fica em silêncio) |
| LDP v1.3 (script da IQ) | Script: só desenho no gráfico | No bot, não entra | 49,1% (97 mil) |
| LDP v1.3 + regra das linhas | Só na ferramenta de pesquisa | No bot, não entra | 48,8% (64 mil) |
| WIKI PRO V2.1 (script da IQ) | Script: só desenho no gráfico | No bot, não entra | 49,3% (56 mil) |

Na pesquisa, os três últimos entram na abertura da vela seguinte ao sinal.

**Estratégia não é script.** Script é ajuda visual. Estratégia é a receita que junta contexto, padrões e gatilho, decide a entrada e é medida.

Termos usados aqui:
- **M1**: velas de 1 minuto. O bot só opera M1.
- **Binária turbo**: opção de 1 minuto da IQ. Ganha se o preço fechar a favor do preço de entrada.
- **Payout**: quanto a vitória paga. Nos pares `-op` é ~84%: ganha US$ 1,68 numa entrada de US$ 2 e perde US$ 2 no erro.
- **Empate**: acerto mínimo para não perder dinheiro, que é 1 ÷ (1 + payout). Com 84%, dá **54,3%**.
- **ATR**: a régua do tamanho normal da vela naquele momento. É a média da amplitude (máxima − mínima) das 14 velas antes da vela analisada. Muda com o horário: de madrugada é bem menor que no horário de Londres e Nova York.
- **Pares `-op`**: na IQ, a binária dos pares normais é o instrumento com final `-op` (ex.: `EURUSD-op`). É ele que o bot lê e opera.

## A. Retração no comando (base do score)

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

Um filtro foi bem nos dois períodos: só operar quando o comando **não** rompeu a máxima (no CALL) ou a mínima (no PUT) das 10 velas anteriores. Deu 69% no ajuste e 63% na conferência, mas com só ~50 entradas em cada. Faz sentido pela apostila (comando dentro da região, não esticado). Fica como **candidato** a testar nas próximas semanas de dados, que nenhuma regra viu, antes de entrar no bot. Na revisão de 08/11 ele oscilou: ajudou com recuo de 0,8 ATR e atrapalhou com 1,0 ATR. Por isso a v2 usou outro sinal de "esticado", que foi estável (seção A2).

## A2. Retração no comando v2 (`retracao_comando_v2`)

**Regra congelada em 08/11/2026.** É a retração no comando com **uma mudança**:

- **Pernada esticada não entra.** Se o comando é a **3ª vela seguida (ou mais) da mesma cor**, pula. Na apostila, pernada íngreme não aceita retração (pág. 131). Doji não conta nem quebra a sequência.
- O resto é igual à v1: vela de comando (corpo ≥ 60%, amplitude ≥ 1,5 ATR), GAP aborta, recuo de 0,8 ATR nos 15 s iniciais, entrada a favor do comando, vencimento no fim da vela.

A v1 continua no bot sem mudança, porque o Score LDP v1 usa a v1 por dentro. A v2 só arma em velas em que a v1 também armaria, então a v2 é um pedaço da v1.

**Como foi escolhida.** Pares `-op` e OTC, velas de 5 s de 31/10 a 08/11/2026. Ajuste antes de 05/11; conferência de 05/11 em diante, vista uma vez só, depois de a regra ser escrita. Payout de 84%, empate 54,3%.

| Teste | v1 | v2 |
|---|---|---|
| Ajuste · `-op` | 57,4% (336) | **60,5% (248)** |
| Ajuste · OTC | 55,9% (93) | **58,0% (69)** |
| Conferência · `-op` | 53,7% (147) | **54,2% (107)** |
| Conferência · OTC | 48,1% (54) | **54,8% (42)** |

O "não esticado" foi o filtro mais estável do ajuste: deu de +2 a +4 pontos em todas as variações testadas (recuo de 0,8, 1,0 e 1,2 ATR; vela de comando, de força ou média).

**O que isso quer dizer.** A v2 ficou melhor que a v1 nos quatro testes, mas a melhora é pequena. Na conferência dos `-op`, ela ficou no **empate** (54,2% contra 54,3%). Como a v1, ela **ainda não provou que ganha do payout**. Fica em Observar até ter ~200 entradas ao vivo. Volume esperado: cerca de 3 de cada 4 entradas da v1.

## A3. Esticão rápido (`esticao`)

**Regra congelada em 08/11/2026.** Saiu de um estudo dos dados, sem partir da apostila. Pedido: uma estratégia própria que entregasse 70-80%. Não entrega, e fica só em **Observar**: a configuração recusa Operar até ela provar acerto ao vivo.

**A ideia.** Quando o preço dispara muito logo nos primeiros segundos do minuto, depois de uma vela grande, o disparo costuma ser exagero e volta um pouco até o fim da vela.

1. **ATR** = média das amplitudes das 14 últimas velas fechadas, contando a vela que acabou de fechar.
2. **Vela grande.** A vela que acabou de fechar tem amplitude de pelo menos **1,5 ATR**, de qualquer cor.
3. **Arma os dois lados** para a vela seguinte, medidos a partir da abertura dela: **PUT** em abertura + 1,5 ATR e **CALL** em abertura − 1,5 ATR. Vale o lado que tocar primeiro.
4. **GAP aborta:** a abertura não pode passar de 0,1 ATR do fechamento anterior.
5. **Gatilho só nos 10 s iniciais.** Entra **contra o disparo**, com vencimento no fim da vela.

**Como foi escolhida.** Velas de 5 s de 12 pares `-op` e 8 OTC. Escolha com os dias antes de 05/11 (`-op`) e 06/11 (OTC); conferência nos últimos 2 dias, vista uma vez só, depois de a regra ser escrita. O código do bot reproduz os números do estudo entrada por entrada.

| Teste | Entradas | Acerto |
|---|---|---|
| Escolha · `-op` (02 a 04/11) | 81 | 71,6% |
| Conferência · `-op` (05 e 06/11), entrada no fechamento da vela de 5 s do toque (como o bot mede) | 18 | **61,1%** (faixa 39-80%) |
| Conferência · `-op`, entrada no preço exato do gatilho | 18 | 44,4% |
| OTC, qualquer variação | ~40 | 40-50% |

**O que isso quer dizer.** Os ~72% da escolha não se repetiram, e a conferência tem poucas entradas para dizer algo. Ela depende de entrar rápido, porque o preço volta em segundos. No OTC não há esse efeito, então o que vale é o resultado nos pares normais.

**O que o estudo mostrou além dela.** No OTC, o preço de 5 s não tem memória: correlação entre um movimento e o seguinte de ~0,00, nenhuma ligação com o par `-op` e nenhuma volta à média de 2 a 60 min. Um modelo de aprendizado de máquina com ~50 indicadores acertou 82% nas suas entradas mais confiantes no período de treino e 50-56% nos 2 dias novos. A reversão A, que marcou 59% ao vivo no OTC em 07/11, deu 50,7% em 1.773 entradas nos 9 dias de OTC.

## A4. DeepLOB (IA) (`deeplob_iq`)

**De onde veio.** Do estudo "DeepLOB: um experimento acima de 70%" (E70-DL-001): o modelo público do artigo de Zhang, Zohren e Roberts acerta 75,35% no benchmark FI-2010. Esse número é de outro problema: livro de ofertas de ações (2010) e um rótulo suavizado de 3 classes (alta, estável, baixa). A IQ não fornece livro de ofertas, e o contrato paga só se o preço no vencimento passar da entrada.

**O rótulo explica boa parte dos 75%.** Nas nossas velas de 5 s (mais de 1 milhão de exemplos por mercado), o rótulo suavizado do artigo (média dos próximos preços contra a média dos anteriores) dá **73-75% com uma regra de uma linha** ("preço acima da média recente → alta"), até no OTC, que é sorteio. Metade da "média futura" já é conhecida no presente. No alvo do contrato, a mesma regra dá 50%.

**A regra (congelada em 08/11/2026).**
1. No fechamento de cada vela M1, a rede lê as **100 últimas velas de 5 s** (≈ 8 min). Por vela: abertura, máxima, mínima e fechamento menos o fechamento anterior, divididos pelo desvio da própria janela, mais o segundo do minuto.
2. Rede: a do artigo, adaptada para 6 features (convoluções, inception de 3 ramos e LSTM de 64). Probabilidade calibrada (Platt) num dia separado.
3. Probabilidade de subir ≥ 0,52: anota **CALL**; ≤ 0,48: anota **PUT**. Entrada no 1º preço da vela seguinte, com vencimento no fim dela.
4. **OTC: em silêncio.** Só M1. Só Observar: a configuração recusa Operar.
5. Ao vivo, as velas de 5 s são montadas com o preço lido a cada 0,5 s. Na carga do histórico, são as da IQ.

**Como foi medida.** Pré-registro, mesmo protocolo da especificação v1.0. Treino, calibração e seleção em dias separados; teste final só se a seleção aprovasse.

| Mercado | Treino | Calibração | Seleção | Resultado |
|---|---|---|---|---|
| OTC | 31/10 a 03/11 | 04/11 | 05/11 | Separação 0,500 (cara ou coroa); probabilidade calibrada igual para tudo (0,504): **NO_TRADE** |
| `-op` | 01 a 02/11 | 03/11 | 04/11 | Separação 0,493; limiar 0,52: **48,2% em 1.787** (faixa 45,9-50,6%): **NO_TRADE** |

Nos dois mercados, a rede só decorou ruído depois da 1ª época (erro caindo no treino e subindo na calibração). O teste final (05-06/11 e 06-08/11) não foi aberto. O código do bot reproduz o número da seleção entrada por entrada (48,2% em 1.787, 41 empates), e a rede em numpy dá a mesma saída da rede em PyTorch (diferença < 0,0000001).

**Por que está no bot.** Pedido do dono do bot, só para observar: é o teste em dados novos que os estudos exigem. Ela anota em média ~1 entrada por minuto somando os pares normais. Pesos em `backend/app/strategies/models/deeplob_iq_op.npz`; precisa do numpy no ambiente do servidor.

## A5. Bollinger + RCI (`bb_rci`), estudo de 09/11/2026

**A regra (padrão fixado antes de olhar os números).** Bandas de Bollinger 20 / 2 desvios e RCI de 9. A vela k chega na banda de cima com RCI ≥ +80: **PUT**. Chega na de baixo com RCI ≤ -80: **CALL**. Entrada no início da vela k+1, vencimento no fim dela (1 min). Código em `backend/app/strategies/bb_rci.py`, já no formato das estratégias do bot. O cálculo do estudo reproduz o código do bot sinal por sinal (8.144 de 8.144 no EURUSD-op).

**Como foi medida.** Velas M1 de 09/09 a 08/11, com 12 pares `-op` e 8 OTC. Escolha até 18/10 e conferência de 19/10 a 08/11. Grade de 96 variações (2/2,5/3 desvios, toque ou fechou fora, RCI 9 ou 14, nível 80 ou 90, com ou sem "RCI virando", contra ou a favor), escolhida só no período de escolha. Payout 0,85, ou seja, empate em 54,05%.

| | Escolha | Conferência |
|---|---|---|
| Padrão `-op` | 50,3% (63.035) | **50,0% (33.841)** |
| Padrão OTC | 50,2% (63.660) | **50,1% (33.388)** |
| Melhor variação `-op` (3σ fechou fora, RCI 9 ±90, a favor) | 53,2% (590) | 48,9% (380) |
| Melhor variação OTC (3σ toque, RCI 14 ±80, a favor) | 52,7% (915) | 52,5% (469); em 8 pares OTC nunca usados (31/10-09/11): **46,4% (181)** |

O padrão dispara muito: ~1 sinal a cada 8 min por par.

**Martingale.** Testado com o `RiskManager` do bot (valor do gale = recupera o ciclo + lucro de uma entrada), uma ordem por vez. Dois tipos: gale imediato (mesmo par, vela seguinte) e "com análise" (como o bot faz: o gale vai na próxima entrada). Período de conferência, entrada R$ 2:

| Padrão, sem stops | sem gale | G1 imediato | G2 imediato | G1 com análise | G2 com análise |
|---|---|---|---|---|---|
| `-op` | -R$ 2.063 | -R$ 2.833 | -R$ 3.544 | -R$ 2.742 | -R$ 3.849 |
| OTC | -R$ 3.094 | -R$ 4.420 | -R$ 6.664 | -R$ 4.243 | -R$ 5.921 |

Com o gale, a taxa de **ciclos** ganhos sobe (50% → 75% no G1 → 87% no G2), mas o acerto **por ordem** continua em 50% e o prejuízo cresce, porque cada ciclo perdido custa R$ 6,36 (G1) ou R$ 15,85 (G2). Na conta, com acerto p por ordem o martingale não muda o resultado por real apostado: -7,5% a 50%, zero a 54,05%, +1,8% a 55%. Ele só move mais dinheiro. Em sessões diárias com a config do usuário (stop win/loss R$ 20, 30 entradas, para em 4 perdas seguidas), o padrão termina vermelho em 11 a 13 de 18 dias nos `-op` e em 13 a 19 de 21 dias no OTC, em todos os modos. Só uma das 40 combinações ficou positiva: a melhor variação OTC com G1 imediato, +R$ 29,67 em 21 dias. Ela foi escolhida depois de ver o resultado e acerta 53,4% por ordem, abaixo do empate. Nos 8 pares OTC nunca usados, a mesma combinação fez -R$ 13,35 sem stops.

**Conclusão.** Bollinger + RCI em M1 é cara ou coroa nos dois mercados, e o martingale só aumenta o prejuízo.

**No bot (09/11/2026), a pedido do dono, apesar do estudo.** Começa Desligada e pode Observar ou Operar (não está travada em Observar como o esticão e o DeepLOB). Entra no 1º preço da vela seguinte ao sinal, como o DeepLOB, e dispara bem mais que as outras: ~1 entrada a cada 8 min por par. Com o martingale ligado, dá para deixar só ela usando o gale (seção B.5).

## A6. Bollinger + RCI v2 (`bb_rci_v2`), criada em 09/11/2026, **só Observar**

**A ideia (do dono do bot).** Somar confluências à Bollinger + RCI para deixá-la mais assertiva, medindo **daqui para frente, no ao vivo**, sem usar velas antigas para decidir. Cada indicador tem um papel que combina com a aposta contra da Bollinger:

| Confluência | Pergunta | A favor quando |
|---|---|---|
| Gator (Bill Williams; Alligator 13/8/5 da mediana, deslocadas 8/5/3) | o mercado está de lado? | as duas barras vermelhas na vela do sinal (as médias se juntando, sem tendência acelerando) |
| MACD 12/26/9 | o empurrão está cansando? | CALL: histograma negativo e maior que o da vela anterior; PUT: o espelho |
| Weis Wave (ondas de fechamento com virada de 0,5 ATR) | o movimento está perdendo combustível? | a onda mais recente na direção do movimento tem menos volume que a anterior na mesma direção |
| Fractal (5 velas, só confirmados) | tem um piso ou teto ali? | o toque fica a até 0,5 ATR do último fractal na direção (só anotado, não decide) |

**A regra (congelada em 09/11/2026; mudar = outra versão).** A v2 entra quando a v1 entra **e** Gator dormindo **e** MACD virando **e**, onde há volume, Weis Wave mais fraca. A IQ manda volume (de ticks) só nos pares normais; no OTC vem zero, então lá o Weis não conta. Entrada e vencimento iguais aos da v1. Código em `backend/app/strategies/bb_rci_v2.py` e `bb_rci_confluencias.py`.

**O que fica gravado.** Todo sinal da v1 (que continua decidindo igual) passa a ter as quatro marcações nos detalhes (`extra.confluencias`: true, false ou null = sem dados). Assim dá para avaliar depois cada indicador e outras combinações.

**Frequência esperada.** Contando só quantas vezes entraria (sem olhar resultado) nas velas de 09/11: ~0,3% dos sinais da v1 nos pares normais e ~1,5% no OTC. No sinal da Bollinger o preço acabou de andar forte "em fila", que é justamente quando o Gator está acordado e o MACD acelerando; por isso as confluências raramente concordam.

**A régua (combinada antes de qualquer resultado).** A v2 passa para Operar se, nos mesmos dias ao vivo, tiver pelo menos **5 pontos a mais de acerto por entrada que a v1** (com 150+ entradas da v2), ou **menos de 1 ciclo de G2 perdido a cada 11**. Análises secundárias (não decidem sozinhas): "2 de 3" (~8% dos sinais nos pares normais) e cada indicador sozinho, a partir das marcações gravadas na v1.

## B. Como operar no BotBene

### 1. Configuração (uma vez)

Na tela **Configuração**:
- **Modo**, um dos quatro:
  - **Só sinais:** registra as entradas e não manda ordem.
  - **Aprovação:** cada entrada aparece na tela e só vai para a conta demo se você aprovar.
  - **Automático:** o bot entra sozinho na conta demo, sem perguntar e sem cartão na tela. Bom para deixar rodando e juntar resultado.
  - **Automático com veto:** entra sozinho, mas o cartão aparece com bipe já aprovado. Se você não fizer nada, a ordem sai no gatilho; se clicar em "Cancelar esta entrada", não sai.
- **Estratégias:** cada uma fica em **Desligada**, **Observar** (anota e mede, sem mandar ordem) ou **Operar** (pode mandar ordem, conforme o modo). Deixe só a **retração no comando** em Operar.
  - Uma ordem por par e vela: CALL e PUT juntos se anulam; no mesmo sentido, vale a de mais confluências.
  - Ligar ou desligar vale no próximo início do bot; trocar entre Observar e Operar vale na hora.
- **Ajuda visual no gráfico:** linhas e setas do LDP v1.3 e setas do WIKI PRO. Só desenham: nunca decidem entrada e não entram nas estatísticas.
- **Pares:** os `-op`, até 20. Hoje são EURUSD, GBPUSD, USDJPY, AUDUSD, EURJPY e EURGBP.
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

Quando uma estratégia arma uma entrada, aparece no topo da tela, em qualquer página, uma **linha** com **bipe** (desde 09/11/2026; antes era um cartão grande com um gráfico próprio). Isso vale nos modos aprovação e automático com veto.
- **Na linha:** a direção, o par, a estratégia, o preço do gatilho, o **preço agora e quantos pips faltam** (quando o gráfico está no par), o valor (com o selo do gale), o vencimento, a contagem regressiva da janela e os botões **Aprovar** e **Rejeitar** (ou **Cancelar entrada** no automático com veto).
- **A análise é no gráfico principal**, que mostra a linha tracejada do gatilho ("CALL armado" / "PUT armado"):
  - quando surge um pedido, o gráfico vai sozinho para o par dele;
  - se você está **analisando outro par** (trocou de par ou mexeu no gráfico no último minuto e meio), ele não troca: a linha pergunta **"Ir para o gráfico desta entrada?"**, com **Ir** e **Ficar aqui**. Depois de "Ficar aqui", o botão **Ver no gráfico** leva até ele quando quiser.
- **Vários pedidos ao mesmo tempo** viram várias linhas. O mais urgente fica destacado e é o que decide o gráfico.
- **Resultado:** ordem enviada (com o resultado) ou recusada pela corretora vira um **aviso pequeno no canto de baixo**, que some sozinho. Pedido que terminou sem ordem (o preço não veio, a gestão de risco barrou, você cancelou) não vira aviso: fica na lista de Ordens e em "Últimos setups".
- No **gráfico expandido**, as linhas ficam embaixo da coluna da direita, sem cobrir o gráfico nem os botões da entrada manual, e o aviso fica no canto de baixo à esquerda.
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
  - mais uma perda poderia passar do stop loss (contando o pior caso das ordens abertas). Com **"Stop loss acompanha o lucro"** ligado (desde 10/11/2026), o limite conta do melhor resultado da sessão, e não do Iniciar: com stop loss de 50, a sessão que chegou a +80 para antes de cair abaixo de +30. Sem lucro ainda, vale igual (−50 desde o Iniciar); o limite só sobe;
  - atinge o limite de entradas;
  - ou encosta em X perdas seguidas.
- **Martingale com análise.** Fica desligado por padrão e a recomendação é manter assim:
  - depois de uma perda, só a próxima entrada **válida e aprovada** vale mais (nunca entra às cegas na vela seguinte);
  - o valor é calculado para recuperar o ciclo, com até 2 gales;
  - **você escolhe quais estratégias usam o gale** (desde 09/11/2026), e **cada marcada tem o seu ciclo**: a perda de uma não deixa a entrada da outra mais cara, a vitória de uma não fecha o ciclo da outra, e cada ciclo tem uma ordem aberta por vez. As não marcadas entram sempre com o valor normal. Stop win, stop loss, máximo de entradas e perdas seguidas contam todas juntas, e o stop loss reserva os gales que ainda podem vir em todos os ciclos abertos;
  - até a noite de 09/11/2026 as marcadas dividiam um ciclo só, com uma ordem aberta por vez entre todas. Com a Bollinger + RCI e a retração no comando marcadas, a Bollinger entrava no início de quase toda vela (58 ordens em 58 minutos na sessão das 17:28) e a retração, que dispara de 3 a 12 s depois, achava a vaga ocupada: 6 dos 8 sinais dela depois das 13:38 não viraram ordem;
  - **stop de ciclo** (opcional): para de abrir entradas depois de X ciclos perdidos inteiros na sessão (perdeu a entrada e todos os gales), somando todas as estratégias;
  - se a próxima entrada do gale cai logo na vela seguinte à perda, o bot **espera o resultado** da ordem anterior (ele chega ~1 s depois da vela abrir) dentro da janela de entrada, e a ordem sai com o valor certo. Se a janela fechar antes, a entrada fica bloqueada, nenhuma ordem sai, e ela aparece no histórico de ordens como bloqueada, com o motivo (desde 09/11/2026; antes ela era sempre bloqueada);
  - ele não melhora o acerto, só concentra a perda. Com US$ 2 e 1 gale, perder o ciclo custa US$ 6,39 e apaga quase 4 vitórias de US$ 1,68.
  - **contar por ciclo de gale** (caixa no Painel e no Desempenho; na tela Entradas aparece sozinho): a % é de **ciclos ganhos** (ganhou na entrada ou em algum gale) sobre os ciclos com resultado; ciclo ganho = 1 vitória, ciclo perdido = 1 derrota, e quantas ordens ele perdeu aparece no texto ao lado. Como o ciclo perdido custa a entrada e todos os gales, o mínimo é alto: com G2 e payout de 83%, 16,14 ÷ (16,14 + 1,66) = **90,7%** (até 10/11 a conta contava cada ordem perdida, com mínimo de 76,4%). Os números do topo ficam só com as estratégias que usam gale (misturar com quem conta por ordem não tem mínimo único); cada estratégia mostra o mínimo dela, e o resultado em dinheiro do Painel é o de todas. O número que conversa direto com o dinheiro é **"1 ciclo perdido a cada N"**: com G2 e payout de 83%, empata em 1 a cada ~10,7.

### 6. Quando reavaliar

Com 10 ou 30 entradas o resultado é sorte, para o bem ou para o mal: há dias de 40% e dias de 66% com a mesma regra. Reavalie com **~200 entradas da retração no comando**. Os números de cima do Painel contam só as estratégias em Operar; as que só observam aparecem separadas no placar.

## C. As outras regras

A estratégia de marcações roda se você a colocar em Observar ou Operar. O LDP v1.3 e o WIKI PRO são scripts: no bot, só desenham no gráfico. As regras e os números deles abaixo vêm da ferramenta de pesquisa (`python -m app.tools.research`), que continua medindo os scripts para comparação.

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

## 2b. Leitura do estudo (`backend/app/ldp/reading.py`)

Camada que lê o gráfico como as análises das págs. 162-220: **"Identifique um lote passado. Dentro desse lote localize e marque a nova alta / nova baixa + nova posição."** Só lê: nenhuma estratégia usa isto ainda. Aparece no Painel em **mostrar a leitura do estudo**.

| Peça | Regra | Páginas |
|---|---|---|
| Lote | Velas da mesma cor. Abre por reversão, comando ou depois de um fechamento de preço. Fecha por reversão confirmada, fim de taxa ou rompimento | 121-123 |
| Rompimento do lote | O **corpo** passa da abertura da vela que abriu o lote | 115, 123 |
| Nano-lote | Uma vela de outra cor seguida da cor do lote. **Não fecha o lote** | 126, 133, 182 |
| Nova alta/baixa | 1º pavio depois de o corpo fechar além da máxima/mínima anterior ao lote | 97, 102, 129 |
| Nova posição | A vela seguinte, na mesma cor | 113, 115, 129 |
| Região central | Do pavio da nova alta/baixa até a projeção da nova posição; sem projeção, a abertura dela | 102, 129-130, 164 |
| Indecisão (dupla, tripla, futuro) | O **corpo inteiro** dentro do pavio anterior. A região fica sem lado até um corpo romper; depois, ganha o lado de quem rompeu | 106-112 |
| Vela de força | Pavio na abertura, corpo de impulso. Região no corpo: rompeu, terminou dentro ou retraiu nela | 11-16, 69-70, 138 |
| Defesa | Corpo do 1º candle da reversão, depois de confirmada | 149-152 |
| Vela de força na defesa | Vela de força que chega numa região contrária e fecha nela, sem romper: primeiro registro, nova posição, comando, taxa dividida etc. A leitura vira para o outro lado. Só rótulo, ainda sem entrada | 153, 211, 218 |
| Transferência / desinstalação | Pavio alinhado com um pavio recente, sem nada passar entre eles: mesma cor / cor diferente | 134-135 |
| Cenário | Topos e fundos (o melhor), tendência (fluxo) ou consolidado (não operar) | 223 |

**Regiões em uso:** só as dos 2 lotes mais recentes de cada lado. Em cada lote, a região central e as de indecisão sempre ficam; das outras (comando, taxa dividida, nano-lote), só as 2 mais recentes. Máximo de 12 ao mesmo tempo. Uma região sai quando um corpo fecha além dela (pág. 115).

**Por que isso importa.** No mapa antigo (seção 3), 67% das velas "travavam" em alguma marcação, então travar não dizia nada. Contando só frequência nos 12 pares `-op` (~115 mil velas), sem olhar resultado, a leitura nova dá: trava em qualquer região 26,5%; trava na região de nova alta/baixa + nova posição 4,7%; trava em região de dupla/tripla 6,1%. Indecisão caiu de ~24% para ~12% das velas, e o cenário ficou em 65% topos e fundos, 32% consolidado e 3% tendência.

**Ainda a confirmar com o dono do estudo, no gráfico:** a definição numérica do macro-lote (págs. 124, 128) não entrou nesta versão; os números do cenário e a tolerância de alinhamento são valores iniciais.

## 2c. Estratégias da leitura do estudo (`backend/app/strategies/recipes.py`)

**Regras congeladas em 06/11/2026, antes de qualquer medição.** Daqui em diante, nenhum número delas muda olhando o resultado; uma versão nova vira outra estratégia, com outro nome. Todas armam no fechamento da vela e entram na vela seguinte se o preço tocar a marcação nos primeiros 15 s (pág. 162), com vencimento no fim dela. Abertura em GAP aborta (pág. 28).

**Vela de força** (para as três): pavio na abertura, corpo ≥ 50% da amplitude e amplitude ≥ 1,2 × a média das 14 velas anteriores (pág. 11-16). **Travou:** fechou a até 0,15 ATR da borda da região, sem passar dela.

| Estratégia | Arma quando | Marcação e sentido | Exige |
|---|---|---|---|
| **Retração no lote** (pág. 162-172) | Existe uma região de nova alta/baixa **+ nova posição** do lado certo, a até 0,6 ATR do fechamento | Borda de cima da região de compra (CALL) ou de baixo da de venda (PUT) | Nada além da região; confluências são anotadas para medir |
| **Reversão A · força trava** (pág. 30, 44, 153, 197, 218) | Uma vela de força fechou travada numa região contrária ativa (primeiro registro, comando, taxa dividida, indecisão etc.) | Borda que ela tocou; entra **contra** a vela de força | 2 confluências |
| **Reversão B · força rompe indecisão** (pág. 106-119) | Uma dupla/tripla posição ou futuro foi rompida pelo corpo de uma vela de força ou de um comando, há até 5 velas, e o preço está a até 0,6 ATR da região | Borda da região do lado de quem rompeu; entra **a favor** de quem rompeu | 2 confluências |

**Confluências** (1 ponto cada, contando as regiões ativas a até 0,15 ATR da marcação, do lado da entrada):
1. marcação de comando ou de taxa dividida (pág. 26, 41);
2. dupla/tripla posição ou futuro (pág. 110, 112);
3. primeiro registro + nova posição (pág. 102, 162);
4. duas ou mais marcações juntas;
5. espaço até a próxima barreira contrária ≥ 0,8 ATR (pág. 177, 199, 201).

**Como medir** (plano, Etapa 3): payout de 84%, empate 54,3%. Primeira olhada nos dados até 03/11/2026; **confirmação** de 04/11 em diante, que nenhuma regra viu. Só a confirmação decide. O cenário (pág. 223), o horário e cada confluência são anotados para análise, sem virar filtro antes de passar pela confirmação.

**Resultado (medido em 06/11/2026, 12 pares `-op`, velas de 5 s de 26/10 a 06/11):**

| Estratégia | Primeira olhada (até 03/11) | Confirmação (04 a 06/11) |
|---|---|---|
| Retração no lote | 50,8% (9.119) | 51,0% (4.089) |
| Reversão A · força trava | 51,0% (2.171) | 51,1% (960) |
| Reversão B · força rompe indecisão | 49,3% (2.094) | 52,6% (871) |
| *Retração no comando (referência)* | *56,5% (742)*¹ | *53,9% (243)* |

¹ Inclui os dias usados para escolher a regra em 03/11, então não é uma olhada limpa.

**Conclusão:** as três, como foram escritas, **ficam abaixo do empate nos dois períodos** e não devem operar. Mais confluências não melhoraram o acerto. Os grupos que pareceram bons num período não se repetiram no outro: espaço na reversão A deu 54,1% na primeira olhada e 50,3% na confirmação; primeiro registro na reversão B deu 48,5% e depois 58,2%. Isso é oscilação, não vantagem. Elas também entram demais (a retração no lote, ~95 entradas por par por dia), o que mostra que a leitura automática ainda não é seletiva como a do estudo. Antes de qualquer versão nova, a leitura precisa ser conferida no gráfico por quem opera o estudo.

## 2d. Score LDP v1: o combo (`backend/app/strategies/score.py`)

**A ideia (do dono do bot).** Em vez de escolher uma estratégia contra a outra, todas rodam juntas e montam um score. Quando os padrões positivos coincidem, entra; quando não, pula e diz na tela o porquê. O foco é acerto: o gale fica de fora até o score provar acerto alto de forma consistente.

**Regras congeladas em 06/11/2026.** Nenhum número muda olhando o resultado. Uma melhoria vira outra versão (`score_ldp_v2`), com as regras escritas antes de medir, e só é comparada em dados posteriores ao congelamento dela.

1. A cada vela fechada, as cinco estratégias de dentro da vela (retração no comando, marcações, retração no lote, reversão A e B) armam ou não. Cada lado ganha pontos: +1 por estratégia armada, +1 por confluência do estudo (seção 2c), +1 se a vela não rompeu a máxima/mínima das 10 anteriores, +1 em topos e fundos, −1 em consolidação (pág. 223), −1 por estratégia armada do outro lado. Fica o lado com mais pontos; empate pula.
2. **Base:** a retração no comando precisa estar armada no lado escolhido (pág. 27, 162).
3. **Quatro padrões, 1 ponto cada; entra com 3 ou 4:**
   - marcação de comando ou de taxa dividida (pág. 26, 41);
   - o comando não rompeu a máxima (CALL) ou a mínima (PUT) das 10 velas anteriores;
   - espaço de pelo menos 0,8 ATR até a próxima barreira contrária (pág. 177, 199, 201);
   - recorrência: o combo acertou pelo menos 6 das últimas 10 entradas naquele par. Não vem da apostila: é desempenho recente, e a tela mostra separado.
4. **Gatilho:** o primeiro toque, nos primeiros 15 s da vela seguinte, em qualquer marcação das estratégias do lado escolhido. GAP aborta (pág. 28). Vencimento no fim da vela.

A recorrência conta todas as entradas do combo no par (o lado escolhido em cada vela, entre ou não). Por isso o score vê os primeiros 15 s de toda vela: na carga do bot e na pesquisa, pelas velas de 5 s (o bot busca desde 2 h antes da meia-noite); ao vivo, pela vela em formação.

**Na tela.** Quando arma, o cartão mostra os quatro padrões com ✓ e ✗. Quando um comando aparece e o score pula, a linha "Pulou" em **Últimos setups** diz quantos padrões passaram e quais faltaram, por exemplo: `Pulou · 2 de 4 · ✓ marcação · ✗ comando dentro das 10 velas · ✓ espaço · ✗ recorrência (5 de 10)`.

**Como foi escolhido (06/11/2026).** Entradas com a retração no comando, 12 pares `-op` e 8 OTC, payout de 84%, empate em 54,3%:

| Período | Entradas | Acerto |
|---|---|---|
| `-op` até 03/11 (usado para escolher os padrões) | 128 | 71,1% |
| `-op` 04 a 06/11 | 40 | 62,5% |
| OTC 27/10 a 06/11 | 49 | 63,3% |
| Fora do período de escolha, somado | 89 | **62,9%** (faixa 52,5–72,2%) |

O código do bot reproduz essa medição entrada por entrada (as mesmas 223 entradas, com os mesmos resultados). Somar todos os pontos com o mesmo peso **não** funcionou (~51% em qualquer nota); o que separou foi partir da retração no comando e exigir os padrões a favor: 0 padrão 45%, 1 padrão 52%, 2 padrões 55-60%, 3 padrões 71-73% (poucas entradas).

**Gale.** Testado com 1 e 2 níveis, na vela seguinte e na próxima oportunidade (qualquer par, mesmo par, mesmo par e lado, entrada forte). A entrada depois de uma perda acerta igual às outras (71,4% em 70 contra 65,3%), então o gale só aumenta a aposta: não muda o acerto e atrapalha a leitura. Fica desligado até o score provar acerto alto de forma consistente.

**Validação.** `python -m app.tools.score_check` mede o score com a mesma classe do bot, nas velas de 5 s guardadas a partir de 07/11/2026, e mostra o placar ao vivo. Volume esperado: ~75 entradas por semana nos 12 pares `-op` e ~32 nos 8 OTC. Se o acerto real for 65%, ~85 entradas já bastam para ficar acima do empate mesmo no pior caso; para afirmar mais de 60%, ~350.

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

## 7b. Revisão de 08/11/2026: por que as marcações e as estratégias do estudo não funcionam

**Dados.** 20 pares com velas de 5 s: 12 `-op` de 02 a 06/11 e 8 OTC de 31/10 a 08/11. São ~176 mil velas e ~76 mil setups armados pelas estratégias v1, rodadas como o bot roda.

**Método.**
- **Ajuste:** antes de 05/11.
- **Conferência:** de 05/11 em diante. Foi vista uma vez só, depois de as regras novas serem escritas.
- **Simulador conferido contra o bot ao vivo:** das 2.071 entradas de 07 e 08/11, 98% aparecem nos dois. O resultado é o mesmo em 93%, e a diferença mediana no preço de entrada é de 0,07 ATR.

**As v1, no ajuste:**

| Estratégia | Entradas | Acerto | Dispara em |
|---|---|---|---|
| Marcações | 3.435 | 51,0% | 36% dos armados |
| Retração no lote | 8.320 | 50,4% | 42% |
| Reversão A · força trava | 2.058 | 49,9% | **94%** |
| Reversão B · força rompe indecisão | 1.564 | 51,0% | 38% |
| *Retração no comando (referência)* | *419* | *57,0%* | *5%* |

**Diagnóstico.**
1. **A marcação fica colada na abertura.** A distância mediana até o fechamento é de 0,1 a 0,2 ATR, então o preço toca quase sempre. Entrar perto da abertura dá o mesmo que os scripts de fechamento: cara ou coroa. Na reversão A, a marcação é a própria borda onde a vela de força fechou, e por isso ela entra praticamente na abertura em 94% das vezes.
2. **Nada da leitura separa as entradas boas das ruins:** confluências (3, 4 ou 5 dão o mesmo acerto), força da marcação, tipo de gatilho, cenário, horário, tendência.
3. **A vantagem vem de outro lugar: entrar contra um movimento forte nos 15 s iniciais.** Nos `-op`, com recuo de 0,8 ATR em qualquer vela e para qualquer lado, dá 54,4% (3.823). Depois de um comando, sobe para 57,4% (326). É o princípio da retração da apostila, e o comando é a única leitura que comprovadamente aumenta o efeito.
4. **Com esse gatilho, a leitura das outras estratégias não acrescenta:** marcações 51,8% (199), retração no lote 53,0% (317), reversão B 53,4% (88). Todas abaixo dos 54,4% da referência sem estratégia nenhuma.
5. **`-op` × OTC.** O efeito do item 3 aparece nos `-op` e quase some nos OTC. Com recuo de 1,0 ATR, qualquer vela, dá 55,3% nos `-op` e 51,4% nos OTC. Os preços OTC são gerados pela própria IQ, fora do mercado. **Nos OTC, nenhuma regra mostrou vantagem medida.**

**Tentado e reprovado.**
- **Reversão A v2 (esticão depois da força).**
  - **Regra:** vela de força que fez máxima ou mínima nova das 10 anteriores; nos 15 s iniciais da seguinte, o preço estica 1,0 ATR a favor dela; entra contra.
  - **Resultado:** 64,5% (169) no ajuste dos `-op`, mas **48,6% (105) na conferência**.
  - **Por que reprovou:** era o melhor de muitos recortes e não se repetiu. Não entrou no bot.
- **Marcações, retração no lote e reversão B exigindo recuo de 0,8 ATR até a marcação.** Ficaram abaixo da referência já no ajuste (item 4). Não há versão nova delas.

**Ao vivo, 07 e 08/11, conta real, pares OTC:**

| Estratégia | Acerto |
|---|---|
| Retração no lote | 47,8% (1.282) |
| Marcações | 49,4% (540) |
| Reversão B | 48,0% (223) |
| Reversão A | 59,1% (318) |
| Retração no comando | 65,4% (26) |
| Score LDP v1 | 2 de 5 |

A reversão A foi bem nesses dois dias, mas na pesquisa oscilou entre 48% e 54%. Com seis estratégias medidas ao mesmo tempo, é esperado que uma pareça boa por acaso. Fica em Observar.

**Recomendações.**
- **Desligar** marcações, retração no lote e reversão B. Elas só enchem a tela e o banco de entradas sem vantagem.
- **Reversão A em Observar.**
- **Operar nos pares `-op`** quando estiverem abertos.
- **Conflito entre estratégias:** se duas estratégias em **Operar** armarem CALL e PUT na mesma vela, o bot cancela as duas (`_order_candidates`).

## 8. Ainda não implementado (próximas fases)

- Cenário (topos e fundos / tendência / consolidação) e macro-lote como filtros medidos na pesquisa.
- Transferência de preço e desinstalação (pág. 134-135) — a definir com exemplos reais.
- Filtro candidato "comando que não rompeu a máxima/mínima das 10 velas anteriores" (69% / 63% com ~50 entradas cada): testar em semanas novas de dados.
- Pausa automática por desempenho.

(Já feito: vários pares ao mesmo tempo; payout mínimo e horário de operação.)
