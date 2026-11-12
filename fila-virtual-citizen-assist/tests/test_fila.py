"""Testes automatizados dos cenários mínimos do enunciado (seção 6 do PDF).

Executar a partir da pasta do projeto:
    python -m unittest discover -s tests -v

Cada teste sobe o servidor real em uma porta livre, com uma pasta de dados
temporária, e conversa com ele por HTTP — o mesmo caminho usado pelo navegador.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
_TMP = tempfile.TemporaryDirectory()
os.environ["FILA_DATA_DIR"] = _TMP.name

import app  # noqa: E402  (precisa da variável de ambiente acima)


class QueueApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app.STATE_FILE.unlink(missing_ok=True)
        self.server = app.create_server("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # ----------------------------------------------------------- utilitários
    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def arrive(self) -> tuple[int, dict]:
        return self.request("POST", "/api/arrivals", {})

    def complete(self, minutes: float = 7) -> tuple[int, dict]:
        return self.request("POST", "/api/completions", {"duration_minutes": minutes})

    # ----------------------------------------------------------- cenário 1
    def test_1_chegada_de_novos_cidadaos(self) -> None:
        for expected in (1, 2, 3):
            status, state = self.arrive()
            self.assertEqual(status, 200)
            self.assertEqual(state["queue_count"], expected)
        self.assertEqual([p["id"] for p in state["queue"]], [1, 2, 3])
        self.assertEqual([p["ahead_at_arrival"] for p in state["queue"]], [0, 1, 2])
        self.assertEqual(state["events"][0]["type"], "chegada")
        self.assertIn("T", state["events"][0]["at"])          # horário ISO 8601

    # ----------------------------------------------------------- cenário 2
    def test_2_conclusao_de_atendimentos(self) -> None:
        self.arrive()
        self.arrive()
        status, state = self.complete(8)
        self.assertEqual(status, 200)
        self.assertEqual(state["queue_count"], 1)
        self.assertEqual(state["completed_count"], 1)
        self.assertEqual(state["queue"][0]["id"], 2)                 # FIFO
        self.assertEqual(state["queue"][0]["waited_service_minutes"], 8.0)
        self.assertEqual(state["model"]["observed_points"], 1)
        self.assertEqual(state["events"][0]["type"], "conclusao")

    # ----------------------------------------------------------- cenário 3
    def test_3_saida_com_fila_vazia_e_bloqueada(self) -> None:
        status, body = self.complete()
        self.assertEqual(status, 409)
        self.assertIn("vazia", body["error"])
        self.assertEqual(body["state"]["queue_count"], 0)
        self.assertEqual(body["state"]["completed_count"], 0)
        self.assertEqual(body["state"]["rejected_count"], 1)
        self.assertEqual(body["state"]["events"][0]["type"], "rejeitado")

    # ----------------------------------------------------------- cenário 4
    def test_4_atualizacao_da_estimativa_de_espera(self) -> None:
        _, empty = self.request("GET", "/api/state")
        self.assertEqual(empty["conventional_wait_minutes"], 0)
        _, one = self.arrive()
        _, three = (self.arrive(), self.arrive())[1]
        self.assertGreater(three["ai_wait_minutes"], one["ai_wait_minutes"])
        self.assertAlmostEqual(three["conventional_wait_minutes"],
                               round(3 * three["average_service_minutes"], 1), delta=0.11)
        self.complete(20)                                             # atendimentos longos
        _, after = self.complete(20)                                  # pessoa 2 esperou 20 min
        self.assertGreater(after["average_service_minutes"], three["average_service_minutes"])
        self.assertEqual(after["model"]["observed_points"], 2)
        before = (three["model"]["intercept"], three["model"]["slope"])
        self.assertNotEqual((after["model"]["intercept"], after["model"]["slope"]), before)

    # ----------------------------------------------------------- validações extras
    def test_duracao_invalida_e_rejeitada(self) -> None:
        self.arrive()
        for invalid in (0, -5, 241, "abc"):
            status, body = self.request("POST", "/api/completions", {"duration_minutes": invalid})
            self.assertEqual(status, 400, invalid)
            self.assertEqual(body["state"]["queue_count"], 1)

    def test_json_invalido_e_rota_desconhecida(self) -> None:
        req = urllib.request.Request(self.base + "/api/arrivals", data=b"{x", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()
        status, _ = self.request("POST", "/api/qualquer", {})
        self.assertEqual(status, 404)

    def test_capacidade_maxima(self) -> None:
        state = app.empty_state()
        for _ in range(app.MAX_QUEUE):
            app.register_arrival(state)
        with self.assertRaises(app.QueueError):
            app.register_arrival(state)

    def test_estado_sobrevive_reinicio_do_servidor(self) -> None:
        self.arrive()
        self.arrive()
        self.tearDown()                                               # "desliga" o servidor
        self.server = app.create_server("127.0.0.1", 0)               # e liga de novo
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        _, state = self.request("GET", "/api/state")
        self.assertEqual(state["queue_count"], 2)
        self.assertEqual(len(state["events"]), 2)

    def test_persistencia_e_exportacao_csv(self) -> None:
        self.arrive()
        self.assertTrue(app.STATE_FILE.exists())
        with urllib.request.urlopen(self.base + "/api/events.csv", timeout=5) as response:
            text = response.read().decode("utf-8-sig")
        self.assertIn("data_hora;tipo;fila_apos;origem;descricao", text)
        self.assertIn(";chegada;1;", text)


class ModelTest(unittest.TestCase):
    def test_regressao_recupera_reta_conhecida(self) -> None:
        rows = [{"queue_size": q, "service_minutes": 1.0, "wait_minutes": 2 + 3 * q} for q in range(6)]
        intercept, slope = app.regression(rows)
        self.assertAlmostEqual(intercept, 2.0)
        self.assertAlmostEqual(slope, 3.0)

    def test_validacao_otimizada_igual_a_reajuste_completo(self) -> None:
        rows = app.load_training_rows()
        errors = []
        for index, row in enumerate(rows):                           # versão O(n²) de referência
            intercept, slope = app.regression(rows[:index] + rows[index + 1:])
            errors.append(abs(max(0.0, intercept + slope * app.feature(row)) - row["wait_minutes"]))
        self.assertAlmostEqual(app.evaluate(rows)["mae_ai"], round(sum(errors) / len(errors), 2))

    def test_ia_tem_erro_menor_que_media_historica_nos_dados_simulados(self) -> None:
        result = app.evaluate(app.load_training_rows())
        self.assertEqual(result["samples"], 60)
        self.assertLess(result["mae_ai"], result["mae_conventional"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
