# Plano de testes e evidências

Os quatro cenários mínimos do enunciado (seção 6) foram executados em três frentes: testes automatizados da API, terminal Raspberry Pi Pico W no Wokwi e painel web no navegador. Os resultados abaixo foram obtidos em 12/11/2026.

## Cenários mínimos

| Cenário | Ação | Resultado esperado | Evidência obtida |
| --- | --- | --- | --- |
| (1) Chegada de novos cidadãos | 3 toques no botão verde (Pico) / 4 cliques em **Registrar chegada** (painel) | fila cresce 1 a 1, em ordem de chegada, cada evento com horário | Pico: `chegada;1`, `chegada;2`, `chegada;3` com data e hora. Painel: fila 0 → 4, convencional 28,9 min, IA 30,7 min. Teste `test_1` ✔ |
| (2) Conclusão de atendimentos | botão azul com o potenciômetro em 7,0 min / **Concluir atendimento** com 10 min | a primeira pessoa sai (FIFO), concluídos +1, espera medida e estimativas atualizadas | Pico: `conclusao;pessoa=1;espera=0.0`, `pessoa=2;espera=7.0`, `pessoa=3;espera=14.0`. Painel: fila 4 → 3 → 2, concluídos 0 → 1 → 2. Teste `test_2` ✔ |
| (3) Tentativa de saída com fila vazia | concluir sem ninguém na fila | operação recusada; fila continua 0; concluídos não mudam | Pico: LED vermelho, display `! FILA VAZIA`, log `rejeitado;conclusao com fila vazia`. Painel: mensagem "A fila está vazia…", contador de recusadas = 1. API: HTTP 409. Teste `test_3` ✔ |
| (4) Atualização da estimativa de espera | registrar chegadas e concluir atendimentos com durações diferentes | convencional = fila × média; IA recalculada; modelo aprende com as observações | Painel: média 7,2 → 10,0 min após atendimentos de 10 min; base 60 simulados + 2 observados. Pico: modelo de a = −0,100/b = 1,065 para a = −0,121/b = 1,066 (n = 62). Teste `test_4` ✔ |

## Verificações adicionais

| Verificação | Resultado |
| --- | --- |
| Duração 0, −5, 241 ou texto | HTTP 400; fila inalterada (`test_duracao_invalida_e_rejeitada`) ✔ |
| JSON malformado / rota inexistente | HTTP 400 / 404 ✔ |
| Fila cheia | 201ª chegada recusada no servidor (`test_capacidade_maxima`); no Pico, a pessoa 32 entrou e a 33ª foi recusada (`rejeitado;capacidade maxima`) ✔ |
| Toques repetidos (repique do botão) | filtro de 200 ms na interrupção ✔ |
| Persistência | após reiniciar o servidor, fila e eventos continuam (`test_estado_sobrevive_reinicio_do_servidor`) ✔ |
| Exportação de eventos | `GET /api/events.csv` gera CSV com data/hora, tipo, fila e origem ✔ |
| Duas abas abertas | cada aba consulta `GET /api/state` a cada 3 s e mostra as mudanças feitas na outra (mostrar no vídeo) |
| Desempenho da API | `GET /api/state` em 0,59 ms com 560 registros de treinamento (antes da otimização: 278 ms) ✔ |

## Como repetir

```bash
cd fila-virtual-citizen-assist
python -m unittest discover -s tests -v
```

Para o terminal físico, siga [firmware-pico-w/README.md](../firmware-pico-w/README.md). O log da simulação aparece no monitor serial do Wokwi.

## Registro da execução

- **Data:** 12/11/2026
- **Responsável:** preencher
- **Ambiente:** Python 3.14.7 no Windows 11; navegador Chromium; Wokwi com Raspberry Pi Pico W e MicroPython v1.28.0
- **Resultado geral:** 12/12 testes automatizados aprovados; os quatro cenários reproduzidos manualmente no painel e no terminal simulado
- **Observação:** os 60 registros iniciais (`data/historico_simulado.csv`) são **simulados** e identificados como tal.
