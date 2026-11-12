"""Servidor da fila virtual Citizen Assist AI (somente biblioteca padrão do Python).

Responsabilidades:
- receber as operações de entrada (chegada / conclusão) via HTTP + JSON;
- validar regras da fila (FIFO, sem contagem negativa, capacidade, duração);
- persistir estado e registro de eventos com horário em data/estado.json;
- calcular a estimativa convencional e a previsão por regressão linear;
- servir o painel web (static/) e exportar os eventos em CSV.

Variáveis de ambiente opcionais:
- FILA_HOST (padrão 127.0.0.1; use 0.0.0.0 para aceitar outros dispositivos da rede)
- FILA_PORT (padrão 8000)
- FILA_DATA_DIR (padrão ./data; usado pelos testes automatizados)
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HISTORY_FILE = ROOT / "data" / "historico_simulado.csv"
DATA = Path(os.environ.get("FILA_DATA_DIR", ROOT / "data"))
STATE_FILE = DATA / "estado.json"
HOST = os.environ.get("FILA_HOST", "127.0.0.1")
PORT = int(os.environ.get("FILA_PORT", "8000"))

MAX_QUEUE = 200            # capacidade máxima da fila (evita crescimento sem limite)
MAX_EVENTS = 250           # eventos mantidos no registro
MAX_OBSERVATIONS = 500     # observações reais usadas no treinamento
MIN_DURATION, MAX_DURATION = 0.0, 240.0
LOCK = threading.Lock()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Dados de treinamento e modelo
# --------------------------------------------------------------------------- #
def load_training_rows() -> list[dict[str, float]]:
    """Lê o histórico SIMULADO (sintético) usado como base inicial do modelo."""
    with HISTORY_FILE.open("r", encoding="utf-8", newline="") as stream:
        return [
            {
                "queue_size": float(row["pessoas_a_frente"]),
                "service_minutes": float(row["duracao_media_min"]),
                "wait_minutes": float(row["espera_observada_min"]),
                "source": "simulado",
            }
            for row in csv.DictReader(stream, delimiter=";")
        ]


def feature(row: dict) -> float:
    """Variável explicativa x = pessoas à frente × duração média do atendimento."""
    return float(row["queue_size"]) * float(row["service_minutes"])


def regression(rows: list[dict]) -> tuple[float, float]:
    """Mínimos quadrados para y = a + b·x. Retorna (a, b)."""
    samples = [(feature(row), float(row["wait_minutes"])) for row in rows]
    if len(samples) < 2:
        return 0.0, 1.0
    mean_x = sum(x for x, _ in samples) / len(samples)
    mean_y = sum(y for _, y in samples) / len(samples)
    denominator = sum((x - mean_x) ** 2 for x, _ in samples)
    if denominator == 0:
        return max(0.0, mean_y), 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in samples) / denominator
    return mean_y - slope * mean_x, slope


def evaluate(rows: list[dict]) -> dict:
    """Validação cruzada leave-one-out: compara erro da média histórica e da regressão.

    Para cada ponto, a reta é ajustada sem ele e o erro é medido nele. Em vez de
    reajustar n vezes (O(n²)), retiramos o ponto dos somatórios Σx, Σy, Σx², Σxy:
    custo O(n), o que mantém a resposta da API rápida mesmo com 500+ observações.
    """
    count = len(rows)
    if count < 3:
        return {"samples": count, "mae_conventional": None, "mae_ai": None}
    points = [(feature(row), float(row["wait_minutes"])) for row in rows]
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    err_conv, err_ai = [], []
    n = count - 1
    for x, actual in points:
        rx, ry, rxx, rxy = sx - x, sy - actual, sxx - x * x, sxy - x * actual
        denominator = n * rxx - rx * rx
        if denominator == 0:
            slope, intercept = 0.0, ry / n
        else:
            slope = (n * rxy - rx * ry) / denominator
            intercept = (ry - slope * rx) / n
        err_conv.append(abs(x - actual))
        err_ai.append(abs(max(0.0, intercept + slope * x) - actual))
    return {
        "samples": len(rows),
        "mae_conventional": round(sum(err_conv) / len(err_conv), 2),
        "mae_ai": round(sum(err_ai) / len(err_ai), 2),
    }


# --------------------------------------------------------------------------- #
# Estado persistente
# --------------------------------------------------------------------------- #
def empty_state() -> dict:
    return {
        "queue": [],
        "events": [],
        "service_durations": [],
        "wait_observations": [],
        "completed_count": 0,
        "rejected_count": 0,
        "next_id": 1,
    }


def load_state() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = empty_state()
        save_state(state)
        return state
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state.get("queue"), list) or not isinstance(state.get("events"), list):
            raise ValueError("Estrutura inválida")
        for key, value in empty_state().items():
            state.setdefault(key, value)
        return state
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"Não foi possível ler {STATE_FILE.name}: {error}") from error


def save_state(state: dict) -> None:
    """Gravação atômica: escreve em arquivo temporário e substitui o original."""
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def average_service(state: dict, simulated: list[dict]) -> float:
    durations = [float(value) for value in state["service_durations"] if float(value) > 0]
    if durations:
        return sum(durations) / len(durations)
    return sum(row["service_minutes"] for row in simulated) / len(simulated)


def get_dashboard(state: dict) -> dict:
    simulated = load_training_rows()
    service_minutes = average_service(state, simulated)
    queue_size = len(state["queue"])
    conventional = queue_size * service_minutes

    observed = state.get("wait_observations", [])
    training_rows = simulated + observed
    intercept, slope = regression(training_rows)
    predicted = max(0.0, intercept + slope * (queue_size * service_minutes))
    return {
        "queue_count": queue_size,
        "queue_capacity": MAX_QUEUE,
        "completed_count": state.get("completed_count", 0),
        "rejected_count": state.get("rejected_count", 0),
        "average_service_minutes": round(service_minutes, 1),
        "conventional_wait_minutes": round(conventional, 1),
        "ai_wait_minutes": round(predicted, 1),
        "model": {
            "name": "Regressão linear simples",
            "equation": "espera = a + b × (pessoas na fila × duração média)",
            "intercept": round(intercept, 3),
            "slope": round(slope, 3),
            "training_points": len(training_rows),
            "simulated_points": len(simulated),
            "observed_points": len(observed),
            "evaluation": evaluate(training_rows),
        },
        "queue": state["queue"],
        "events": state["events"][:20],
        "updated_at": now_iso(),
    }


def add_event(state: dict, event_type: str, description: str, **extra) -> None:
    event = {"type": event_type, "description": description, "at": now_iso(),
             "queue_after": len(state["queue"]), **extra}
    state["events"].insert(0, event)
    del state["events"][MAX_EVENTS:]


# --------------------------------------------------------------------------- #
# Regras da fila (entrada → processamento → saída)
# --------------------------------------------------------------------------- #
class QueueError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def register_arrival(state: dict, source: str = "painel") -> dict:
    if len(state["queue"]) >= MAX_QUEUE:
        raise QueueError(409, f"Capacidade máxima da fila ({MAX_QUEUE}) atingida.")
    simulated = load_training_rows()
    person = {
        "id": state["next_id"],
        "arrived_at": now_iso(),
        "ahead_at_arrival": len(state["queue"]),
        "avg_service_at_arrival": round(average_service(state, simulated), 2),
        "waited_service_minutes": 0.0,
    }
    state["next_id"] += 1
    state["queue"].append(person)
    add_event(state, "chegada", f"Pessoa {person['id']} entrou na fila.", source=source)
    return person


def register_completion(state: dict, duration: float, source: str = "painel") -> dict:
    if not state["queue"]:
        raise QueueError(409, "A fila está vazia; não há atendimento para concluir.")
    if not math.isfinite(duration) or not MIN_DURATION < duration <= MAX_DURATION:
        raise QueueError(400, "Informe uma duração maior que 0 e até 240 minutos.")
    person = state["queue"].pop(0)
    # Relógio de serviço: a espera de cada pessoa é a soma das durações dos
    # atendimentos concluídos enquanto ela aguardava. Assim a demonstração é
    # coerente mesmo quando os cliques acontecem em poucos segundos.
    for waiting in state["queue"]:
        waiting["waited_service_minutes"] = round(float(waiting.get("waited_service_minutes", 0)) + duration, 2)
    state["wait_observations"].append({
        "queue_size": float(person.get("ahead_at_arrival", 0)),
        "service_minutes": float(person.get("avg_service_at_arrival", duration)),
        "wait_minutes": float(person.get("waited_service_minutes", 0)),
        "source": "observado",
    })
    state["wait_observations"] = state["wait_observations"][-MAX_OBSERVATIONS:]
    state["service_durations"].append(duration)
    state["service_durations"] = state["service_durations"][-MAX_OBSERVATIONS:]
    state["completed_count"] = state.get("completed_count", 0) + 1
    add_event(
        state, "conclusao",
        f"Atendimento da pessoa {person['id']} concluído; duração informada: {duration:.1f} min; "
        f"espera medida: {person.get('waited_service_minutes', 0):.1f} min.",
        source=source,
    )
    return person


def register_rejection(state: dict, reason: str, source: str) -> None:
    state["rejected_count"] = state.get("rejected_count", 0) + 1
    add_event(state, "rejeitado", f"Operação recusada: {reason}", source=source)


def events_csv(state: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["data_hora", "tipo", "fila_apos", "origem", "descricao"])
    for event in reversed(state["events"]):
        writer.writerow([event["at"], event["type"], event.get("queue_after", ""),
                         event.get("source", ""), event["description"]])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# --------------------------------------------------------------------------- #
# Camada de comunicação HTTP
# --------------------------------------------------------------------------- #
class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CitizenAssistQueue/2.0"

    def log_message(self, _format: str, *_args) -> None:
        return

    def send_body(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict) -> None:
        self.send_body(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 4096:
            raise QueueError(413, "Requisição muito grande.")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QueueError(400, "Corpo da requisição não é um JSON válido.") from error
        if not isinstance(payload, dict):
            raise QueueError(400, "O corpo deve ser um objeto JSON.")
        return payload

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            with LOCK:
                self.send_json(200, get_dashboard(load_state()))
            return
        if path == "/api/events.csv":
            with LOCK:
                body = events_csv(load_state())
            self.send_body(200, body, "text/csv; charset=utf-8",
                           {"Content-Disposition": 'attachment; filename="eventos-fila.csv"'})
            return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(404, "Arquivo não encontrado")
            return
        self.send_body(200, target.read_bytes(),
                       CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in ("/api/arrivals", "/api/completions", "/api/reset"):
            self.send_json(404, {"error": "Operação desconhecida."})
            return
        with LOCK:
            state = load_state()
            source = "painel"
            try:
                payload = self.read_json()
                source = str(payload.get("source", "painel"))[:20] or "painel"
                if path == "/api/arrivals":
                    register_arrival(state, source)
                elif path == "/api/completions":
                    try:
                        duration = float(payload.get("duration_minutes", 0))
                    except (TypeError, ValueError):
                        duration = float("nan")
                    register_completion(state, duration, source)
                else:
                    state = empty_state()
                    add_event(state, "reinicio", "Demonstração reiniciada.", source=source)
            except QueueError as error:
                register_rejection(state, str(error), source)
                save_state(state)
                self.send_json(error.status, {"error": str(error), "state": get_dashboard(state)})
                return
            save_state(state)
            self.send_json(200, get_dashboard(state))


def create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    DATA.mkdir(parents=True, exist_ok=True)
    load_state()
    return ThreadingHTTPServer((host, port), RequestHandler)


def main() -> None:
    server = create_server()
    shown_host = "127.0.0.1" if HOST in ("0.0.0.0", "") else HOST
    print(f"Citizen Assist AI disponível em http://{shown_host}:{PORT}")
    if HOST in ("0.0.0.0", ""):
        print("Aceitando conexões de outros dispositivos da rede local (use o IP deste computador).")
    print("Para encerrar, pressione Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
