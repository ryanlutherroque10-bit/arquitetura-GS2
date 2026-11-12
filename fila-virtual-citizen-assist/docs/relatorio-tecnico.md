# Relatório técnico — Sistema Inteligente de Gerenciamento de Filas Virtuais

| Campo | Informação |
| --- | --- |
| Disciplina | Arquitetura e Organização de Computadores |
| Projeto integrador | Citizen Assist AI — Global Solution 2026.2 |
| Turma | 1CC-FEV |
| Integrantes | **preencher: nome completo — RM** |
| Protótipo | Terminal Raspberry Pi Pico W (simulado no Wokwi) + servidor Python + painel web |
| Repositório | **preencher: link do GitHub** · Simulação Wokwi: **preencher: link salvo** |

## 1. Problema e objetivo

Em postos de saúde, secretarias e bibliotecas, o cidadão normalmente não sabe quantas pessoas estão na frente nem quanto vai esperar. O objetivo é construir um sistema computacional que registre entradas e saídas da fila, mostre o tamanho da fila, estime a espera com uma técnica simples de IA e disponibilize essas informações por um navegador.

A solução tem dois nós computacionais que seguem as mesmas regras:

1. **Terminal de atendimento — Raspberry Pi Pico W.** Botões físicos de entrada, potenciômetro, display OLED e LEDs de saída. A fila e a previsão rodam no microcontrolador RP2040. Simulado no Wokwi.
2. **Servidor + painel web.** Um servidor HTTP em Python (`app.py`) mantém a fila oficial, persiste os eventos e calcula as estimativas. Um painel no navegador consulta o servidor e oferece botões virtuais.

## 2. Arquitetura e componentes (Etapa 1)

O diagrama completo e o fluxo de informações estão em [arquitetura.md](arquitetura.md) e [diagrama-arquitetura.svg](diagrama-arquitetura.svg).

| Componente | Terminal Pico W | Servidor / painel |
| --- | --- | --- |
| CPU | RP2040, 2× ARM Cortex-M0+ a 125 MHz | x86-64 (AMD, 8 processadores lógicos no computador de teste) |
| Memória principal | SRAM 264 KB | RAM do computador |
| Armazenamento | Flash QSPI 2 MB | SSD (`data/`) |
| Entrada | botões GP14/GP15, potenciômetro GP26 (ADC0) | botões virtuais e campo de duração |
| Saída | OLED SSD1306 (I2C), LEDs GP16/GP17, serial USB | painel web e CSV de eventos |
| Comunicação | I2C, USB CDC, Wi-Fi 802.11n (CYW43439, previsto) | HTTP/1.1 + JSON sobre TCP/IP |

## 3. Implementação da fila virtual (Etapa 2)

| Requisito | Como foi atendido | Onde |
| --- | --- | --- |
| Registrar chegada por um botão | botão verde físico (GP14) e botão "Registrar chegada" no painel | `firmware-pico-w/main.py` `arrival()`; `app.py` `register_arrival()` |
| Registrar conclusão por outro botão | botão azul físico (GP15) e botão "Concluir atendimento" | `completion()`; `register_completion()` |
| Atualizar automaticamente a quantidade aguardando | contador recalculado em cada operação; OLED redesenhado a cada 250 ms; painel consulta o servidor a cada 3 s | `draw()`; `static/app.js` |
| Impedir contagem negativa e operações inválidas | conclusão com fila vazia é recusada (LED vermelho / HTTP 409); duração fora de 0–240 min (HTTP 400); fila cheia (capacidade 32 no Pico e 200 no servidor); JSON inválido (400); rota inexistente (404); toques repetidos filtrados (200 ms) | `completion()`, `QueueError` |
| Exibir o total de pessoas na fila | OLED "Fila: n/32"; cartão "Na fila" no painel | — |
| Registrar eventos e horários | log CSV na serial do Pico; no servidor, até 250 eventos com horário ISO 8601, origem e tamanho da fila, exportáveis em `GET /api/events.csv` | `log()`; `add_event()`, `events_csv()` |

**Estrutura de dados.** A fila é **FIFO** (primeiro a chegar, primeiro a ser atendido). No Pico W ela é um **buffer circular** com quatro vetores `array` de tamanho fixo. Os índices `head` e `count` evitam deslocar elementos na memória: enfileirar e desenfileirar custam O(1). No servidor, é uma lista Python persistida em JSON.

**Medição da espera ("relógio de serviço").** Quando um atendimento de duração *d* termina, todos que continuam na fila somam *d* à espera. Ao ser chamada, a pessoa gera uma observação real: (pessoas à frente quando chegou, duração média naquele momento, espera acumulada). Assim a demonstração é coerente mesmo com cliques feitos em segundos, e a espera é medida na mesma unidade da duração informada pelo operador.

## 4. Previsão inteligente de espera (Etapa 3)

### 4.1 Dados

`data/historico_simulado.csv` tem **60 registros simulados**, identificados na coluna `origem = simulado`. Eles foram gerados por [`tools/gerar_historico.py`](../tools/gerar_historico.py) com semente fixa (2026), então o arquivo pode ser reproduzido. O gerador modela um posto real de forma simples:

- de 0 a 10 pessoas à frente, com duração média histórica de 5 a 10 min;
- cada atendimento varia ±25% em torno da média;
- cada chamada entre atendimentos gasta cerca de 0,7 min (deslocamento, chamada pelo nome, conferência de documentos);
- há ruído de ±1 min.

Durante o uso, cada atendimento concluído vira uma nova observação, somada às simuladas.

### 4.2 Estimativa convencional (média histórica)

`espera_convencional = pessoas na fila × duração média dos atendimentos`

### 4.3 Modelo de IA — regressão linear simples

`espera_IA = a + b × x`, com `x = pessoas na fila × duração média`

Os coeficientes são obtidos por **mínimos quadrados**:

`b = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)`  e  `a = (Σy − b·Σx) / n`

Com os 60 registros simulados: **a = −0,100 min e b = 1,065**. O coeficiente *b* > 1 mostra que o modelo aprendeu que a espera real é cerca de 6,5% maior que a conta convencional, porque ela ignora o tempo de chamada entre atendimentos.

No Pico W a regressão é **incremental**: o firmware guarda só os cinco somatórios (n, Σx, Σy, Σx², Σxy), inicializados com os dados simulados, e soma cada nova observação. Ocupa 5 números na memória, qualquer que seja o número de atendimentos.

### 4.4 Comparação e avaliação

As duas estimativas foram comparadas por **validação cruzada *leave-one-out***: para cada registro, a reta é ajustada sem ele e o erro é medido nele. A métrica é o erro médio absoluto (MAE).

| Estimativa | MAE nos 60 registros simulados |
| --- | --- |
| Convencional (média histórica) | **3,35 min** |
| IA (regressão linear) | **2,86 min** (≈ 15% menor) |

O painel mostra as duas estimativas lado a lado, os coeficientes atuais, o MAE de cada uma e quantos registros são simulados ou observados. A comparação é recalculada a cada consulta.

**Exemplo:** com 3 pessoas na fila e média de 7,23 min, a convencional indica 21,7 min e a regressão 23,0 min.

**Ressalva:** os dados são sintéticos. O ganho de 15% vale para o processo que o gerador simula e não é uma promessa de precisão em um posto real. Para isso seria preciso coletar dados reais, anonimizados e autorizados.

## 5. Comunicação e visualização (Etapa 4)

O painel ([`static/`](../static)) é acessível por navegador em `http://127.0.0.1:8000`. Com `FILA_HOST=0.0.0.0`, outros computadores e celulares da mesma rede acessam pelo IP do servidor. Ele mostra:

- **quantidade atual de pessoas na fila** (cartão principal e lista com posição e espera acumulada);
- **tempo estimado de espera** (IA) e a estimativa convencional, com o erro médio de cada uma;
- **quantidade de atendimentos concluídos** e de operações inválidas recusadas;
- **atualização por comunicação com o sistema:** consulta `GET /api/state` a cada 3 s e, a cada clique, envia `POST` e redesenha com a resposta JSON. O indicador "Sistema conectado/desconectado" mostra se o servidor responde.

API REST:

| Método e rota | Função | Respostas |
| --- | --- | --- |
| `GET /api/state` | estado completo, estimativas, modelo e 20 últimos eventos | 200 |
| `POST /api/arrivals` | registra chegada | 200 · 409 fila cheia |
| `POST /api/completions` `{"duration_minutes": 7}` | conclui o primeiro da fila | 200 · 400 duração inválida · 409 fila vazia |
| `POST /api/reset` | reinicia a demonstração | 200 |
| `GET /api/events.csv` | exporta o registro de eventos | 200 |

## 6. Análise da arquitetura computacional (Etapa 5)

### 6.1 Processador selecionado — RP2040 (Raspberry Pi Pico W)

| Característica | Valor | Impacto no projeto |
| --- | --- | --- |
| Núcleos | 2× ARM Cortex-M0+ | o firmware usa 1 núcleo; o segundo fica livre para, por exemplo, a pilha de rede |
| Conjunto de instruções | ARMv6-M (Thumb/Thumb-2 parcial), 32 bits, arquitetura RISC *load/store* | instruções simples e compactas, boas para código em flash |
| Clock | até 133 MHz; **125 MHz medido** com `machine.freq()` no simulador | um clique é processado e o display redesenhado em poucos ms |
| Pipeline | 2 estágios (Cortex-M0+) | baixo consumo e latência de interrupção previsível |
| Organização de memória | barramento único para instruções e dados (**von Neumann**), matriz AHB-Lite ligando os dois núcleos aos bancos de SRAM e periféricos | código em flash e dados em SRAM disputam o mesmo barramento; o cache XIP de 16 KB reduz esse custo |
| Ponto flutuante | **sem FPU**; MicroPython usa `float` de 32 bits emulado em software (rotinas otimizadas na ROM) | a regressão funciona, mas cada operação float leva dezenas de ciclos; precisão de ~7 dígitos |
| Aritmética inteira | multiplicador de 1 ciclo e divisor inteiro em hardware | índices do buffer circular (`%`) são baratos |
| Interrupções | NVIC com prioridades; GPIO pode gerar IRQ por borda | botões tratados por interrupção, sem *polling* ativo |
| Periféricos usados | GPIO, ADC 12 bits (500 kS/s), I2C, USB 1.1, RTC; PIO + SPI ligam o chip Wi-Fi | — |
| Rádio (Pico W) | Infineon CYW43439: Wi-Fi 802.11n 2,4 GHz e Bluetooth | enlace previsto para enviar eventos à API |

**Comparação com o servidor:** a CPU x86-64 do computador de teste é uma arquitetura CISC com vários núcleos superescalares, execução fora de ordem, caches L1/L2/L3, FPU/SIMD e memória virtual com sistema operacional. Ela executa o CPython, que interpreta *bytecode*, e atende várias requisições em paralelo com *threads*. O servidor também roda sem mudanças em um Raspberry Pi 4/5 (ARM Cortex-A72/A76, ARMv8-A 64 bits, Linux), que seria a escolha para um posto real de baixo custo.

### 6.2 Organização da memória e estimativa de utilização

**RP2040 / Pico W**

| Região | Tamanho | Conteúdo no projeto |
| --- | --- | --- |
| ROM interna | 16 KB | *bootloader*, rotinas de ponto flutuante |
| SRAM | 264 KB (4 bancos de 64 KB intercalados + 2 de 4 KB) | pilha, variáveis do MicroPython, heap com os dados da aplicação |
| Flash externa QSPI | 2 MB | interpretador MicroPython e sistema de arquivos com `main.py`, executados via **XIP** (*execute in place*) com cache de 16 KB |
| Registradores de periféricos | mapeados em memória | GPIO, ADC, I2C, RTC acessados como endereços |

Medido no simulador (`gc.mem_alloc()` / `gc.mem_free()` logo após carregar o programa): **12.032 bytes usados e 193.408 bytes livres** no heap (~94% livre). Estimativa das estruturas da aplicação:

| Estrutura | Cálculo | Bytes |
| --- | --- | --- |
| `q_id` (uint16) | 32 × 2 | 64 |
| `q_ahead` (uint8) | 32 × 1 | 32 |
| `q_avg` (float32) | 32 × 4 | 128 |
| `q_wait` (float32) | 32 × 4 | 128 |
| *framebuffer* OLED | 128 × 64 / 8 | 1.024 |
| somatórios do modelo + contadores | ~10 objetos | < 200 |
| **Total de dados da aplicação** | | **≈ 1,6 KB** |

A maior parte dos 12 KB usados é o *bytecode* compilado de `main.py`, as funções e os objetos do MicroPython. Como os vetores têm tamanho fixo, o consumo não cresce durante o uso: o log de status a cada 30 s manteve ~193 KB livres.

**Servidor**

| Medida (Python 3.14, computador de teste) | Valor |
| --- | --- |
| Processo do servidor em execução (working set / memória privada) | 23,5 MB / 14,5 MB |
| Dados de estado na RAM com 50 chegadas e 30 conclusões (`tracemalloc`) | ~75 KiB |
| `estado.json` nesse cenário | 24,6 KiB |
| `estado.json` no pior caso (200 na fila, 250 eventos, 500 observações) | 161,5 KiB |
| `historico_simulado.csv` | 1,3 KB |

Os limites (`MAX_QUEUE = 200`, `MAX_EVENTS = 250`, `MAX_OBSERVATIONS = 500`) tornam o crescimento previsível: memória e disco ficam abaixo de 200 KiB de dados.

### 6.3 Operações de entrada, processamento e saída

| Etapa | Pico W | Servidor |
| --- | --- | --- |
| Entrada | GPIO com pull-up: 3,3 V = solto, 0 V = pressionado; interrupção na borda de descida. ADC converte a tensão do potenciômetro (0–3,3 V) em 12 bits, lidos em 16 bits (`read_u16`) e mapeados para 1–30 min | requisição HTTP com JSON validado (tamanho máximo de 4 KB, tipo e faixa dos campos) |
| Processamento | ISR curta → flag → laço principal; operações no buffer circular; média; regressão incremental | *thread* por requisição; *lock* para exclusão mútua; FIFO; relógio de serviço; regressão; validação cruzada O(n) |
| Saída | OLED via I2C (1 KB por quadro, ~4 quadros/s); LEDs; CSV pela USB | resposta JSON; painel redesenhado; CSV de eventos |

### 6.4 Comunicação entre dispositivos e protocolos

| Enlace | Protocolo / camada | Características |
| --- | --- | --- |
| RP2040 ↔ OLED | **I2C** a 400 kHz, endereço 0x3C | serial síncrono, 2 fios (SDA/SCL), mestre-escravo com endereçamento |
| RP2040 ↔ botões/LEDs | **GPIO** digital | sinais 0/3,3 V; LEDs com resistor de 220 Ω para limitar a corrente |
| RP2040 ↔ potenciômetro | **ADC** (SAR, 12 bits) | sinal analógico convertido em número |
| RP2040 ↔ computador | **USB 1.1 CDC** (porta serial virtual) | transporta o log CSV |
| RP2040 ↔ CYW43439 | **SPI** gerado pelo PIO | o rádio é um coprocessador; o RP2040 envia comandos e pacotes |
| Pico W ↔ rede (previsto) | **Wi-Fi 802.11n → IP → TCP → HTTP** | enviaria `POST /api/arrivals` e `/api/completions` à mesma API |
| Navegador ↔ servidor | **HTTP/1.1 + JSON sobre TCP/IP** (porta 8000) | modelo requisição-resposta; *polling* a cada 3 s |

### 6.5 Limitações de desempenho, memória e conectividade

**Desempenho**
- *Encontrado e corrigido durante os testes:* a primeira versão da validação cruzada reajustava a reta *n* vezes (O(n²)). Com 560 registros, cada `GET /api/state` levava **278 ms**, e o painel consulta a cada 3 s. Reescrita com somatórios (O(n)), caiu para **0,59 ms** com o mesmo resultado (há teste automatizado comparando as duas versões).
- O servidor relê e regrava o JSON a cada operação. É simples e seguro para um posto, mas limita a vazão de escrita ao desempenho do disco; em grande escala seria necessário um banco de dados transacional.
- O *polling* a cada 3 s gera tráfego mesmo sem mudanças. WebSockets ou *Server-Sent Events* dariam atualização instantânea com menos requisições.
- No Pico W, o MicroPython é interpretado e a matemática em `float` é emulada (sem FPU). Para esta carga é mais que suficiente, mas não serviria para modelos maiores.
- `flash()` bloqueia o laço por 120 ms. Toques dentro dessa janela ficam pendentes na flag e são processados logo depois, mas dois toques do mesmo botão nesse intervalo contam como um (o filtro de repique também é de 200 ms).

**Memória**
- Capacidade fixa de 32 pessoas no terminal e 200 no servidor. Acima disso a chegada é recusada, de propósito, para evitar estouro.
- O Pico guarda o modelo em `float` de 32 bits. Depois de milhares de observações, Σx² fica grande e a precisão relativa cai. Uma melhoria seria usar médias móveis ou reiniciar os somatórios periodicamente.
- O terminal perde a fila ao ser desligado (SRAM é volátil). Gravar na flash a cada evento desgastaria a memória (ciclos de escrita limitados); a fila oficial persistente é a do servidor.

**Conectividade**
- No Wokwi público o Pico W não obtém IP, então o enlace Wi-Fi não foi demonstrado na simulação. Na placa real é o próximo passo.
- O servidor usa HTTP sem criptografia e sem autenticação, adequado só para rede local de demonstração. Para internet pública: HTTPS, login de operador e limite de requisições.
- Sem rede, o painel mostra "Sistema desconectado" e o terminal continua funcionando sozinho. Uma versão futura guardaria os eventos e os reenviaria quando a conexão voltasse.

## 7. Testes e resultados

### 7.1 Testes automatizados (servidor)

`python -m unittest discover -s tests -v` sobe o servidor real em uma porta livre e conversa com ele por HTTP. Resultado: **12 testes, todos aprovados** (Python 3.14.7, 12/11/2026).

| Teste | Situação do enunciado | Resultado |
| --- | --- | --- |
| `test_1_chegada_de_novos_cidadaos` | (1) chegada | fila 1 → 2 → 3, ordem FIFO, evento com horário ✔ |
| `test_2_conclusao_de_atendimentos` | (2) conclusão | fila 2 → 1, concluídos 0 → 1, pessoa 2 vira a primeira e acumula 8 min de espera ✔ |
| `test_3_saida_com_fila_vazia_e_bloqueada` | (3) saída com fila vazia | HTTP 409, fila e concluídos continuam 0, evento `rejeitado` ✔ |
| `test_4_atualizacao_da_estimativa_de_espera` | (4) atualização da estimativa | espera sobe com a fila, convencional = fila × média, modelo muda após observações ✔ |
| `test_duracao_invalida_e_rejeitada` | operação inválida | 0, −5, 241 e "abc" → HTTP 400 sem alterar a fila ✔ |
| `test_json_invalido_e_rota_desconhecida` | operação inválida | 400 e 404 ✔ |
| `test_capacidade_maxima` | limite de memória | 201ª chegada recusada ✔ |
| `test_estado_sobrevive_reinicio_do_servidor` | persistência | fila e eventos continuam após desligar e religar o servidor ✔ |
| `test_persistencia_e_exportacao_csv` | registro de eventos | `estado.json` criado e CSV exportado ✔ |
| `test_regressao_recupera_reta_conhecida` | modelo | recupera a = 2 e b = 3 de dados exatos ✔ |
| `test_validacao_otimizada_igual_a_reajuste_completo` | desempenho | versão O(n) = versão O(n²) ✔ |
| `test_ia_tem_erro_menor_que_media_historica...` | IA | MAE IA < MAE convencional ✔ |

### 7.2 Terminal Raspberry Pi Pico W (Wokwi)

Sequência executada: concluir com a fila vazia → 3 chegadas → 3 conclusões, com o potenciômetro em 7,0 min. Log serial obtido:

```
2026-11-12 09:00:00;inicio;0;0;CPU=125 MHz;RAM livre=193408 bytes;RAM usada=12032 bytes;capacidade=32
2026-11-12 09:00:00;modelo;0;0;a=-0.100;b=1.065;base=60 registros simulados
2026-11-12 09:00:01;rejeitado;0;0;conclusao com fila vazia
2026-11-12 09:00:02;chegada;1;0;pessoa=1
2026-11-12 09:00:02;chegada;2;0;pessoa=2
2026-11-12 09:00:02;chegada;3;0;pessoa=3
2026-11-12 09:00:03;conclusao;2;1;pessoa=1;duracao=7.0;espera=0.0
2026-11-12 09:00:04;conclusao;1;2;pessoa=2;duracao=7.0;espera=7.0
2026-11-12 09:00:05;conclusao;0;3;pessoa=3;duracao=7.0;espera=14.0
```

A espera medida segue o esperado (0, 7 e 14 min). A conclusão com fila vazia foi bloqueada e o LED vermelho acendeu. Depois de duas observações reais, o log de status mostrou o modelo reajustado (a = −0,121, b = 1,066, n = 62). O potenciômetro em 400/1023 resultou em duração de 12,5 min, como calculado (1 + 400/1023 × 29 ≈ 12,3 → arredondado para 12,5).

### 7.3 Painel web

Sequência feita no navegador: concluir com fila vazia → 4 chegadas → concluir 10 min → concluir 10 min → nova chegada.

| Passo | Na fila | Convencional | IA | Concluídos | Recusadas |
| --- | --- | --- | --- | --- | --- |
| Concluir com fila vazia | 0 | 0 | 0 | 0 | 1 (mensagem "A fila está vazia") |
| 4 chegadas | 4 | 28,9 min | 30,7 min | 0 | 1 |
| Concluir (10 min) | 3 | 30,0 min | 31,9 min | 1 | 1 |
| Concluir (10 min) | 2 | 20,0 min | 21,3 min | 2 | 1 |
| Nova chegada | 3 | 30,0 min | 31,9 min | 2 | 1 |

A estimativa foi atualizada a cada operação. A média passou de 7,2 min (histórico) para 10 min (atendimentos reais), e o modelo passou a usar 60 simulados + 2 observados.

## 8. Conclusão

O protótipo mostra, em dois níveis de hardware, como entrada, processamento, memória, armazenamento, saída e comunicação trabalham juntos. No microcontrolador, interrupções de GPIO, conversão ADC, buffer circular em SRAM e barramento I2C formam um terminal físico de baixo custo. No servidor, a pilha TCP/IP, o protocolo HTTP, a persistência atômica em disco e o painel web levam a informação ao cidadão. A regressão linear, comparada com a média histórica por validação cruzada, reduziu o erro médio de 3,35 para 2,86 min nos dados simulados. As limitações medidas (desempenho do *polling* e da validação, precisão de `float32`, ausência de rede no simulador) apontam os próximos passos.

## Referências

- Raspberry Pi Ltd. *RP2040 Datasheet* e *Raspberry Pi Pico W Datasheet*.
- Arm Ltd. *Cortex-M0+ Technical Reference Manual*.
- MicroPython. Documentação da porta `rp2` (`machine.Pin`, `machine.ADC`, `machine.I2C`, `framebuf`).
- Wokwi. Simulador de eletrônica online — <https://wokwi.com>.
- Python Software Foundation. Documentação de `http.server`, `json`, `csv`, `unittest`.
