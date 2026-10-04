import {summary, remaining, parseBank} from './core.js';
/** Locate a named dashboard element. */
const byId = id => document.getElementById(id);
let bank = [];
/** Execute one same-origin JSON request and propagate classified server errors. */
async function api(path, method = 'GET', body) {
  const response = await fetch(`/api/${path}`, {method, headers: {'Content-Type': 'application/json'},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const value = await response.json();
  if (!response.ok) throw new Error(value.message || JSON.stringify(value.detail || value.error));
  return value;
}
/** Show an action's outcome and keep failures visible for the operator. */
async function action(work) {
  try {byId('notice').textContent = ''; await work();}
  catch (error) {byId('notice').textContent = error.message;}
}
/** Refresh the bank selector using safe text nodes. */
function renderBank(values) {
  bank = values; byId('bank').value = JSON.stringify(values, null, 2);
  byId('question').replaceChildren(...values.map(question => {
    const option = document.createElement('option'); option.value = question.id;
    option.textContent = question.question; return option;
  }));
}
/** Render a fresh game snapshot without replacing editor contents. */
function renderSession(session) {
  byId('phase').textContent = (session.phase || 'ready').toUpperCase();
  byId('players').textContent = session.players?.length ?? '—';
  byId('round').textContent = session.rounds?.length ?? '—';
  byId('remaining').textContent = remaining(session);
  byId('results').textContent = summary(session);
  byId('pending').textContent = (session.outbox || []).filter(item => item.status === 'pending').map(item => item.text).join('\n\n') || 'None.';
  byId('prompt').textContent = session.rounds?.at(-1)?.question.question || 'Registration uses !join.';
  if (session.error) byId('notice').textContent = session.error;
}
/** Bind a button to a guarded asynchronous operation. */
function bind(id, work) {byId(id).addEventListener('click', () => action(work));}
bind('save', async () => renderBank(await api('questions', 'PUT', parseBank(byId('bank').value))));
bind('check', async () => {
  const question = bank.find(item => item.id === byId('question').value);
  const result = await api('test-answer', 'POST', {question, answer: byId('candidate').value});
  byId('verdict').textContent = result.accepted ? `Accepted · matches “${result.alias}”` : 'Rejected · no complete alias match';
});
bind('start', async () => renderSession(await api('start', 'POST', {mode: 'simulation', question_ids: bank.map(item => item.id)})));
bind('native', async () => renderSession(await api('start', 'POST', {mode: 'native', question_ids: bank.map(item => item.id)})));
bind('resume', async () => renderSession(await api('resume', 'POST')));
bind('cancel', async () => renderSession(await api('cancel', 'POST')));
bind('inject', async () => renderSession(await api('inject', 'POST', {author: byId('author').value, body: byId('reply').value})));
bind('recover', async () => renderSession(await api(`recover/${encodeURIComponent(byId('archive').value)}`, 'POST')));
bind('export', async () => {
  const blob = new Blob([JSON.stringify(await api('questions'), null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'questions.json'; anchor.click(); URL.revokeObjectURL(url);
});
byId('import').addEventListener('change', () => action(async () => {
  const file = byId('import').files[0];
  if (file) byId('bank').value = JSON.stringify(parseBank(await file.text()), null, 2);
}));
await action(async () => {renderBank(await api('questions')); byId('settings').textContent = JSON.stringify(await api('settings'), null, 2); byId('native').disabled = !(await api('capabilities')).native_ready;});
setInterval(() => action(async () => renderSession(await api('session'))), 1000);
