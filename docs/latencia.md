# Latência das entradas: o que foi medido e o plano para quando precisar

**Estudo de 09/11/2026.** Nenhum código do bot mudou por causa dele. Serve de ponto de partida se um dia a velocidade da entrada passar a importar.

## Veredito de hoje: não vale mexer

- **O machine learning não é o gargalo.** O DeepLOB leva 6,4 ms por previsão e roda só nos pares fora do OTC.
- **O que mais atrasa a ordem é a espera do gale.** Nas estratégias com gale, 2 de cada 3 ordens saem com 3 a 9 s de vela, esperando o resultado da ordem anterior para saber o valor.
- **Atrasar não fez perder:**

  | Ordens de bb_rci e retracao_comando (até 09/11) | Ordens | Acerto |
  |---|---|---|
  | Saíram na hora (menos de 3 s de vela) | 41 | 49% (±15%) |
  | Saíram atrasadas (3 s ou mais) | 83 | 65% (±10%) |

  É pouca ordem, então isso não prova que atrasar ajuda. Mas não há sinal de que atrapalhe.
- **Os ganhos possíveis são pequenos para opções de 60 s.** As melhorias seguras (opções 1 a 3 abaixo) tiram ~0,3–0,5 s. Sem uma estratégia com vantagem comprovada, isso não muda o resultado. A prioridade continua sendo achar a vantagem (estudo dos 70%).
- **O único problema real que o atraso causava já foi resolvido.** O sinal dizia "loss" quando a ordem ganhava, porque a ordem abria num preço diferente. Desde 09/11, sinal que virou ordem fica com o resultado da corretora (`details.corretora`; ver README, tela Entradas).

## Quando voltar a isso

- **Uma estratégia passar no estudo** e a vantagem dela estiver no primeiro preço da vela, como no Bollinger + RCI e no DeepLOB, que entram no 1º preço. Aí as opções 5 e 0 passam a valer.
- **A distância entre o preço do sinal e o preço da ordem aparecer como perda.** Isso se confere comparando `details.corretora.velas` com o resultado da ordem, e o acerto na hora × atrasada, com `python -m tests.bench_fechamento`.
- **Entrarem mais modelos ao vivo**, como o meta-modelo ou outras redes. Aí vale a opção 6.

## O caminho de uma entrada

1. A vela k fecha na IQ. O bot só sabe disso quando chega o **primeiro preço da vela k+1** pelo stream.
2. O bot lê o stream de cada par a cada **0,5 s** (`POLL_SECONDS`, [bot.py](../backend/app/service/bot.py)), um par depois do outro (`_poll` → `_poll_runner`).
3. Ao ver a vela nova, `_on_close` do par faz a leitura da LdP, roda todas as estratégias (`plan_all`), grava a vela, resolve pendentes e avisa o painel. Os 20 pares fecham na mesma volta, então o último espera os outros 19.
4. `_check_triggers` confere o gatilho. Se tocou, grava o sinal (`_store_intra`, `_touch_details`) e chama `_send_order`.
5. Se a ordem anterior do gale ainda não tem resultado, a entrada fica em "esperando resultado" (`waiting_gale` em [orders.py](../backend/app/service/orders.py)). `_retry_gale_waits` manda a ordem quando o resultado chega, se ainda estiver dentro da janela de 10–15 s. Senão, fica bloqueada.
6. A ordem roda numa thread (`OrderManager._run`): `broker.buy` → a IQ aceita → espera o vencimento → lê o resultado (`order_result`). O resultado chega uns 3–5 s depois do vencimento.

## O que foi medido (09/11/2026)

**Segundo da vela em que o bot viu o toque** (`details.touch.sec`). No bb_rci e no deeplob_iq o gatilho é o 1º preço, então isso é o tempo até o bot enxergar a vela nova:

| Estratégia | Mediana | p90 |
|---|---|---|
| bb_rci | 1,16 s | 1,97 s |
| deeplob_iq | 1,12 s | 1,78 s |
| reversao_forca | 1,17 s | 2,24 s |

Esse 1,16 s se divide assim:

| Parte | Quanto | Observação |
|---|---|---|
| Espera entre leituras | +0,25 s em média, até 0,5 s | o bot dorme 0,5 s por volta |
| Fechamento dos 20 pares | 140 ms na mediana, p90 185 ms (bancada sem o medidor) | maiores custos: score_ldp (~1,2 ms/par), status do painel, gravar vela, pendentes |
| Thread por leitura da IQ | ~0,2–0,4 ms cada, ~40 por volta | `call_with_deadline` em [iqoption.py](../backend/app/broker/iqoption.py) abre uma thread até para ler o dicionário do stream |
| O resto (~0,6 s) | IQ mandar o preço novo + relógio | **não medido**: precisa da opção 0 |

Outros achados:

- **O relógio da IQ é a última mensagem `timeSync`** (`server_time()` lê `api.timesync.server_timestamp`). Entre uma mensagem e outra ele não anda, então pode estar atrasado. Tudo que usa "agora" herda isso, inclusive `touch.sec`, que portanto pode subestimar a latência.
- **A compra binária da biblioteca fica num laço sem pausa** (`buy_by_raw_expirations` em `iqoptionapi/stable_api.py`) até a resposta chegar, disputando o processador com a thread que recebe essa resposta. A digital já usa o nosso `_place_digital`, com pausa de 20 ms.
- **DeepLOB:** 6,4 ms por previsão (numpy; o LSTM de 100 passos é a maior parte). Com 4 pares fora do OTC, ~26 ms por vela.
- **Espera do gale:** das ordens de bb_rci/retracao_comando, a maioria saiu entre 4 e 6 s de vela.

## Como medir de novo

```bash
cd backend
.venv/bin/python -m tests.bench_fechamento            # dados ao vivo + bancada do fechamento + DeepLOB
.venv/bin/python -m tests.bench_fechamento --perfil   # idem, com as funções mais caras
```

O script ([tests/bench_fechamento.py](../backend/tests/bench_fechamento.py)) só lê `data/botbene.sqlite` e a config. A bancada roda o bot com corretora falsa (velas reais dos pares da config) num banco temporário, então dá para rodar com o bot ligado.

## Opções, da mais segura para a mais ousada

### 0. Cronômetro no log (fazer primeiro, junto com qualquer outra)

- **O que é:** registrar, por vela e por ordem, quando chegou o 1º preço da vela, quando o gatilho foi visto, quando a ordem foi pedida, quando a IQ aceitou e quando chegou o resultado. Também guardar a mensagem que a IQ manda quando a ordem abre (`socket-option-opened` / `option-opened`), para ver se ela traz o preço de abertura, que a opção 4 precisa.
- **Como:** a mensagem `candle-generated` da IQ tem o campo `at` (nanossegundos, horário da cotação). Hoje `_to_candle` descarta esse campo. Para separar "IQ demorou" de "bot demorou", basta comparar `at` com o relógio local. A diferença entre os dois relógios se estima pelas mensagens `timeSync`.
- **Ganho:** nenhum direto. É o que diz se as outras opções valem e confirma o ganho delas.
- **Risco:** nenhum, se for só log.

### 1. Ler por aviso em vez de a cada 0,5 s

- **O que é:** o bot acorda no instante em que chega preço novo, em vez de dormir 0,5 s entre as voltas.
- **Como:** a thread do websocket chama `WebsocketClient.dict_queue_add` a cada vela recebida. Envolver esse método na instância (de novo a cada conexão) para marcar um `threading.Event`. No `_run`, trocar `self._stop.wait(self.poll_seconds)` por esperar esse aviso com limite de 0,5 s. A classe base `Broker` ganha um `wait_quote(timeout)` que só dorme, para a corretora falsa e os testes.
- **Ganho:** −0,25 s em média (até −0,5 s) em todas as estratégias.
- **Risco:** baixo. Cuidado com a CPU: com 20 pares chegam dezenas de mensagens por segundo. Uma volta por aviso com um piso de ~50 ms entre voltas resolve.

### 2. Caminho rápido na abertura da vela

- **O que é:** na volta do fechamento, fazer primeiro só o que decide a ordem: leitura LdP, estratégias que operam e gatilho. Depois vem o resto: gravar velas, resolver pendentes, estratégias que só observam e o status do painel (uma vez por volta, não uma por par). Mandar a ordem antes de gravar o sinal.
- **Ganho:** −0,1 a −0,2 s nos últimos pares da lista.
- **Risco:** baixo. O cuidado é manter a ordem dos fatos no banco: o sinal precisa existir para a ordem apontar `signal_id`. Dá para criar o sinal em memória e gravar logo depois.
- **Junto:** ler o stream sem abrir thread. `get_realtime_candles` é só uma leitura de dicionário; copiar com nova tentativa, porque a thread do websocket mexe nele ao mesmo tempo.

### 3. Compra sem o laço sem pausa

- **O que é:** fazer para a binária o que `_place_digital` já faz: mandar o pedido (`api.buyv3_by_raw_expired`) e esperar a resposta com pausas de 10–20 ms, ou com um aviso.
- **Ganho:** milissegundos, mais menos disputa de processador durante a compra.
- **Risco:** baixo. Repetir o tratamento de erro da biblioteca (mensagem de recusa e limite de 5 s).

### 4. Resultado do gale calculado pelo bot

- **O que é:** no fechamento da vela, o bot compara o preço de abertura da ordem anterior com o fechamento e já sabe se ganhou ou perdeu, sem esperar os 3–5 s da IQ. Só decide sozinho com folga clara de preço. Empate ou quase empate continua esperando a IQ.
- **Depende de:** a IQ mandar o preço de abertura da ordem (opção 0 confirma).
- **Ganho:** −3 a −5 s na maioria das ordens das estratégias com gale. A ordem passa a entrar perto do preço do sinal.
- **Risco:** médio. Se errar, o valor do gale sai errado. Antes de valer, rodar alguns dias **só anotando** a previsão e comparando com o resultado da IQ. O valor da folga sai dessa comparação.

### 5. Decidir em 58–59 s e comprar antes da vela fechar

- **O que é:** para as estratégias que entram no 1º preço (Bollinger + RCI, DeepLOB), calcular o sinal com a vela ainda em formação e comprar no fim dela. A binária comprada com menos de 30 s para o fim do minuto vence no fim do minuto seguinte (`expiry_for` em `broker/base.py`), que é o mesmo vencimento de hoje.
- **Ganho:** −1,2 s mais o tempo da compra.
- **Risco:** muda a estratégia, porque o sinal pode virar no último segundo. **Exige estudo e pré-registro antes**, com as velas de 5 s da base de pesquisa: quantas vezes o sinal de 58 s é igual ao final, e o acerto com entrada em 58–59 s.

### 6. Acelerar o machine learning e os indicadores

- **DeepLOB:** ONNX Runtime ou numba levam a previsão de ~6 ms para ~1 ms. Ganho de ~20 ms por vela hoje. Em modelo pequeno com uma previsão por vez, ONNX contra PyTorch é quase empate, então só vale medindo.
- **Indicadores:** calcular aos poucos, a cada preço, sem refazer a janela inteira (como a biblioteca talipp). Corta parte dos 140 ms do fechamento. Esforço alto, ganho pequeno.
- **Quando vale:** se entrarem mais modelos ao vivo. Aí também vale rodar o que só observa fora do caminho da ordem (opção 2).

## Cuidados ao implementar

- O usuário roda o bot na **conta REAL** e às vezes há outras sessões editando a mesma pasta. Trabalhar numa cópia, testar e aplicar com `git apply` conferindo antes se os arquivos mudaram.
- O servidor não recarrega o código Python sozinho: precisa reiniciar. Só parar o bot com o **ciclo de gale fechado**: gale no nível 0, nenhuma ordem aberta, nenhum pedido em andamento, entre 15 e 40 s da vela. Na REAL o bot não volta sozinho: o usuário clica em Iniciar bot.
- Cada opção precisa de teste com a corretora falsa (`tests/fakes.py`) e de uma medição antes/depois com `tests.bench_fechamento`.

## Fontes consultadas

- Leitura por aviso × leitura periódica, e separar quem recebe os preços de quem decide: [dev.to (Polymarket, arquitetura)](https://dev.to/benjamin_cup/designing-a-low-latency-trading-architecture-for-polymarket-clob-v2-1943), [dev.to (latência evitável)](https://dev.to/mateosoul/eliminating-avoidable-latency-in-event-driven-trading-systems-with-a-polymarket-trading-bot-41c4), [dev.to (bot em Python com websocket)](https://dev.to/bluewhale-quant-lab/building-a-low-latency-polymarket-trading-bot-in-python-py-clob-client-websocket-4il8), [differ.blog](https://differ.blog/p/reducing-real-time-market-api-latency-websocket-practical-implementat-effe9d)
- Estado da ordem com atraso de rede: [dev.to (máquina de estados da ordem)](https://dev.to/mateosoul/designing-a-latency-aware-order-state-machine-for-a-polymarket-trading-bot-2lek)
- Tempo de ida e volta de uma ordem por websocket em outras corretoras: [dev.binance.vision](https://dev.binance.vision/t/creating-an-order-via-websocket/1455/2)
- Biblioteca da IQ e o laço de espera na compra: [evecimar/iqoptionapi](https://github.com/evecimar/iqoptionapi)
- Indicadores que se atualizam a cada preço: [talipp](https://pypi.org/project/talipp/1.2.0), [screamer](https://screamer.readthedocs.io/en/latest/functions_rolling/BollingerBands.html), [Wickra](https://wickra-docs.pages.dev/Indicator-BollingerBands)
- ONNX × PyTorch numa previsão por vez: [fórum do PyTorch](https://discuss.pytorch.org/t/does-onnx-increase-inference-efficiency-compared-to-pytorch-model/194980), [theneuralbase](https://theneuralbase.com/onnx/learn/advanced/performance-comparisons/)
