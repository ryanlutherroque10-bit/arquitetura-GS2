# Relatório técnico — Sistema inteligente de gerenciamento de filas virtuais

| Campo | Informação |
| --- | --- |
| Disciplina | Arquitetura e Organização de Computadores |
| Projeto integrador | Citizen Assist AI |
| Turma | 1CC-FEV |
| Integrantes | Preencher nomes completos e RMs antes da entrega |
| Protótipo | Aplicação web local em Python |

## 1. Problema e objetivo

Em serviços comunitários, a falta de informação sobre o tamanho da fila e a espera pode dificultar a organização do atendimento. Este protótipo registra entradas e conclusões, mostra o estado da fila em um navegador e compara uma estimativa de espera convencional com uma regressão linear simples.

## 2. Arquitetura e componentes

O computador que executa o protótipo contém CPU, RAM e armazenamento. O servidor Python recebe as operações HTTP do navegador, aplica as regras e calcula indicadores. Os dados operacionais ficam em JSON no armazenamento; o histórico sintético fica em CSV. A página HTML/CSS/JavaScript apresenta as informações e oferece controles que simulam botões de entrada.

O fluxo completo está detalhado em [arquitetura.md](arquitetura.md). A requisição de chegada é processada como entrada, alterando uma lista em memória; o resultado é salvo no arquivo JSON e enviado ao navegador como saída. Cada atendimento concluído remove a pessoa mais antiga da fila e registra o horário e a duração informada.

## 3. Organização e estimativa de memória

O servidor mantém estruturas simples em RAM: lista de pessoas aguardando, eventos recentes, durações dos atendimentos e observações usadas no modelo. O histórico sintético contém 12 linhas. O código limita a lista operacional a 250 eventos e a 500 durações reais observadas para manter crescimento previsível. A ocupação exata depende do interpretador e do navegador; para esta escala, espera-se consumo de poucos megabytes para o processo Python, além do consumo próprio do navegador. O estado persistente ocupa poucos quilobytes enquanto a fila e o histórico forem pequenos.

Em um ESP32, esse desenho precisaria de uma estrutura mais compacta e limites rígidos de fila e registros; também seria necessário escolher um formato de armazenamento compatível com flash e considerar desgaste de escrita.

## 4. Entrada, processamento e saída

- **Entrada:** botões virtuais de chegada e conclusão; duração numérica do atendimento.
- **Processamento:** criação de identificador, validação, inclusão/remoção FIFO, atualização de totais, média e regressão linear.
- **Saída:** número aguardando, número concluído, estimativas, lista de pessoas e eventos com horários.

Uma conclusão com fila vazia retorna erro HTTP `409` e não altera os dados. Duração inválida retorna `400`.

## 5. Comunicação

O navegador e o servidor trocam mensagens por HTTP e JSON no endereço local `127.0.0.1:8000`. A página consulta o estado a cada três segundos e atualiza seus indicadores. Essa configuração demonstra comunicação em rede entre processos no mesmo computador. Para demonstrar em outros computadores, o servidor pode ser configurado para escutar na rede local e o firewall deve permitir a porta; para acesso público pela internet, são necessários hospedagem, HTTPS e controles de acesso.

## 6. Estimativa convencional e modelo

A linha de base convencional calcula `pessoas aguardando × duração média`. O modelo linear usa o histórico de `pessoas à frente × duração média` como variável de entrada e o tempo observado como alvo. A amostra fornecida é simulada para que seja possível demonstrar o cálculo antes de haver observações próprias. Quando um atendimento é concluído, o sistema acrescenta uma observação de execução; como a duração e o tempo de espera são aproximados, a previsão é didática. O dashboard apresenta as duas estimativas para comparação.

## 7. Limitações e melhorias

- A amostra inicial é pequena, sintética e não representa uma unidade de atendimento real.
- A duração de um atendimento é informada pelo operador; não existe sensor ou relógio de início/fim automatizado.
- A fila e o servidor estão no mesmo computador por padrão; não há contas de usuário, HTTPS, redundância ou banco de dados transacional.
- A atualização periódica usa consultas HTTP em intervalo fixo; em grande escala seria melhor usar mecanismo de atualização em tempo real e serviço persistente.
- Um próximo passo seria validar o modelo com dados reais autorizados e anonimizados, medir erro de previsão, acrescentar controle de acesso e testar em uma placa ou implantação de rede.

## 8. Conclusão

O protótipo demonstra como entradas, processamento, memória, armazenamento, comunicação e interface de saída trabalham juntos em um sistema computacional. Os quatro cenários mínimos podem ser apresentados no vídeo seguindo [roteiro-demonstracao.md](roteiro-demonstracao.md); o checklist e as evidências de execução devem ser registrados em [plano-de-testes.md](plano-de-testes.md).
