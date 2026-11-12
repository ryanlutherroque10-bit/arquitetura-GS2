"""Protótipo local de fila virtual usando apenas a biblioteca padrão do Python."""

from __future__ import annotations

import csv
import json
import math
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
STATE_FILE = DATA / "estado.json"
HISTORY_FILE = DATA / "historico_simulado.csv"
HOST = "127.0.0.1"
PORT = 8000
LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_training_rows() -> list[dict[str, float]]:
    with HISTORY_FILE.open("r", encoding="utf-8", newline="") as stream:
        return [
            {
                "queue_size": float(row["pessoas_a_frente"]),
                "service_minutes": float(row["duracao_media_min"]),
                "wait_minutes": float(row["espera_observada_min"]),
            }
            for row in csv.DictReader(stream, delimiter=";")
        ]


def load_state() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = {"queue": [], "events": [], "service_durations": [], "next_id": 1}
        save_state(state)
        return state
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state.get("queue"), list) or not isinstance(state.get("events"), list):
            raise ValueError("Estrutura inválida")
        state.setdefault("service_durations", [])
        state.setdefault("next_id", 1)
        return state
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"Não foi possível ler {STATE_FILE.name}: {error}") from error


def save_state(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def regression(rows: list[dict[str, float]]) -> tuple[float, float]:
    """Regressão linear y = intercepto + inclinação * (fila * duração média)."""
    samples = [
        (row["queue_size"] * row["service_minutes"], row["wait_minutes"])
        for row in rows
    ]
    if len(samples) < 2:
        return 0.0, 1.0
    mean_x = sum(x for x, _ in samples) / len(samples)
    mean_y = sum(y for _, y in samples) / len(samples)
    denominator = sum((x - mean_x) ** 2 for x, _ in samples)
    if denominator == 0:
        return max(0.0, mean_y), 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in samples) / denominator
    intercept = mean_y - slope * mean_x
    return intercept, slope


def get_dashboard(state: dict) -> dict:
    simulated = load_training_rows()
    service_durations = [float(value) for value in state["service_durations"] if float(value) > 0]
    service_minutes = (
        sum(service_durations) / len(service_durations)
        if service_durations
        else sum(row["service_minutes"] for row in simulated) / len(simulated)
    )
    queue_size = len(state["queue"])
    conventional = queue_size * service_minutes

    actual_rows = state.get("wait_observations", [])
    training_rows = simulated + actual_rows
    intercept, slope = regression(training_rows)
    predicted = max(0.0, intercept + slope * (queue_size * service_minutes))
    return {
        "queue_count": queue_size,
        "completed_count": state.get("completed_count", 0),
        "average_service_minutes": round(service_minutes, 1),
        "conventional_wait_minutes": round(conventional, 1),
        "ai_wait_minutes": round(predicted, 1),
        "model": "Regressão linear simples sobre fila × duração média do atendimento",
        "training_points": len(training_rows),
        "training_source": "dados simulados + atendimentos observados nesta execução",
        "queue": state["queue"],
        "events": state["events"][:20],
        "updated_at": now_iso(),
    }


def add_event(state: dict, event_type: str, description: str) -> None:
    state["events"].insert(0, {"type": event_type, "description": description, "at": now_iso()})
    del state["events"][250:]


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CitizenAssistQueue/1.0"

    def log_message(self, _format: str, *_args) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096:
            raise ValueError("Requisição muito grande.")
        if length == 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("O corpo deve ser um objeto JSON.")
        return payload

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            with LOCK:
                self.send_json(200, get_dashboard(load_state()))
            return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(404, "Arquivo não encontrado")
            return
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "text/javascript; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            with LOCK:
                state = load_state()
                if path == "/api/arrivals":
                    person = {"id": state["next_id"], "arrived_at": now_iso()}
                    state["next_id"] += 1
                    state["queue"].append(person)
                    add_event(state, "chegada", f"Pessoa {person['id']} entrou na fila.")
                elif path == "/api/completions":
                    if not state["queue"]:
                        self.send_json(409, {"error": "A fila está vazia; não há atendimento para concluir."})
                        return
                    duration = float(payload.get("duration_minutes", 0))
                    if not math.isfinite(duration) or not 0 < duration <= 240:
                        raise ValueError("Informe uma duração entre 0 e 240 minutos.")
                    person = state["queue"].pop(0)
                    arrived = datetime.fromisoformat(person["arrived_at"])
                    elapsed = max(0.0, (datetime.now(arrived.tzinfo) - arrived).total_seconds() / 60)
                    observed_wait = max(0.0, elapsed - duration)
                    ahead = len(state["queue"])
                    state.setdefault("wait_observations", []).append({
                        "queue_size": float(ahead),
                        "service_minutes": duration,
                        "wait_minutes": observed_wait,
                    })
                    state["wait_observations"] = state["wait_observations"][-500:]
                    state["service_durations"].append(duration)
                    state["service_durations"] = state["service_durations"][-500:]
                    state["completed_count"] = state.get("completed_count", 0) + 1
                    add_event(state, "conclusao", f"Atendimento da pessoa {person['id']} concluído; duração informada: {duration:.1f} min.")
                else:
                    self.send_json(404, {"error": "Operação desconhecida."})
                    return
                save_state(state)
                self.send_json(200, get_dashboard(state))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error) or "Dados inválidos."})


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    load_state()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"Citizen Assist AI disponível em http://{HOST}:{PORT}")
    print("Para encerrar, pressione Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
