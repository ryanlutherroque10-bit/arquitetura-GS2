# Citizen Assist AI — terminal de fila no Raspberry Pi Pico W (RP2040) em MicroPython.
#
# Entradas : botão verde (GP14) = chegada | botão azul (GP15) = concluir atendimento
#            potenciômetro (GP26 / ADC0) = duração do atendimento (1 a 30 min)
# Saídas   : display OLED SSD1306 128x64 via I2C0 (SDA GP4, SCL GP5)
#            LED verde (GP16) = operação aceita | LED vermelho (GP17) = operação recusada
#            porta serial USB = registro de eventos com data/hora (CSV)
# Processo : fila FIFO em buffer circular de tamanho fixo, validação, estimativa
#            convencional e regressão linear com aprendizado incremental.
#
# Simulação: https://wokwi.com (Raspberry Pi Pico W + MicroPython) — ver README desta pasta.

import gc
import time
from array import array

import framebuf
from machine import ADC, I2C, RTC, Pin, freq

# ---------------------------------------------------------------- driver do display
# Driver mínimo do OLED SSD1306 (I2C) usando framebuf. O quadro de 128x64 pixels
# (1 bit/pixel = 1024 bytes) fica na RAM do RP2040 e é enviado a cada show().
_INIT = (
    0xAE,        # display desligado
    0x20, 0x00,  # endereçamento horizontal
    0x40,        # linha inicial 0
    0xA1,        # remapeamento de segmentos
    0xA8, 63,    # multiplex 64 linhas
    0xC8,        # varredura COM invertida
    0xD3, 0x00,  # deslocamento vertical 0
    0xDA, 0x12,  # configuração dos pinos COM
    0xD5, 0x80,  # clock do display
    0xD9, 0xF1,  # pré-carga
    0xDB, 0x30,  # nível VCOMH
    0x81, 0xFF,  # contraste
    0xA4,        # exibe o conteúdo da RAM
    0xA6,        # modo normal (não invertido)
    0x8D, 0x14,  # charge pump ligado
    0xAF,        # display ligado
)


class SSD1306_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.width, self.height, self.i2c, self.addr = width, height, i2c, addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        for command in _INIT:
            self.cmd(command)
        self.fill(0)
        self.show()

    def cmd(self, command):
        self.i2c.writeto(self.addr, bytes((0x80, command)))

    def show(self):
        for command in (0x21, 0, self.width - 1, 0x22, 0, self.pages - 1):
            self.cmd(command)
        self.i2c.writeto(self.addr, b"\x40" + self.buffer)


# ---------------------------------------------------------------- hardware
I2C_BUS = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
OLED = SSD1306_I2C(128, 64, I2C_BUS)
BTN_ARRIVAL = Pin(14, Pin.IN, Pin.PULL_UP)     # nível baixo = pressionado
BTN_COMPLETE = Pin(15, Pin.IN, Pin.PULL_UP)
POT = ADC(26)                                  # ADC de 12 bits (lido em 16 bits)
LED_OK = Pin(16, Pin.OUT)
LED_ERR = Pin(17, Pin.OUT)
LED_BOARD = Pin("LED", Pin.OUT)                # LED da placa (ligado ao CYW43439)

DEBOUNCE_MS = 200

# Relógio de tempo real (RTC) interno do RP2040. O simulador inicia em 2021-01-01;
# sem rede no simulador, ajustamos a data/hora de início da demonstração aqui.
# Em uma placa real com Wi-Fi, usar ntptime.settime() para sincronizar.
DEMO_START = (2026, 11, 12, 3, 9, 0, 0, 0)     # (ano, mês, dia, dia_semana, h, min, s, sub)
if time.localtime()[0] < 2024:
    RTC().datetime(DEMO_START)

# ---------------------------------------------------------------- memória
# Buffer circular de capacidade fixa: o consumo de RAM é conhecido na compilação.
CAPACITY = 32
q_id = array("H", [0] * CAPACITY)              # 2 bytes por posição
q_ahead = array("B", [0] * CAPACITY)           # 1 byte: pessoas à frente na chegada
q_avg = array("f", [0.0] * CAPACITY)           # 4 bytes: média de atendimento na chegada
q_wait = array("f", [0.0] * CAPACITY)          # 4 bytes: espera acumulada (min)
head = 0
count = 0
next_id = 1
completed = 0
rejected = 0

# ---------------------------------------------------------------- modelo
# Somatórios da regressão y = a + b·x, x = pessoas à frente × duração média.
# Inicializados com os 60 registros SIMULADOS de data/historico_simulado.csv
# (n, Σx, Σy, Σx², Σxy). Cada atendimento concluído soma uma observação real:
# o aprendizado é incremental e usa memória constante (5 números).
reg_n, reg_sx, reg_sy, reg_sxx, reg_sxy = 60, 2199.5, 2337.0, 116315.25, 123683.5
service_sum, service_n = 7.233 * 60, 60        # média histórica simulada = 7,2 min


def regression():
    den = reg_n * reg_sxx - reg_sx * reg_sx
    if den == 0:
        return 0.0, 1.0
    b = (reg_n * reg_sxy - reg_sx * reg_sy) / den
    a = (reg_sy - b * reg_sx) / reg_n
    return a, b


def average_service():
    return service_sum / service_n


def estimates():
    avg = average_service()
    conventional = count * avg
    a, b = regression()
    return conventional, max(0.0, a + b * conventional)


# ---------------------------------------------------------------- utilitários
def timestamp():
    t = time.localtime()
    return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]


def log(kind, detail):
    # Formato CSV: data_hora;tipo;fila;concluidos;detalhe
    print("%s;%s;%d;%d;%s" % (timestamp(), kind, count, completed, detail))


def read_duration():
    raw = POT.read_u16()                       # 0..65535
    minutes = 1 + raw * 29 / 65535             # 1..30 min
    return round(minutes * 2) / 2              # passos de 0,5 min


def flash(led):
    led.on()
    time.sleep_ms(120)
    led.off()


status_line = "Pronto"


def draw():
    conventional, ai = estimates()
    OLED.fill(0)
    OLED.fill_rect(0, 0, 128, 10, 1)
    OLED.text("CITIZEN ASSIST", 8, 1, 0)
    OLED.text("Fila: %d/%d" % (count, CAPACITY), 0, 12)
    OLED.text("Concluidos: %d" % completed, 0, 20)
    OLED.text("Conv: %.1f min" % conventional, 0, 28)
    OLED.text("IA:   %.1f min" % ai, 0, 36)
    OLED.text("Dur.: %.1f min" % read_duration(), 0, 44)
    OLED.text(status_line[:16], 0, 56)
    OLED.show()


# ---------------------------------------------------------------- regras da fila
def arrival():
    global count, next_id, status_line, rejected
    if count >= CAPACITY:
        rejected += 1
        status_line = "! FILA CHEIA"
        log("rejeitado", "capacidade maxima")
        flash(LED_ERR)
        return
    tail = (head + count) % CAPACITY
    q_id[tail] = next_id
    q_ahead[tail] = count
    q_avg[tail] = average_service()
    q_wait[tail] = 0.0
    count += 1
    status_line = "+ Chegada #%d" % next_id
    log("chegada", "pessoa=%d" % next_id)
    next_id = next_id + 1 if next_id < 65535 else 1
    flash(LED_OK)


def completion():
    global head, count, completed, status_line, rejected
    global reg_n, reg_sx, reg_sy, reg_sxx, reg_sxy, service_sum, service_n
    if count == 0:                             # impede contagem negativa
        rejected += 1
        status_line = "! FILA VAZIA"
        log("rejeitado", "conclusao com fila vazia")
        flash(LED_ERR)
        return
    duration = read_duration()
    person, ahead, avg, waited = q_id[head], q_ahead[head], q_avg[head], q_wait[head]
    head = (head + 1) % CAPACITY
    count -= 1
    for i in range(count):                     # quem ficou esperou mais 'duration' min
        q_wait[(head + i) % CAPACITY] += duration
    x = ahead * avg                            # observação real -> treina o modelo
    reg_n += 1
    reg_sx += x
    reg_sy += waited
    reg_sxx += x * x
    reg_sxy += x * waited
    service_sum += duration
    service_n += 1
    completed += 1
    status_line = "- Atendido #%d" % person
    log("conclusao", "pessoa=%d;duracao=%.1f;espera=%.1f" % (person, duration, waited))
    flash(LED_OK)


# ---------------------------------------------------------------- interrupções
pending = {"arrival": False, "complete": False}
last_irq = {"arrival": 0, "complete": 0}


def make_handler(name):
    def handler(_pin):
        now = time.ticks_ms()
        if time.ticks_diff(now, last_irq[name]) > DEBOUNCE_MS:
            last_irq[name] = now
            pending[name] = True               # trabalho pesado fica no laço principal
    return handler


BTN_ARRIVAL.irq(trigger=Pin.IRQ_FALLING, handler=make_handler("arrival"))
BTN_COMPLETE.irq(trigger=Pin.IRQ_FALLING, handler=make_handler("complete"))

# ---------------------------------------------------------------- laço principal
gc.collect()
print("data_hora;tipo;fila;concluidos;detalhe")
log("inicio", "CPU=%d MHz;RAM livre=%d bytes;RAM usada=%d bytes;capacidade=%d"
    % (freq() // 1_000_000, gc.mem_free(), gc.mem_alloc(), CAPACITY))
a0, b0 = regression()
log("modelo", "a=%.3f;b=%.3f;base=%d registros simulados" % (a0, b0, reg_n))

last_draw = 0
last_report = time.ticks_ms()
while True:
    if pending["arrival"]:
        pending["arrival"] = False
        arrival()
        last_draw = 0
    if pending["complete"]:
        pending["complete"] = False
        completion()
        last_draw = 0
    now = time.ticks_ms()
    if last_draw == 0 or time.ticks_diff(now, last_draw) > 250:
        draw()                                 # atualiza o display ~4 vezes/s
        last_draw = now
        LED_BOARD.toggle()                     # "batimento" do sistema
    if time.ticks_diff(now, last_report) > 30_000:
        gc.collect()
        a, b = regression()
        log("status", "RAM livre=%d bytes;a=%.3f;b=%.3f;n=%d" % (gc.mem_free(), a, b, reg_n))
        last_report = now
    time.sleep_ms(10)
