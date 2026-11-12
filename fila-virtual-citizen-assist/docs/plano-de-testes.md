# Plano de demonstração e testes manuais

Os cenários abaixo reproduzem os quatro casos mínimos do enunciado. A coluna de resultado esperado ajuda a equipe a comparar a execução com o comportamento correto. Preencham a evidência observada (captura de tela ou anotação) durante a gravação/apresentação.

| Cenário | Ação | Resultado esperado | Evidência observada |
| --- | --- | --- | --- |
| Chegadas | Clique em **Registrar chegada** duas vezes. | A fila mostra duas pessoas, na ordem de chegada; cada evento tem horário; os indicadores de espera se atualizam. | Preencher na apresentação. |
| Conclusão | Informe uma duração positiva e clique em **Concluir atendimento**. | A pessoa mais antiga sai da fila, total concluído aumenta em um, duração fica registrada e estimativas se atualizam. | Preencher na apresentação. |
| Fila vazia | Com a fila vazia, tente concluir um atendimento. | A fila continua em zero; aparece a mensagem de fila vazia; nenhum contador muda. | Preencher na apresentação. |
| Estimativa | Com pessoas na fila, compare os dois cartões e conclua atendimentos com durações diferentes. | A estimativa convencional segue quantidade × média; a regressão é exibida e os dados observados passam a compor o treinamento. | Preencher na apresentação. |

## Verificações adicionais

- Tente informar duração vazia, zero ou acima de 240 minutos; a interface deve bloquear a ação ou mostrar validação.
- Atualize a página; a quantidade e os eventos já salvos devem permanecer.
- Abra o painel em outra aba do mesmo computador; os valores devem ser atualizados pela API.

## Registro da execução

- **Data:** preencher
- **Responsável:** preencher
- **Ambiente:** Python 3.10+ e navegador em computador local
- **Resultado geral:** preencher após executar a demonstração
- **Observações:** os dados de partida do arquivo `data/historico_simulado.csv` são sintéticos e devem ser apresentados como simulados.
