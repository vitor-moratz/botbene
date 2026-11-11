# Caderno do Padrão Moratz

Gerado por `python -m app.tools.moratz` a partir de `caderno.jsonl`. Não edite à mão: o registro só cresce.

## Placar das tentativas

| | -op | OTC |
|---|---|---|
| Testes em D (regras) | 2 | 0 |
| Variações testadas em D | 2 | 0 |
| Conferências em E | 2 | 0 |
| Versões congeladas | 0 | 0 |
| Lotes de leitura registrados | 0 | 0 |

Total de variações já olhadas em D: **2**. Quanto maior, mais desconfiança com um resultado bonito em D: é para isso que existem o E e o futuro.

## Registros

### 10/11/2026 13:30 · Marco

> Começo do Padrão Moratz. Laboratório montado; a história de M1 de 09/09 a 08/11 foi guardada em data/moratz/velas_m1.sqlite e completada pelo arquivo do servidor até 10/11 (-op) e 09/11 (OTC).

Nota: 12 pares -op e 8 OTC têm velas em D; 5 -op e 8 OTC só existem desde 31/10–02/11 (pares novos para o E). EURAUD, USDCAD e USDCHF -op ficam fora (pagam 0,50).

### 10/11/2026 13:30 · Marco · -op (mercado normal)

> Primeiro mapa da máquina em D: 480.540 velas de 12 pares.

Nota: Base: alta 50,1%, continua a cor 48,8%. Células a 5 ou mais pontos de 50% (n ≥ 300): 3 de 943 em % de alta e 2 em continua, contra 0,2 em média no sorteio (máx 2). O que aparece, nos 12 pares: a vela tende a VIRAR nas horas da virada do dia do forex (18h: continua 43,8%, ou seja, vira 56,2% em 16.169; de 16h a 20h todas abaixo de 47,5%) e depois de fechar colada num extremo (fecho abaixo de 0,17 ou acima de 0,83: continua 46,9%). Cuidado: nos estudos anteriores, efeitos desse tipo sumiram com a entrada alguns segundos depois da abertura (pulo da cotação em horário fraco). Qualquer ideia com eles precisa passar pela medida com entrada após a 1ª vela de 5 s.

### 10/11/2026 13:30 · Marco · OTC

> Primeiro mapa da máquina em D: 454.854 velas de 8 pares.

Nota: Base: alta 50,0%, continua a cor 50,1%. Células a 5 ou mais pontos de 50%: 0 de 939, contra 0,5 em média no sorteio. Nada fora do acaso, como nos estudos anteriores.

### 10/11/2026 14:36 · Teste em D (descoberta) · M-001 · `eab014c5b385` · -op (mercado normal)

> No -op, entre 16h e 20h, quando a vela fecha colada na máxima (fecho ≥ 0,83), a próxima desce.

19204 sinais decididos · acerto 57,5% (IC95 56,8% a 58,2%) · empate 54,6% · 598,2 sinais/dia · 12 de 12 pares acima de 50%

Sorteio: o acaso fez igual ou melhor em 0,5% das 200 vezes (média 49,8%).

Passou a porta.

Nota: primeira hipótese, tirada do mapa da máquina (virada 16-20h + fechamento no extremo)

### 10/11/2026 14:36 · Teste em D (descoberta) · M-002 · `f1079a098cde` · -op (mercado normal)

> No -op, entre 16h e 20h, quando a vela fecha colada na mínima (fecho ≤ 0,17), a próxima sobe.

18835 sinais decididos · acerto 58,5% (IC95 57,8% a 59,2%) · empate 54,6% · 587,0 sinais/dia · 12 de 12 pares acima de 50%

Sorteio: o acaso fez igual ou melhor em 0,5% das 200 vezes (média 50,1%).

Passou a porta.

Nota: primeira hipótese, tirada do mapa da máquina (virada 16-20h + fechamento no extremo)

### 10/11/2026 14:36 · Conferência em E (uma vez) · M-001 · `eab014c5b385` · -op (mercado normal)

> No -op, entre 16h e 20h, quando a vela fecha colada na máxima (fecho ≥ 0,83), a próxima desce.

11085 sinais decididos · acerto 55,5% (IC95 54,6% a 56,4%) · empate 54,6% · 615,9 sinais/dia · 12 de 12 pares acima de 50%

Passou a porta.

Nota: pares novos: 54,6% em 1834

### 10/11/2026 14:36 · Conferência em E (uma vez) · M-002 · `f1079a098cde` · -op (mercado normal)

> No -op, entre 16h e 20h, quando a vela fecha colada na mínima (fecho ≤ 0,17), a próxima sobe.

11215 sinais decididos · acerto 55,2% (IC95 54,3% a 56,1%) · empate 54,6% · 622,7 sinais/dia · 12 de 12 pares acima de 50%

Passou a porta.

Nota: pares novos: 53,0% em 1826
