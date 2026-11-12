// Painel da fila virtual: consulta o servidor por HTTP/JSON e envia as operações.
const $ = (id) => document.getElementById(id);
const fmt = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const POLL_MS = 3000;
const EVENT_LABELS = {
  chegada: 'Entrada registrada',
  conclusao: 'Atendimento concluído',
  rejeitado: 'Operação inválida bloqueada',
  reinicio: 'Demonstração reiniciada',
};

function showFeedback(message, isError = false) {
  $('feedback').textContent = message;
  $('feedback').classList.toggle('error', isError);
}

function escapeText(value) {
  const span = document.createElement('span');
  span.textContent = String(value);
  return span.innerHTML;
}

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function render(data) {
  const model = data.model;
  const evaluation = model.evaluation || {};
  setText('queue-count', data.queue_count);
  setText('queue-pill', data.queue_count);
  setText('completed-count', data.completed_count);
  setText('rejected-count', data.rejected_count);
  setText('ai-wait', data.ai_wait_minutes);
  setText('ai-wait-2', data.ai_wait_minutes);
  setText('conventional-wait', data.conventional_wait_minutes);
  setText('conventional-wait-2', data.conventional_wait_minutes);
  setText('average-service', data.average_service_minutes);
  setText('coef-a', model.intercept.toFixed(2));
  setText('coef-b', model.slope.toFixed(3));
  setText('mae-conv', evaluation.mae_conventional ?? '—');
  setText('mae-ai', evaluation.mae_ai ?? '—');
  setText('training-points', `${model.training_points} registros`);
  setText('training-mix', `${model.simulated_points} simulados + ${model.observed_points} observados`);
  setText('updated-at', fmt.format(new Date(data.updated_at)));
  setText('connection-label', 'Sistema conectado');
  document.querySelector('.pulse').classList.add('online');

  $('queue-list').innerHTML = data.queue.length
    ? data.queue.map((person, index) => `<div class="queue-row"><div class="queue-person"><span class="person-number">${index + 1}</span><div><strong>Pessoa ${escapeText(person.id)}</strong><small>Chegada às ${fmt.format(new Date(person.arrived_at))} · já esperou ${escapeText(person.waited_service_minutes ?? 0)} min</small></div></div><span class="queue-position">${index === 0 ? 'próxima' : `${index} à frente`}</span></div>`).join('')
    : '<div class="empty-state">A fila está vazia. Registre uma chegada para começar.</div>';

  $('event-list').innerHTML = data.events.length
    ? data.events.map((event) => `<div class="event-row"><span class="event-mark ${escapeText(event.type)}"></span><div class="event-copy"><strong>${escapeText(event.description)}</strong><small>${EVENT_LABELS[event.type] || escapeText(event.type)}${event.source ? ` · origem: ${escapeText(event.source)}` : ''}</small></div><span class="event-time">${fmt.format(new Date(event.at))}</span></div>`).join('')
    : '<div class="empty-state">Nenhum evento registrado nesta execução.</div>';
}

async function refresh() {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error('Falha ao consultar o servidor.');
    render(await response.json());
  } catch (error) {
    setText('connection-label', 'Sistema desconectado');
    document.querySelector('.pulse').classList.remove('online');
  }
}

async function send(path, body = {}, successMessage = 'Registro salvo. Os indicadores foram atualizados.') {
  const buttons = [$('arrive-button'), $('complete-button'), $('reset-button')];
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'painel', ...body }),
    });
    const data = await response.json();
    if (data.state) render(data.state);
    if (!response.ok) throw new Error(data.error || 'Não foi possível atualizar a fila.');
    render(data);
    showFeedback(successMessage);
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

$('arrive-button').addEventListener('click', () => send('/api/arrivals'));
$('complete-button').addEventListener('click', () => {
  const duration = Number($('duration-input').value);
  if (!Number.isFinite(duration) || duration <= 0 || duration > 240) {
    showFeedback('Informe uma duração maior que 0 e até 240 minutos.', true);
    return;
  }
  send('/api/completions', { duration_minutes: duration });
});
$('reset-button').addEventListener('click', () => {
  if (window.confirm('Apagar a fila e o registro desta demonstração?')) {
    send('/api/reset', {}, 'Demonstração reiniciada.');
  }
});

refresh();
window.setInterval(refresh, POLL_MS);
