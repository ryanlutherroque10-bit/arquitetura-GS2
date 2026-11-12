# Terminal de fila — Raspberry Pi Pico W (Wokwi)

Firmware MicroPython que transforma um **Raspberry Pi Pico W** em um terminal físico de fila: botões reais de entrada, potenciômetro para informar a duração do atendimento, display OLED e LEDs de saída. Toda a lógica da fila e a previsão por regressão linear rodam no próprio microcontrolador RP2040.

## Como simular no navegador (sem placa)

1. Acesse <https://wokwi.com/projects/new/micropython-pi-pico-w>.
2. Na aba **main.py**, apague o conteúdo e cole o arquivo [`main.py`](main.py) desta pasta.
3. Na aba **diagram.json**, apague o conteúdo e cole o arquivo [`diagram.json`](diagram.json).
4. Clique no botão verde ▶ (*Start the simulation*).
5. Opcional: faça login no Wokwi e clique em **Save** para gerar um link público do projeto (coloque o link no relatório e no README principal).

Testado em 12/11/2026 com MicroPython v1.28.0 no Wokwi.

## Ligações (pinagem)

| Componente | Pino do Pico W | Interface | Função |
| --- | --- | --- | --- |
| Botão verde "Chegada" | GP14 + GND | GPIO digital, pull-up interno, interrupção na borda de descida | registra chegada |
| Botão azul "Concluir" | GP15 + GND | GPIO digital, pull-up interno, interrupção | conclui o atendimento da primeira pessoa |
| Potenciômetro | GP26 (ADC0), 3V3, GND | conversor analógico-digital de 12 bits | duração do atendimento (1 a 30 min) |
| Display OLED SSD1306 128×64 | GP4 (SDA), GP5 (SCL), 3V3, GND | I2C0 a 400 kHz, endereço 0x3C | mostra fila, concluídos, estimativas |
| LED verde + resistor 220 Ω | GP16 | GPIO digital (saída) | operação aceita |
| LED vermelho + resistor 220 Ω | GP17 | GPIO digital (saída) | operação recusada (fila vazia/cheia) |
| LED da placa | "LED" (via CYW43439) | — | pisca a cada atualização do display |
| Monitor serial | USB | USB CDC | registro de eventos em CSV com data/hora |

## O que aparece no display

```
CITIZEN ASSIST
Fila: 3/32
Concluidos: 2
Conv: 21.7 min      <- pessoas × duração média
IA:   23.0 min      <- regressão linear
Dur.: 7.0 min       <- leitura do potenciômetro
+ Chegada #5        <- última operação
```

## Registro de eventos (monitor serial)

Saída real da simulação (cenários mínimos do enunciado):

```
data_hora;tipo;fila;concluidos;detalhe
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

O relógio do simulador começa em 01/01/2021. O firmware ajusta o RTC para a data de início da demonstração (`DEMO_START`). Em uma placa real com Wi-Fi, a sincronização seria feita com `ntptime.settime()`.

## Decisões de projeto

- **Interrupções + laço principal**: a rotina de interrupção apenas filtra o repique (200 ms) e marca uma flag. O processamento acontece fora da interrupção, como recomendado em sistemas embarcados.
- **Buffer circular de tamanho fixo** (`array`): 32 posições × 11 bytes = 352 bytes. O consumo de RAM é previsível e não há fragmentação de heap.
- **Regressão incremental**: em vez de guardar todas as observações, o firmware mantém cinco somatórios (n, Σx, Σy, Σx², Σxy). Cada atendimento concluído atualiza o modelo em O(1) de tempo e memória.
- **Mesmas regras do servidor**: FIFO, sem contagem negativa, capacidade máxima e "relógio de serviço" para medir a espera (soma das durações dos atendimentos feitos enquanto a pessoa aguardava).

## Limitação conhecida da simulação

O Pico W tem Wi-Fi (chip CYW43439), mas no Wokwi público ele associa à rede `Wokwi-GUEST` e não recebe endereço IP (DHCP sem resposta; testes com IP fixo deram `ETIMEDOUT`). Por isso a comunicação em rede do protótipo é demonstrada pelo servidor web (`../app.py`). Em uma placa real, o terminal enviaria as mesmas operações para a API `POST /api/arrivals` e `POST /api/completions`.
