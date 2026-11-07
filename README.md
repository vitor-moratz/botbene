<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/img/logo-escuro.png">
    <img src="docs/img/logo.png" alt="BotBene" width="420">
  </picture>
</p>

# BotBene

Bot de CALL/PUT para a IQ Option (M1) baseado na apostila **"Estudos e anotações sobre a Lógica do Preço"**.
O objetivo é ser **seletivo**: operar só quando a leitura da apostila estiver clara e mostrar no dashboard o acerto por script e por setup.

**📘 [Como instalar e usar (passo a passo, tecnologias e problemas comuns)](docs/INSTALACAO.md)** · **[Estratégias em uso](docs/estrategia.md)**

> **Status:** Fase 3. O bot manda ordens na conta demo (testado de ponta a ponta) e acompanha até 8 pares ao mesmo tempo. A estratégia principal é a **retração no comando** (apostila, pág. 27), a melhor encontrada: 56,4% no primeiro período de conferência, mas 53,8% em 6 pares novos. Fora da amostra, fica em ~54%, igual ao empate (54,3%), ou seja, ainda **sem vantagem comprovada**. Os scripts da plataforma ficaram em ~49% em 42 dias de histórico. **Estratégias em uso e como operar:** primeira parte de [docs/estrategia.md](docs/estrategia.md) (também em PDF: "BotBene - Guia das estrategias.pdf"). Números da pesquisa: Parte 2, seção 7.

## Programa (Windows)

A instalação completa, num computador novo, está em [docs/INSTALACAO.md](docs/INSTALACAO.md). Com o projeto já instalado, crie os atalhos uma vez, no PowerShell do Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\moratz\botbene\desktop\instalar_atalho.ps1"
```

Depois é só abrir **BotBene** pela Área de Trabalho ou pelo Menu Iniciar. O atalho sobe o servidor no WSL (escondido) e abre o painel numa janela própria, sem barra de endereço. Se o ícone mudar, rode o instalador de novo: ele grava o ícone com um nome novo, para o Windows não mostrar o antigo do cache. Ele também liga o atalho à janela, para a barra de tarefas mostrar o ícone do BotBene.
- Fechar a janela **não** para o bot: ele continua rodando. Para encerrar tudo, use **Desligar BotBene** na barra lateral.
- Log do servidor: `data/server.log`.

## Painel

- **Modos:** só sinais, aprovação, automático, ou automático com veto (entra sozinho, mas dá para cancelar; é o recomendado). Começa sempre na conta demo; a real se escolhe na barra lateral (veja os Avisos).
- **Estratégias:** cada uma fica **Desligada**, **Observar** (anota e mede, sem ordem) ou **Operar** (pode mandar ordem). Uma ordem por par e vela: CALL e PUT juntos se anulam; no mesmo sentido, vale a de mais confluências.
- **Scripts** (LDP v1.3, WIKI PRO): só ajuda visual no gráfico. Nunca decidem entrada e não entram nas estatísticas. A comparação deles fica na ferramenta de pesquisa.
- **Pedidos de aprovação** (no topo de qualquer tela, com aviso sonoro): gráfico grande com 60 velas, vela de comando marcada, linhas do gatilho e da abertura, vela da entrada ao vivo; ao lado, contagem dos 15 s, preço agora e pips até o gatilho, valor, vencimento e o botão Aprovar. Vários pedidos viram abas. Aprovar antes do gatilho = a ordem sai no toque; depois do toque (ainda nos 15 s) = sai no preço do momento. Botão **Tela cheia** na barra lateral.
- **Vigia da conexão:** se a IQ para de responder, o horário dela para, a biblioteca avisa que caiu ou nenhum par aberto recebe preço novo, o bot fecha a conexão, abre outra, recarrega os pares e volta a rodar sozinho (aviso amarelo enquanto isso; "reconectou N×" depois). Chamadas à biblioteca que estouram o prazo têm a thread encerrada, porque ela espera em laços sem pausa. Em último caso, o servidor reinicia sozinho (`desktop/start_server.sh`) e retoma o bot com o placar da sessão; na conta real, ele não volta a operar sem alguém clicar em Iniciar.
- **Gráficos:** botões **−** e **+** de zoom e foco no preço atual, no gráfico do Painel e no do pedido de aprovação. No Painel, **Expandir** deixa só o gráfico, em tela cheia.
- **Troca de par:** abas acima do gráfico com os pares do bot e os últimos que você olhou, com o payout de cada um; **+ Todos os pares** (ou clique no nome do par) abre a lista de binárias da IQ com busca e categorias. O par da tela fica ao vivo mesmo com o bot parado ou fora da lista dele. Olhar um par não muda o que o bot opera.
- **Entrada manual:** cartão com CALL e PUT, valor, expiração de 1 a 5 min (a que o par aceitar), payout e hora do vencimento. A decisão é sua: os stops, os filtros e o martingale do bot não valem e não contam com ela, e ela fica fora das estatísticas das estratégias. Aparece no gráfico como **MANUAL CALL/PUT** e nas ordens com a marca MANUAL. Na conta real, um clique envia, sem confirmação.
- **Painel:** resultado, acerto e entradas de hoje (só ao vivo), gráfico com velas, marca **ENTRADA CALL/PUT** com preço e resultado em cada ordem enviada, setas pequenas nas entradas só anotadas, linhas e setas dos scripts, suporte/resistência, próxima entrada armada, **ordens na conta demo** com o placar da sessão, feed das entradas e leitura da última vela.
- **Configuração:** login da IQ (com "Testar conexão"; a senha fica só em `data/config.json` e nunca volta para a tela), modo (os 4 acima), estado de cada estratégia, ajuda visual no gráfico, pares, vela, valor da entrada, stop win, stop loss, máximo de entradas, pausa por perdas seguidas, payout mínimo, horário de operação e martingale com análise (o gale só vale para a próxima entrada válida e aprovada; até 2 níveis; o ciclo inteiro precisa caber no stop loss).
- **Entradas:** todas as entradas por período (Hoje / 7 dias / Mês / Geral), com entrada, saída e resultado.
- **Desempenho:** por período, resultado por hora/dia/mês, saldo acumulado, acerto por estratégia com intervalo de confiança, por setup, por horário e OTC × normal.

O backtest (calculado ao iniciar, cobrindo o dia desde a meia-noite) fica como referência: nas telas, o padrão é sempre **ao vivo**. Com "mostrar sinais do backtest" marcado, o quadro **Retroativo de hoje** conta vitórias, perdas, acerto e resultado por estratégia.

Sem o atalho, dá para rodar à mão: `cd ~/botbene/backend && .venv/bin/python -m uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5` e abrir http://127.0.0.1:8000.

## Avisos

- A IQ Option não tem API oficial. O bot usa a biblioteca **não oficial** `iqoptionapi`, sem atualização desde jan/2022. Ela pode quebrar, e uso automatizado pode violar os termos da corretora (risco de bloqueio da conta).
- Para não perder dinheiro, é preciso acertar mais que `1 / (1 + payout)`: **54,1%** com payout de 85%, **55,6%** com 80%.
- Tudo começa na conta **demo (PRACTICE)**. A **real** se escolhe na barra lateral, só com o bot parado. Ela pede a palavra REAL digitada, exige stop loss e deixa a tela marcada em vermelho. A recomendação, pelos números da pesquisa, é ficar na demo até a estratégia provar vantagem ao vivo.
- Na IQ, a binária dos pares normais é o instrumento com final **`-op`** (`EURUSD-op`). O `EURUSD` sem sufixo é outro instrumento, com preço um pouco diferente: o bot lê e opera o `-op`. Os `-OTC` costumam abrir quando o mercado normal fecha, como no fim de semana.
- A conta demo da IQ é em **dólar**; valores de entrada e stops ficam na moeda da conta.
- O vencimento da ordem é calculado pelo horário da IQ, não pelo relógio do computador (neste PC o relógio estava ~29 s adiantado). Mesmo assim, vale manter o relógio do Windows sincronizado.

## Estrutura

```
backend/app/
  market/      velas, CandleStore (stream ao vivo), CSV
  indicators/  EMA, RMA, RSI, ATR, ADX/DMI (mesma matemática do Quadcode Script)
  ldp/         motor da apostila: candles.py, structures.py, levels.py, engine.py
  strategies/  ports fiéis (ldp_v13.py, wiki_pro_v21.py) e as de dentro da vela
               (retracao_comando.py, ldp_apostila.py, intra.py)
  broker/      interface da corretora + adaptador IQ Option (velas, stream, ordens)
  risk/        valor da entrada, stop win/loss, limite de entradas, pausa por perdas seguidas
  research/    base de pesquisa (1 min + 5 s, vários pares) e avaliação das estratégias
  tools/       fetch_candles, signals_report, live_watch, research
backend/tests/ figuras da apostila como casos de teste + teste de "sem repintura"
frontend/      painel (HTML, CSS e JS sem build) e os ícones icon-*.png
desktop/       atalho do Windows (instalar_atalho.ps1, BotBene.ps1, start_server.sh), botbene.ico, make_brand.ps1
assets/brand/  ícone e logo originais (make_brand.ps1 gera todos os tamanhos a partir deles)
scripts_iq/    scripts .lua originais da plataforma (referência dos ports; só na máquina, fora do git)
docs/          estrategia.md (regras ↔ páginas da apostila), INSTALACAO.md (tutorial), img/ (logo)
```

## Como rodar (WSL Ubuntu)

```bash
cd ~/botbene/backend

# 1) Ambiente Python (uma vez). Se der erro de ensurepip: sudo apt install python3.14-venv
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2) Testes
.venv/bin/python -m pytest -q

# 3) Biblioteca da IQ Option (não oficial, instalada direto do GitHub)
.venv/bin/pip install "websocket-client==0.56"
.venv/bin/pip install -U https://github.com/iqoptionapi/iqoptionapi/archive/refs/heads/master.zip

# 4) Credenciais: copie e preencha (o .env nunca vai para o git)
cp .env.example .env

# 5) Baixar velas e gerar o relatório de sinais
.venv/bin/python -m app.tools.fetch_candles --asset EURUSD --tf 60 --count 2000
.venv/bin/python -m app.tools.signals_report --csv ../data/candles/EURUSD_60.csv

# 6) Acompanhar ao vivo, sem ordens (Ctrl+C para parar)
.venv/bin/python -m app.tools.live_watch --asset EURUSD --tf 60

# 7) Pesquisa: baixar a base (6 pares) e medir as estratégias (ajuste × conferência)
.venv/bin/python -m app.tools.research baixar --dias 9               # 1 min + 5 s (a IQ guarda 5 s por ~1 semana)
.venv/bin/python -m app.tools.research baixar --dias 60 --tempos 60  # só 1 min, mais longe
.venv/bin/python -m app.tools.research relatorio
```

O servidor guarda sozinho, a cada 6 horas, as velas de 1 min e de 5 s dos pares configurados em `data/research.sqlite` (a IQ apaga as de 5 s depois de ~1 semana). Assim a pesquisa ganha dados novos toda semana sem precisar rodar nada.

**Conferir os ports contra a plataforma:** abra o mesmo ativo e horário na IQ Option com os scripts originais (`scripts_iq/*.lua`, que ficam só na máquina e não vão para o repositório) e compare as setas com as colunas `ldp_v13` e `wiki_pro_v21` do relatório (horário de Brasília). A meta é bater vela a vela depois do aquecimento dos indicadores (algumas centenas de velas, por causa da EMA 50). Se não bater, anote o horário da diferença: é assim que vamos ajustar o port.

## Materiais

A apostila tem direitos reservados: guarde o PDF em `docs/materiais/`. Essa pasta é ignorada pelo git e nunca vai para o repositório público.

## Próximas fases

| Fase | Entrega |
|---|---|
| 2 | ✓ banco SQLite, API, painel, modo paper, backtest imediato, regra das linhas, gatilhos de dentro da vela (15 s), base de pesquisa com ajuste × conferência, retração no comando |
| 3 | ✓ ordem na demo (testada de ponta a ponta), gestão de risco, modos de aprovação, automático e automático com veto, cartão grande com o trecho do gráfico, tela de configuração, vários pares ao mesmo tempo, seletor Demo/Real com travas, arquivo automático de velas para a pesquisa, martingale com análise (desligado por padrão) |
| 4 | ✓ vigia da conexão com reconexão e reinício automáticos, payout mínimo, horário de operação, entrada manual e gráfico ao vivo de qualquer par · a fazer: pausa automática por desempenho, ranking de setups; conta REAL só com liberação manual |
