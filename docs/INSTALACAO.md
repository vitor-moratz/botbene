<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="img/logo-escuro.png">
    <img src="img/logo.png" alt="BotBene" width="360">
  </picture>
</p>

# Como instalar e usar o BotBene

Este guia leva do zero até o bot rodando num computador com Windows. Explica também do que o BotBene é feito (as tecnologias) e onde ele guarda cada coisa.

**Sumário:** [1. O que é](#1-o-que-é) · [2. Do que você precisa](#2-do-que-você-precisa) · [3. Instalação](#3-instalação-passo-a-passo) · [4. Primeiro uso](#4-primeiro-uso-configuração) · [5. Uso no dia a dia](#5-uso-no-dia-a-dia) · [6. Conta real](#6-conta-real) · [7. Como funciona por dentro](#7-como-funciona-por-dentro) · [8. Tecnologias](#8-tecnologias-stack) · [9. Onde ficam os dados](#9-onde-ficam-os-dados) · [10. Atualizar](#10-atualizar-para-uma-versão-nova) · [11. Problemas comuns](#11-problemas-comuns) · [12. Para quem vai mexer no código](#12-para-quem-vai-mexer-no-código)

---

## 1. O que é

O BotBene opera CALL/PUT de 1 minuto na IQ Option seguindo a apostila **"Estudos e anotações sobre a Lógica do Preço"**. A estratégia principal é a **retração no comando** (pág. 27 da apostila). O que cada estratégia faz e os números da pesquisa estão em [estrategia.md](estrategia.md).

Ele roda **no seu computador**. Um pequeno servidor fica dentro do Linux do Windows (WSL), e o painel abre numa janela própria. Nada fica na nuvem.

> **Antes de começar, leia isto.**
> - Opções binárias têm **alto risco de perda**. Nenhuma estratégia garante acerto.
> - Pela pesquisa, a estratégia principal acerta **cerca de 54%** em dados que ela nunca viu. Isso é praticamente o **empate** (com payout de 84 a 85%, é preciso acertar 54,1% a 54,3% só para não perder). Use a **conta demo** até ela provar vantagem ao vivo.
> - A IQ Option **não tem API oficial**. O bot usa uma biblioteca não oficial, que pode parar de funcionar quando a IQ muda algo. Uso automatizado pode violar os termos da corretora e levar ao bloqueio da conta.

## 2. Do que você precisa

| Item | Detalhe |
|---|---|
| Computador | Windows 10 (versão 2004 ou mais nova) ou Windows 11, com uns 2 GB livres em disco |
| WSL 2 + Ubuntu | O "Linux dentro do Windows", onde o bot roda. Instalação no passo 1 |
| Microsoft Edge | Já vem no Windows. O painel abre numa janela do Edge, sem barra de endereço |
| Internet | Para falar com a IQ Option e carregar o gráfico |
| Conta na IQ Option **com senha** | Se você entra na IQ pelo Google, a conta não tem senha. Crie uma: na tela de login da IQ, clique em **"Esqueceu a senha?"**, use o mesmo e-mail e defina uma senha. O login pelo Google continua funcionando |
| Relógio do Windows certo | Configurações → Hora e idioma → Data e hora → **Sincronizar agora**. O bot usa o horário da IQ, mas é bom manter o relógio certo |

## 3. Instalação, passo a passo

São 7 passos, e você só faz uma vez. Os comandos do passo 1 são no **PowerShell do Windows**. Do passo 2 ao 7, são no **terminal do Ubuntu** (abra "Ubuntu" pelo Menu Iniciar). Para colar no terminal do Ubuntu, use o botão direito do mouse ou `Ctrl+Shift+V`.

### Passo 1: instalar o WSL e o Ubuntu

Abra o **PowerShell como administrador** (botão direito no Menu Iniciar → "Terminal (Admin)") e rode:

```powershell
wsl --install -d Ubuntu
```

Reinicie o computador quando ele pedir. Na primeira vez que o Ubuntu abrir, ele pede um **nome de usuário e uma senha do Linux**. Essa senha não é a da IQ: ela serve para os comandos com `sudo`. Anote.

> Se o WSL já estiver instalado, rode só `wsl --update` e confira que é a versão 2 com `wsl -l -v`.

### Passo 2: instalar o Git e o Python

No terminal do Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
python3 --version    # precisa ser 3.11 ou mais novo
```

### Passo 3: baixar o BotBene

```bash
git clone https://github.com/vitor-moratz/botbene.git ~/botbene
```

O código fica em `~/botbene`, a pasta `botbene` dentro da sua pasta do Ubuntu. No Explorador de Arquivos do Windows, ela aparece em **Linux → Ubuntu → home → (seu usuário) → botbene**.

### Passo 4: criar o ambiente Python e instalar as dependências

```bash
cd ~/botbene/backend
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
```

O `.venv` é uma pasta só do BotBene com as bibliotecas dele. Assim, nada se mistura com o resto do sistema.

### Passo 5: instalar a biblioteca da IQ Option

A biblioteca não está no repositório oficial do Python. Ela vem direto do GitHub, e precisa de uma versão antiga do `websocket-client`. Instale nesta ordem:

```bash
cd ~/botbene/backend
.venv/bin/pip install "websocket-client==0.56"
.venv/bin/pip install -U https://github.com/iqoptionapi/iqoptionapi/archive/refs/heads/master.zip
.venv/bin/pip show websocket-client | grep Version    # tem que mostrar 0.56.0
```

### Passo 6: conferir se está tudo certo

```bash
cd ~/botbene/backend
.venv/bin/python -m pytest -q
```

No final, todos os testes devem passar ("passed", sem "failed"). Eles não acessam a IQ: usam uma corretora de mentira.

### Passo 7: criar o atalho do programa

Ainda no terminal do Ubuntu:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w ~/botbene/desktop/instalar_atalho.ps1)"
```

Esse comando cria o ícone **BotBene** na Área de Trabalho e no Menu Iniciar. Ele também copia o lançador para `%LOCALAPPDATA%\BotBene` e liga o atalho à janela do painel. Assim, a barra de tarefas mostra o ícone do BotBene, e "Fixar na barra de tarefas" fixa o atalho certo.

> Pelo PowerShell do Windows, o equivalente é este (troque `SEU-USUARIO` pelo seu usuário do Ubuntu):
> `powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\SEU-USUARIO\botbene\desktop\instalar_atalho.ps1"`

Pronto, está instalado.

## 4. Primeiro uso: Configuração

1. Abra o **BotBene** pelo atalho. Na primeira vez, ele leva alguns segundos para subir o servidor.
2. Vá em **Configuração**, na barra da esquerda.
3. **Conta IQ Option:** preencha o e-mail e a senha da IQ e clique em **Testar conexão**. A senha fica guardada só no seu computador, em `data/config.json`, e nunca volta para a tela.
4. **Operação:**
   - **Modo:** escolha **Automático com veto** (o recomendado). Cada entrada aparece na tela com um bipe, já aprovada. Se você não fizer nada, a ordem sai sozinha no toque do gatilho. Se não gostar, clique em **Cancelar esta entrada**.

     | Modo | O que faz |
     |---|---|
     | Só sinais | Só avalia e registra as entradas. Não manda ordem |
     | Aprovação | Cada entrada espera você clicar em **Aprovar**. Aprovar não garante a ordem: ela só sai se o preço tocar o gatilho |
     | Automático | Entra sozinho, sem cartão na tela |
     | **Automático com veto** | Entra sozinho, mas mostra o cartão e deixa cancelar |

   - **Estratégias:** cada uma fica em **Desligada**, **Observar** (anota e mede, sem mandar ordem) ou **Operar** (pode mandar ordem, conforme o modo). Deixe **Apostila · retração no comando** em **Operar**. Ligar ou desligar vale no próximo início do bot; trocar entre Observar e Operar vale na hora.
   - **Ajuda visual no gráfico:** as linhas e setas dos scripts (LDP v1.3, WIKI PRO). Eles só desenham: nunca decidem entrada e não entram nas estatísticas.
   - **Pares:** escolha até 20. Os pares normais terminam em **`-op`** (ex.: `EURUSD-op`). Os `-OTC` costumam abrir quando o mercado normal fecha, como no fim de semana. Uma instalação nova já vem com os 12 pares `-op` em que a retração no comando foi estudada e com a troca automática entre OTC e mercado normal ligada: o bot opera o `-op` sempre que ele está aberto.
   - **Tipo de opção:** **Binária** (padrão), **Digital** ou **A de maior payout** (a cada vela, o bot compara a binária e a digital de cada par e entra na que paga mais). As duas usam o mesmo preço na IQ; muda só o produto comprado.
   - **Vela:** 1 minuto.
5. **Gestão de risco:**

   | Campo | O que é | Padrão |
   |---|---|---|
   | Valor de cada entrada | Quanto cada ordem aposta, na moeda da conta (a demo da IQ é em dólar) | 2 |
   | Stop win | Para de abrir ordens quando o lucro da sessão chega neste valor | 20 |
   | Stop loss | Só abre uma ordem nova se, perdendo ela e as que ainda estão abertas, a perda da sessão não passar deste valor | 20 |
   | Máximo de entradas por sessão | Limite de ordens desde que você clicou em Iniciar bot | 30 |
   | Pausar depois de X perdas seguidas | Para depois de X perdas em sequência | 4 |
   | Payout mínimo (%) | Não abre pedido nem manda ordem em par com payout menor. Com payout menor, o acerto para empatar sobe (85% → 54,1%, 80% → 55,6%, 75% → 57,1%) | 80 |
   | Operar das / até as | Janela de operação, no horário de Brasília. Vazio = o dia todo. Se o fim for antes do início, passa da meia-noite | Vazio |
   | Martingale com análise | Depois de uma perda, a próxima entrada **válida da estratégia** vale mais, o bastante para recuperar o ciclo (até 2 gales). Nunca entra às cegas na vela seguinte, e o ciclo inteiro precisa caber no stop loss. Você marca **quais estratégias usam o gale**; as outras entram sempre com o valor normal | Desligado |

   *Sessão* = do clique em **Iniciar bot** até o bot parar.

   Fora dos dois filtros (payout e horário), o bot continua medindo a estratégia, mas não opera.

6. Clique em **Salvar configuração**.

Na barra da esquerda, confira que a conta está em **Demo**.

## 5. Uso no dia a dia

1. Abra o **BotBene** e clique em **Iniciar bot**, no topo.
2. Deixe rodando. Os pedidos aparecem de tempos em tempos, e só cerca de **8 em cada 100** viram ordem, porque o preço precisa recuar até o gatilho nos primeiros 15 segundos da vela. Muitos pedidos sem ordem é o normal.
3. Quando aparecer um pedido, o cartão no topo mostra o gráfico com a vela de comando marcada, a linha do gatilho, a contagem dos 15 s, o valor e o vencimento.
   - **Botões do gráfico** (embaixo, no centro, aqui e no gráfico do Painel): **−** e **+** para ver mais ou menos velas, e o alvo para voltar ao preço atual. O alvo fica azul quando a vela atual saiu da tela. A rodinha do mouse e o arrastar também funcionam.
4. Quando o pedido termina, o cartão de resultado deixa claro o que aconteceu:

   | Cartão | Significa |
   |---|---|
   | ✓ **ORDEM ENVIADA NA CONTA DEMO** | A ordem saiu. Logo abaixo aparece "aguardando o resultado", depois **GANHOU** ou **PERDEU** com o valor |
   | — **NENHUMA ORDEM FOI ENVIADA** | O preço não tocou o gatilho nos 15 s (é o mais comum), ou você cancelou |
   | ✗ **A ORDEM NÃO FOI ENVIADA** | A gestão de risco bloqueou (ex.: stop atingido) ou a corretora recusou. O motivo aparece no cartão |

5. **Painel:** resultado e acerto de hoje, o gráfico, a entrada manual, a próxima entrada armada e o quadro **Ordens**, com cada ordem marcada como *Enviada* ou *Não enviada* e o resultado.
   - **Trocar o par do gráfico:** clique numa das abas acima do gráfico. Em **Bot** ficam os pares que o bot opera; em **Olhando**, os últimos que você abriu (o **×** tira da lista). Cada aba mostra o payout ou "fechado". Para outro par, clique em **+ Todos os pares** ou no nome do par: dá para buscar ("btc", "eur"), filtrar por categoria e ver só os abertos. O par da tela fica ao vivo mesmo com o bot parado. Olhar um par não muda o que o bot opera: isso continua na Configuração.
   - **Entrada manual** (no topo da coluna da direita): escolha o valor (− e +, ou digite) e a expiração, confira o payout, a hora do vencimento e quanto ganha, e clique em **CALL** ou **PUT**. Com menos de 30 s para virar o minuto, o vencimento passa para o minuto seguinte, como na IQ. A decisão é sua: os stops, o limite de entradas, os filtros de payout e horário e o martingale do bot **não valem** para ela e não mudam com ela. Ela também fica fora das estatísticas das estratégias. Na **conta real**, o cartão fica vermelho e **um clique envia dinheiro de verdade, sem confirmação**. Os botões ficam apagados, com o motivo escrito, quando o par está fechado, o valor está fora do limite da IQ ou o bot está reconectando.
   - **No gráfico:** a marca **ENTRADA CALL** ou **ENTRADA PUT**, com o preço e ✓ / ✗ / …, é uma ordem enviada pelo bot; **MANUAL CALL** ou **MANUAL PUT** é uma entrada sua. Enquanto a ordem está aberta, uma linha mostra o preço de entrada. Seta pequena é uma entrada que a estratégia só anotou, sem ordem. **CALL** e **PUT** sem a palavra ENTRADA são do script LDP: só desenho, o bot não opera neles. O gráfico mostra um par por vez: uma ordem em outro par aparece ao escolher a aba desse par.
   - **Mostrar sinais do backtest:** ao iniciar, o bot aplica as estratégias nas velas de hoje, desde a meia-noite, e marca onde elas teriam entrado, com o resultado. Não são ordens e não contam nos números do Painel. Serve para conferir a regra com os olhos: marque a opção, passe o mouse na seta e veja se você também entraria ali.
   - **Retroativo de hoje:** aparece com a opção acima marcada. Conta vitórias, perdas, acerto e resultado de cada estratégia ligada nos botões do gráfico, no par à vista e no conjunto dos pares do mesmo mercado (OTC e mercado normal não se somam). É calculado ao iniciar o bot; depois disso, as entradas contam como ao vivo. Por buscar o dia inteiro, o início do bot demora mais quanto mais tarde for (cerca de 1 min 40 s com 8 pares às 20h).
   - **Expandir:** deixa só o gráfico na tela, em tela cheia, com as abas de par e o cartão de entrada manual fixo à direita. Para voltar, clique em **Sair** ou aperte **Esc**. Pedidos de aprovação e avisos continuam aparecendo por cima, e a conta real continua marcada em vermelho.
   - **Mostrar a leitura do estudo:** desenha lotes (caixas), regiões (faixas) e padrões (rótulos como NA, NP, DP), e diz o cenário atual. Passe o mouse na vela para ver cada padrão com a página da apostila. Só desenho: nenhuma estratégia usa isso ainda. Enquanto está ligada, os scripts saem do gráfico para não embolar.
   - **Se a conexão com a IQ cair**, aparece um aviso amarelo, e o bot reconecta sozinho, sem você fazer nada (em geral, em menos de 1 min). Nesse meio-tempo, nenhuma ordem sai. Depois que volta, o status mostra "reconectou N×". Uma ordem aberta na hora da queda pode ficar como *sem resultado*: confira no histórico da IQ.
   - **Em último caso, o servidor reinicia sozinho** e retoma o bot, sem zerar o placar: o stop win, o stop loss e o limite de entradas continuam contando. Só na conta demo (veja a seção 6).
6. **Entradas:** a lista de todas as entradas por período (Hoje, 7 dias, Mês, Geral).
7. **Desempenho:** acerto com faixa de confiança, resultado por dia e por hora, e saldo acumulado.
8. **Barra da esquerda:** **Tela cheia**, **Tema claro/escuro**, a seta **‹** para encolher o menu e o seletor **Demo / Real** com o saldo.
9. Para encerrar, use **Desligar BotBene**. Só fechar a janela **não** para o bot: ele continua rodando em segundo plano, e o atalho reabre o painel.
10. Para zerar a contagem e recomeçar, use **Configuração → Dados → Zerar histórico do bot**, com o bot parado. Antes de apagar, ele guarda uma cópia em `data/backups/`.

> Deixe o computador **ligado e sem suspender** enquanto o bot roda (Configurações → Sistema → Energia). Se o Windows dormir, o bot para de receber preços. Quando o computador acordar, ele reconecta sozinho, mas perde as entradas do tempo em que ficou dormindo.

## 6. Conta real

O bot sempre começa na **demo**. Para usar a conta real:

1. **Pare** o bot.
2. Na barra da esquerda, clique em **Real** e digite **REAL** para confirmar.
3. É obrigatório ter um **stop loss** configurado.
4. Com a conta real ativa, a tela fica marcada em **vermelho**.
5. Se o servidor precisar reiniciar sozinho, na conta real o bot **não volta a operar sozinho**: ele fica parado, com um aviso, até você conferir a tela e clicar em **Iniciar bot**.

A recomendação, pelos números da pesquisa, é só pensar nisso depois de pelo menos 200 entradas ao vivo com acerto acima do empate, mesmo no pior caso da faixa de confiança. Na prática, isso é cerca de 61% em 200 entradas, ou 59% em 500.

## 7. Como funciona por dentro

```
 Windows                                    WSL (Ubuntu)
 ───────                                    ────────────
 Atalho "BotBene"                           Servidor (Uvicorn + FastAPI) em 127.0.0.1:8000
   └─ lançador PowerShell ──── sobe ──────▶   ├─ 1 "corredor" por par: velas M1 + preço ao vivo
   └─ janela do Edge (--app) ◀─ painel ────   ├─ estratégia: arma na vela de comando, gatilho nos 15 s
         HTTP + WebSocket                     ├─ gestão de risco ─▶ envio da ordem ─▶ resultado
                                              ├─ banco SQLite em data/
                                              └─ adaptador da IQ (iqoptionapi) ◀────▶ IQ Option
```

- O servidor só aceita conexões do próprio computador (`127.0.0.1`).
- No fechamento de cada vela de 1 minuto, a estratégia procura uma **vela de comando**. Se achar, arma um pedido para a vela seguinte.
- Durante a vela seguinte, o bot acompanha o preço ao vivo. Se o preço recuar até o gatilho nos primeiros 15 s, a ordem sai na hora, com vencimento no fim daquela vela.
- O vencimento é calculado pelo **horário da IQ**, não pelo relógio do computador.
- **Vigia da conexão:** o bot reconecta sozinho quando a IQ para de responder, quando o horário dela para de chegar (ele chega a cada segundo), quando o websocket fecha ou quando nenhum par aberto recebe preço novo. Se nem isso resolver, o servidor reinicia sozinho (`desktop/start_server.sh` sobe de novo) e retoma o bot.
- A cada 6 horas, o servidor guarda as velas de 1 min e de 5 s dos pares configurados em `data/research.sqlite`. A IQ apaga as de 5 s depois de cerca de uma semana, e essa base é usada para testar ideias novas.

## 8. Tecnologias (stack)

| Camada | Tecnologia | Versão testada | Para quê |
|---|---|---|---|
| Linguagem | **Python** | 3.14 (funciona a partir da 3.11) | Todo o bot: estratégias, risco, ordens |
| Servidor web | **FastAPI** + **Uvicorn** | 0.162 / 0.54 | API local (`/api/...`) e entrega do painel |
| Tempo real | **WebSocket** (`websockets`) | 17 | Painel atualizado ao vivo, sem recarregar |
| Banco de dados | **SQLAlchemy 2** + **SQLite** (modo WAL) | 2.1 | Entradas, ordens, sessões e velas, num arquivo local |
| Configuração | **Pydantic 2** + **pydantic-settings** | 2.14 / 2.16 | Validação da tela de Configuração e do `.env` |
| Corretora | **iqoptionapi** (não oficial) + **websocket-client** | 7.1.1 / 0.56.0 | Login, velas, preço ao vivo, ordens e resultado |
| Painel | **HTML + CSS + JavaScript** puro | — | Sem Node e sem etapa de build: os arquivos de `frontend/` são servidos como estão |
| Gráficos | **TradingView Lightweight Charts** | 4.2 (via CDN) | Velas, linhas do gatilho e marcações |
| Programa no Windows | **Microsoft Edge** em modo aplicativo (`--app`) + **PowerShell** | Windows PowerShell 5.1 | Atalho, lançador e geração dos ícones |
| Ambiente | **WSL 2** + **Ubuntu** | Ubuntu 26.04 | Onde o servidor roda |
| Testes | **pytest**, **httpx**, **esprima** | 9.2 / 0.28 / 4.0 | Regras da apostila, API, risco, ordens e sintaxe do `app.js` |

## 9. Onde ficam os dados

Tudo fica na pasta `data/` do projeto, que **nunca vai para o Git**:

| Arquivo | O que guarda |
|---|---|
| `data/config.json` | A configuração da tela, incluindo o login da IQ (só o seu usuário do Linux consegue ler) |
| `data/botbene.sqlite` | Entradas, ordens, sessões e velas do bot |
| `data/research.sqlite` | Base de pesquisa: velas de 1 min e de 5 s, que cresce a cada 6 horas |
| `data/backups/` | Cópias feitas ao zerar o histórico |
| `data/server.log` | Registro do servidor (o primeiro lugar para olhar quando algo der errado) |
| `data/relatorios/` | Os PDFs de relatório e o guia |

O arquivo `backend/.env` é opcional: dá para pôr o login nele em vez da tela, copiando `backend/.env.example`. Ele também fica fora do Git.

## 10. Atualizar para uma versão nova

1. Clique em **Desligar BotBene**.
2. No terminal do Ubuntu, rode:
   ```bash
   cd ~/botbene
   git pull
   cd backend && .venv/bin/pip install -e ".[dev]"
   .venv/bin/python -m pytest -q
   ```
3. Abra o **BotBene** de novo pelo atalho.

Seus dados e sua configuração continuam. Se o ícone mudar numa versão nova, rode de novo o comando do passo 7.

## 11. Problemas comuns

| Problema | O que fazer |
|---|---|
| "Testar conexão" falha com e-mail e senha certos | A conta foi criada pelo Google e não tem senha. Crie uma em "Esqueceu a senha?" na IQ (seção 2) |
| O atalho mostra "Não foi possível iniciar o servidor" | Veja o fim do log: `tail -50 ~/botbene/data/server.log`. Muitas vezes falta o passo 4 ou o 5 |
| Erro de `ensurepip` ao criar o `.venv` | Falta o pacote do venv: `sudo apt install -y python3-venv` (ou `python3.X-venv`, com a sua versão) |
| Aviso de que o par "está fechado para binária agora" | Use os pares que terminam em `-op`. Fora do horário do mercado (fim de semana), só os `-OTC` abrem. Par fechado continua sendo avaliado, mas não manda ordem |
| A ordem sai com o vencimento errado | O bot usa o horário da IQ. Mesmo assim, sincronize o relógio do Windows |
| A porta 8000 está ocupada | Já existe um servidor rodando. Clique em **Desligar BotBene**, ou rode `pkill -INT -f uvicorn.app.main` no Ubuntu e abra de novo |
| O painel não mostra a versão nova | Ele recarrega sozinho quando os arquivos mudam. Se não recarregar, aperte `Ctrl+F5` |
| Aviso amarelo "A conexão com a IQ Option caiu" | É normal de vez em quando: a IQ derruba a conexão. O bot reconecta sozinho, tentando de novo com esperas cada vez maiores (até 5 min). Se ficar muito tempo nisso, confira a internet e o login da IQ, e veja `data/server.log` |
| "A IQ recusou o e-mail ou a senha" | Confira o login em **Configuração** e clique em **Testar conexão**. O bot não fica repetindo a senha errada por conta própria, porque isso pode bloquear a conta |
| O bot parou de receber preço e não apareceu aviso | Clique em **Parar bot** e depois em **Iniciar bot**. Se não voltar, desligue e abra de novo |
| O ícone do atalho ou da barra de tarefas continua o antigo | Rode de novo o comando do passo 7. Ele grava o ícone com um nome novo, o que obriga o Windows a largar o antigo. Depois, feche a janela do BotBene e abra pelo atalho |

## 12. Para quem vai mexer no código

```bash
cd ~/botbene/backend

# rodar o servidor à mão (Ctrl+C para parar) e abrir http://127.0.0.1:8000
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5

# testes
.venv/bin/python -m pytest -q

# pesquisa: baixar velas (1 min + 5 s) e medir as estratégias (ajuste × conferência)
.venv/bin/python -m app.tools.research baixar --dias 9
.venv/bin/python -m app.tools.research relatorio
```

- **Estrutura das pastas:** está no [README](../README.md#estrutura).
- **Ícones e logo:** os originais ficam em `assets/brand/` (`icone.png` e `logo.png`, com fundo transparente). Para gerar todos os tamanhos (do painel, do atalho `.ico` e destas páginas), rode no PowerShell do Windows:
  `powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\SEU-USUARIO\botbene\desktop\make_brand.ps1"`
- **Segredos:** o login fica só em `data/config.json` ou em `backend/.env`. Nunca faça commit desses arquivos (o `.gitignore` já bloqueia).
- **Apostila:** ela tem direitos reservados. Guarde o PDF em `docs/materiais/`, pasta que o Git ignora e que nunca vai para o repositório público.
