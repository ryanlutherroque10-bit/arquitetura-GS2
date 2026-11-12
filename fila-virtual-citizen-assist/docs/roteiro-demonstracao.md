# Roteiro sugerido para o vídeo (até 5 minutos)

### 0:00–0:35 — Apresentação
“Este é o protótipo de fila virtual do Citizen Assist AI. Ele simula os controles de entrada por botões no navegador e mostra como CPU, memória, armazenamento e comunicação trabalham juntos.”

### 0:35–1:15 — Arquitetura
Mostre `arquitetura.md`. Explique que o navegador envia JSON por HTTP ao servidor Python; o servidor processa as regras, usa RAM durante o cálculo e salva estado no arquivo JSON.

### 1:15–2:05 — Registrar chegadas
Clique duas vezes em **Registrar chegada**. Mostre o total, a ordem da fila e os horários registrados.

### 2:05–2:50 — Concluir atendimento
Informe uma duração e conclua o atendimento. Mostre a remoção da pessoa mais antiga, a mudança no total concluído e a atualização das estimativas.

### 2:50–3:20 — Fila vazia
Conclua o atendimento restante; com a fila vazia, tente concluir novamente. Mostre que o sistema impede contagem negativa.

### 3:20–4:10 — Estimativa e IA
Registre novas pessoas. Compare a fórmula convencional com a regressão linear simples. Explique que os registros iniciais são simulados, identificados no CSV, e que conclusões alimentam observações da execução.

### 4:10–4:50 — Limites e encerramento
Mencione que a demonstração roda localmente, que os dados da regressão são didáticos e que um sistema real exigiria validação com dados autorizados, hospedagem segura e controles de acesso.
