const $ = (id) => document.getElementById(id);
const fmt = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' });

function showFeedback(message, isError = false) {
  $('feedback').textContent = message;
  $('feedback').classList.toggle('error', isError);
}

function escapeText(value) {
  const span = document.createElement('span');
  span.textContent = value;
  return span.innerHTML;
}

function render(data) {
  $('queue-count').textContent = data.queue_count;
  $('queue-pill').textContent = data.queue_count;
  $('completed-count').textContent = data.completed_count;
  $('ai-wait').textContent = data.ai_wait_minutes;
  $('conventional-wait').textContent = data.conventional_wait_minutes;
  $('average-service').textContent = data.average_service_minutes;
  $('training-points').textContent = `${data.training_points} registros`;
  $('updated-at').textContent = fmt.format(new Date(data.updated_at));
  $('connection-label').textContent = 'Sistema conectado';
  document.querySelector('.pulse').classList.add('online');

  $('queue-list').innerHTML = data.queue.length
    ? data.queue.map((person, index) => `<div class="queue-row"><div class="queue-person"><span class="person-number">${index + 1}</span><div><strong>Pessoa ${person.id}</strong><small>Chegada às ${fmt.format(new Date(person.arrived_at))}</small></div></div><span class="queue-position">${index === 0 ? 'próxima' : `${index} à frente`}</span></div>`).join('')
    : '<div class="empty-state">A fila está vazia. Registre uma chegada para começar.</div>';

  $('event-list').innerHTML = data.events.length
    ? data.events.map((event) => `<div class="event-row"><span class="event-mark ${event.type === 'conclusao' ? 'conclusao' : ''}"></span><div class="event-copy"><strong>${escapeText(event.description)}</strong><small>${event.type === 'chegada' ? 'Entrada registrada' : 'Atendimento concluído'}</small></div><span class="event-time">${fmt.format(new Date(event.at))}</span></div>`).join('')
    : '<div class="empty-state">Nenhum evento registrado nesta execução.</div>';
}

async function refresh() {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error('Falha ao consultar o servidor.');
    render(await response.json());
  } catch (error) {
    $('connection-label').textContent = 'Sistema desconectado';
    document.querySelector('.pulse').classList.remove('online');
  }
}

async function send(path, body = {}) {
  const buttons = [$('arrive-button'), $('complete-button')];
  buttons.forEach((button) => button.disabled = true);
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Não foi possível atualizar a fila.');
    render(data);
    showFeedback('Registro salvo. Os indicadores foram atualizados.');
  } catch (error) {
    showFeedback(error.message, true);
    await refresh();
  } finally {
    buttons.forEach((button) => button.disabled = false);
  }
}

$('arrive-button').addEventListener('click', () => send('/api/arrivals'));
$('complete-button').addEventListener('click', () => {
  const duration = Number($('duration-input').value);
  if (!Number.isFinite(duration) || duration <= 0 || duration > 240) {
    showFeedback('Informe uma duração entre 0 e 240 minutos.', true);
    return;
  }
  send('/api/completions', { duration_minutes: duration });
});

refresh();
window.setInterval(refresh, 3000);
