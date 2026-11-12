# Citizen Assist AI — Fila virtual

Protótipo acadêmico de um sistema de gerenciamento de filas para a Global Solution 2026.2 de Arquitetura e Organização de Computadores. O navegador funciona como painel do cidadão/operador; o servidor local recebe as ações, atualiza a fila, registra horários e calcula duas estimativas de espera.

## Executar

Requisitos: Python 3.10 ou superior. Não é necessário instalar bibliotecas externas.

1. Abra o terminal nesta pasta.
2. Execute `python app.py` (no Windows também pode usar `py app.py`).
3. Abra <http://127.0.0.1:8000> no navegador.
4. Use **Registrar chegada** e **Concluir atendimento**. Ao concluir, informe a duração aproximada do atendimento em minutos.
5. Para encerrar o servidor, volte ao terminal e pressione `Ctrl+C`.

A fila, os eventos e as durações informadas ficam em `data/estado.json`, criado automaticamente e ignorado pelo Git. Exclua esse arquivo com o servidor encerrado para reiniciar a demonstração. O CSV histórico de exemplo permanece preservado.

## O que o protótipo faz

- registra chegadas com identificador e horário;
- conclui o atendimento da pessoa mais antiga da fila;
- impede conclusão quando a fila está vazia e valida a duração informada;
- mantém a quantidade aguardando e o total de atendimentos concluídos;
- calcula uma estimativa convencional (`pessoas na fila × duração média`) e compara com uma regressão linear simples;
- mostra o painel e o histórico recente, atualizados automaticamente;
- usa dados sintéticos claramente identificados em `data/historico_simulado.csv`.

## Pastas e entregáveis

- `app.py`: servidor HTTP, API, persistência e cálculo da estimativa;
- `static/`: interface acessível pelo navegador;
- `data/historico_simulado.csv`: amostra didática, não representa pacientes ou medições reais;
- `docs/arquitetura.md`: diagrama e fluxo de informação;
- `docs/relatorio-tecnico.md`: análise de CPU, memória, entrada/saída, rede, modelo e limitações;
- `docs/plano-de-testes.md`: quatro cenários mínimos e resultados de referência;
- `docs/roteiro-demonstracao.md`: fala sugerida para o vídeo de até 5 minutos.

## Limites e próximos passos

O protótipo simula botões físicos por controles na página e roda na máquina que inicia o servidor. A conexão HTTP local demonstra a troca entre navegador e servidor; para acesso público pela internet, hospede o servidor em um ambiente acessível e configure HTTPS, autenticação e armazenamento adequado. A regressão é didática, usa amostra pequena e não deve ser usada para prometer tempos reais.
