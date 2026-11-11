# Padrão Moratz

Começou em 10/11/2026. A ideia é criar um padrão de velas **nosso**, sem usar padrão de mercado, sem prometer nada e sem expectativa:
- lemos as velas juntos;
- percebemos comportamentos do tipo "quando acontece X, sobe ou desce";
- testamos com honestidade.

Se não der certo, vai para o caderno e tentamos de novo.

São duas inteligências trabalhando juntas. O Moratz traz o olho. O Claude transforma o que ele vê em regra exata, mede e avisa quando o número não sustenta. O Claude também lê as velas, pelo mapa da máquina.

- Caderno de tudo o que já foi tentado: [caderno.md](caderno.md)
- Versões congeladas e pré-registros: `versoes/`, criada no primeiro congelamento
- Regras escritas: [regras/](regras/), com o formato em [regras/modelo.json](regras/modelo.json)
- Código: [backend/app/research/moratz/](../../backend/app/research/moratz/), linha de comando em [backend/app/tools/moratz.py](../../backend/app/tools/moratz.py)
- Mesa de Leitura (página privada): https://claude.ai/artifact/79j578gpYgZv7GgfVjMnJW. O código fica em [mesa/mesa_de_leitura.html](mesa/mesa_de_leitura.html)

## O combinado

1. **Vocabulário nosso.** Nada de martelo, engolfo, Bollinger ou RSI. As velas são descritas pelos traços do dicionário abaixo.
2. **Duas trilhas que não se misturam.** `-op` (mercado normal) e OTC têm dados, testes e caderno próprios, e os números nunca se somam. Uma ideia de uma trilha só vai para a outra como hipótese nova.
3. **Sorteio contra a armadilha.** Toda medida também roda com os resultados embaralhados dentro de cada par e dia, onde não existe padrão nenhum. Se o acaso faz igual com frequência, a ideia cai.
4. **O passado descobre, o futuro julga.** Os ~60 dias de velas já foram muito garimpados em estudos anteriores. Cada versão é congelada (regra, pares, data e hash), e o veredito vem só de velas posteriores ao congelamento.
5. **Caderno.** Toda tentativa é registrada, inclusive as que falharam, com quantas variações foram olhadas.
6. **Réguas fixadas antes de qualquer resultado** (veja "Períodos e portas").
7. **Sem dinheiro.** O Padrão Moratz não manda ordem. Só entra no bot em Observar, e só depois de passar no futuro.
8. **A regra é código.** O Claude ajuda a especificar, auditar e explicar, mas não decide entrada ao vivo.

## Ficha da operação v0

| Definição | Padrão Moratz v0 |
|---|---|
| Instrumento | IQ Option, com trilha `-op` e trilha OTC separadas. Velas M1 da própria IQ |
| Modalidade | Alta/baixa (CALL/PUT), binária ou digital, 1 minuto |
| Tempos gráficos | Gatilho em M1. M5 e M15 são montados do M1, só com velas maiores completas e já fechadas no instante da decisão |
| Decisão | No fechamento da vela k, só com velas até k |
| Entrada | Abertura da vela k+1. Ao vivo, a ordem sai ~1 s depois (mediana medida de 1,16 s) |
| Vencimento | Fechamento da vela k+1, que precisa vir logo depois de k, sem buraco |
| Resultado | Mesma `judge()` do bot: CALL ganha acima da entrada, PUT abaixo. Igual é empate e fica fora da conta |
| Payout e empate | 0,83 nas duas trilhas, o realizado nas ordens do bot até 10/11. Empate = 1/(1+0,83) = **54,6%**. Pares que pagam menos de 0,75 ficam fora: EURAUD, USDCAD e USDCHF `-op`, que pagavam 0,50 |
| Limitações | A abertura da vela aproxima o preço contratado: nas ordens reais do bot ela concordou em 87% dos casos. Por isso a conferência (E) e o futuro também medem a entrada após a 1ª vela de 5 s, igual ao bot, onde houver esse dado (desde ~01/11). O volume só existe no `-op` (contagem de ticks); no OTC vem zerado |

## Dicionário Moratz v0

A "unidade" é a amplitude mediana das 20 velas **anteriores** a k. Uma vela só entra quando as 20 anteriores estão sem buraco.

| Traço | O que mede | Cálculo |
|---|---|---|
| `tamanho` | vela grande ou pequena para o momento | amplitude ÷ unidade |
| `corpo` | quanto da vela é corpo | \|fech − abert\| ÷ amplitude |
| `fecho` | onde fechou dentro da vela | (fech − mín) ÷ amplitude; 0 = no fundo, 1 = no topo |
| `pavio_cima`, `pavio_baixo` | sobra acima e abaixo do corpo | ÷ amplitude |
| `cor` | subiu, desceu ou ficou parada | +1, −1, 0 |
| `fila` | velas seguidas da mesma cor | com sinal: +3 = 3ª verde seguida |
| `lugar` | onde o preço está na faixa das últimas 20 velas | (fech − mín20) ÷ (máx20 − mín20) |
| `viagem` | quanto andou nas últimas 5 velas | (fech_k − abert_k−4) ÷ unidade |
| `salto` | buraco entre o fechamento anterior e a abertura | ÷ unidade |
| `ctx5_cor`, `ctx5_mov` | cor e movimento da última M5 fechada | movimento ÷ unidade |
| `ctx15_cor`, `ctx15_mov` | cor e movimento da última M15 fechada | movimento ÷ unidade |
| `hora`, `dia` | hora de Brasília e dia da semana da entrada | 0–23; 0 = segunda |
| `vol_rel` | volume relativo, só no `-op` | volume ÷ mediana das 20 anteriores |

Uma hipótese é uma **combinação de faixas desses traços** mais uma direção: `call`, `put`, `contra_cor` (contra a cor da vela k) ou `a_favor_cor`. Traços novos que surgirem das leituras entram aqui com data e com a versão do dicionário.

## Períodos e portas (horário de Brasília)

**Períodos**
- **D, descoberta: 09/09 a 18/10/2026.** Lemos, mapeamos, escrevemos e ajustamos à vontade. A Mesa de Leitura sorteia momentos só daqui.
- **E, conferência: 19/10 a 09/11/2026.** Cada versão de regra roda aqui **uma vez**, com trava pelo hash da regra.
  - Em linha separada, só como informação, aparecem os pares que D nunca viu, que só existem desde 31/10–02/11.
  - Mudar a regra depois de olhar o E vira versão nova, e isso fica registrado no caderno.
- **F, futuro: velas a partir do congelamento.**
  - Até 100 sinais, o acerto fica tampado.
  - Aos 100, ele aparece só para cair: abaixo de 50% encerra.
  - Aos 200 sai o veredito. Na zona do meio, junta até 500.

**Portas**
- **Para ir ao E**, em D:
  - n ≥ 150 e acerto ≥ 57%;
  - o sorteio fez igual ou melhor em ≤ 1% de 200 vezes;
  - ≥ 2/3 dos pares acima de 50%;
  - ≥ 7 sinais por dia na trilha, para o futuro chegar a 200 em ~6 semanas.
- **Para congelar**, em E: acerto acima do empate (54,6%) com n ≥ 100 e ≥ 2/3 dos pares acima de 50%.

**Veredito no futuro**
- **Passa** se o limite inferior de Wilson (95%) ficar acima do empate com n ≥ 200, cerca de 61% em 200 ou 59% em 500. É a mesma régua de [estrategia.md](../estrategia.md).
- **Cai** se ficar abaixo de 55% em 200 sinais.

## O ciclo

1. **Lemos juntos**, por três caminhos:
   - a Mesa de Leitura, às cegas;
   - a conversa: o Moratz descreve o que vê na IQ, e `ver` mostra a vela com a régua;
   - o mapa da máquina.
2. O Claude escreve a hipótese como regra em `regras/M-xxx.json`, e o Moratz confirma se é isso mesmo.
3. `testar` mede em D, com sorteio, e registra no caderno.
4. Passou a porta: `conferir` mede em E, uma vez.
5. Passou de novo: `congelar` cria a vX.Y e o pré-registro.
6. `futuro` acompanha até o veredito.
7. Passou no futuro: entra no bot em **Observar**, para conferir o ao vivo. Caiu: fica no caderno e partimos para a próxima ideia.

Mais adiante, um lote às cegas tirado de E, visto uma vez, vai medir se o olho do Moratz funciona em velas em que ele não treinou.

## Comandos

Rodar dentro de `backend/`, com o ambiente do bot:

```bash
.venv/bin/python -m app.tools.moratz base --importar        # traz o M1 novo do arquivo do servidor e mostra a base
.venv/bin/python -m app.tools.moratz mapa                   # mapa da máquina em D (as duas trilhas, ~1 min)
.venv/bin/python -m app.tools.moratz mesa                   # momentos às cegas para a Mesa de Leitura
.venv/bin/python -m app.tools.moratz ver EURUSD-op "14/10/2026 10:32"   # uma vela com a régua
.venv/bin/python -m app.tools.moratz testar ../docs/padrao_moratz/regras/M-001.json --variacoes 3 --nota "..."
.venv/bin/python -m app.tools.moratz conferir ../docs/padrao_moratz/regras/M-001.json
.venv/bin/python -m app.tools.moratz congelar ../docs/padrao_moratz/regras/M-001.json --versao 1.0
.venv/bin/python -m app.tools.moratz futuro --importar
.venv/bin/python -m app.tools.moratz baixar --trilha otc --dias 30 --confirmo   # segundo login na IQ, conta de treino
```

- `ver` esconde o que veio depois quando a data é do período E.
- `baixar` só roda com o OK do dono da conta. Ele é necessário porque, desde 09/11, o servidor só arquiva os pares da configuração, que são todos `-op`. As velas OTC do futuro precisam vir daqui. A IQ guarda ~60 dias de M1.

## A Mesa de Leitura

Ela fica em https://claude.ai/artifact/79j578gpYgZv7GgfVjMnJW e é privada: só o dono abre.

**Abas**
- **Às cegas:** um lote de 300 momentos por trilha, sorteados de D.
- **Mapa da máquina**
- **Caderno**
- **Minhas leituras:** traz a tabela de leituras e as ideias soltas.

**Onde ficam as leituras:** no banco da própria página, nas coleções `leituras` (um documento por momento, com id igual ao do momento, por exemplo `op-001`) e `ideias`. O Claude lê esse banco pela ferramenta `ArtifactData`, com `list` na coleção `leituras`.

**Para republicar** com lote novo, mapa novo ou caderno atualizado:
1. Rode `mesa`, `mapa` e `pagina`.
2. Publique de novo `docs/padrao_moratz/mesa/mesa_de_leitura.html` na mesma URL, mandando como arquivos de apoio:
   - `momentos_op.json` e `momentos_otc.json`, de `data/moratz/mesa/`;
   - `mapa_op.json` e `mapa_otc.json`, de `data/moratz/mapa/`;
   - `caderno.json`, de `data/moratz/mesa/`.
3. Para um lote novo, rode `mesa --lote 2`. Ele faz outro sorteio e gera ids como `op-L2-001`, que não colidem com as leituras do lote 1, guardadas pelo id do momento.

## Onde ficam os dados (fora do git)

- `data/moratz/velas_m1.sqlite` é a base do laboratório: M1 de 09/09/2026 em diante. **Não apague: a IQ não devolve mais setembro.**
- `data/moratz/outros_mercados_m1.sqlite` guarda ouro, prata, BTC, índices e ações, `-op` e OTC, de 09/09 a 08/11. Ficou guardado; ainda não é usado.
- `data/moratz/estudos_anteriores/` tem os pré-registros e o ledger das rodadas de 08–09/11, salvos do `/tmp`.
- `data/moratz/mapa/`, `data/moratz/mesa/` e `data/moratz/conferidas/` guardam as saídas e as travas do E.
