"""Gera data/historico_simulado.csv — DADOS SINTÉTICOS, não são medições reais.

Processo de simulação (semente fixa, reproduzível):
- pessoas_a_frente: inteiro entre 0 e 10;
- duracao_media_min: média histórica do posto naquele período (5 a 10 min);
- cada atendimento real varia ±25% em torno da média (distribuição normal);
- entre um atendimento e outro há ~0,7 min de chamada/deslocamento;
- espera_observada_min = soma dos atendimentos à frente + chamadas + ruído.

Por isso a estimativa convencional (pessoas × média) tende a subestimar a espera,
e a regressão linear consegue aprender esse viés a partir do histórico.

Uso: python tools/gerar_historico.py
"""

from __future__ import annotations

import random
from pathlib import Path

SEED = 2026
ROWS = 60
CALL_OVERHEAD_MIN = 0.7
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "historico_simulado.csv"


def main() -> None:
    rng = random.Random(SEED)
    lines = ["pessoas_a_frente;duracao_media_min;espera_observada_min;origem"]
    for _ in range(ROWS):
        ahead = rng.randint(0, 10)
        average = rng.choice([5.0, 6.0, 6.5, 7.0, 8.0, 10.0])
        services = sum(max(1.0, rng.gauss(average, average * 0.25)) for _ in range(ahead))
        noise = rng.gauss(0, 1.0) if ahead else 0.0
        wait = max(0.0, services + CALL_OVERHEAD_MIN * ahead + noise)
        lines.append(f"{ahead};{average:.1f};{wait:.1f};simulado")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{ROWS} linhas sintéticas gravadas em {OUTPUT}")


if __name__ == "__main__":
    main()
