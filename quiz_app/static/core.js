/** Resolve a frozen display label, keeping identical names distinguishable. */
export function label(session, key) {
  const name = session.player_names?.[key] || key;
  const duplicates = Object.values(session.player_names || {}).filter(value => value === name).length;
  return duplicates > 1 ? `${name} (joueur ${Object.keys(session.player_names).indexOf(key) + 1})` : name;
}
/** Format session evidence without exposing untrusted content as HTML. */
export function summary(session) {
  if (!session.id) return 'Aucune partie active.';
  const rows = (session.rounds || []).flatMap((round, index) =>
    (round.results || []).map(result => `${index + 1}. ${label(session, result.player)}: ${result.points} points · ${result.answer || 'sans réponse'}`));
  return [`Session: ${session.id}`, `Joueurs : ${(session.players || []).map(key => label(session, key)).join(', ') || 'en attente'}`,
    session.error || '', ...rows].filter(Boolean).join('\n');
}
/** Report the remaining deadline in seconds, using an injectable clock. */
export function remaining(session, now = Date.now() / 1000) {
  return ['registration', 'answering', 'interval'].includes(session.phase)
    ? `${Math.max(0, Math.ceil(session.deadline - now))}s` : '—';
}
/** Parse an editable JSON bank and reject a non-array document. */
export function parseBank(text) {
  const value = JSON.parse(text);
  if (!Array.isArray(value)) throw new Error('La banque doit être une liste JSON.');
  return value;
}
/** Copy one question with explicit correction options; unit fields only apply to numbers. */
export function withCorrection(question, mode, units, requireUnit) {
  return {...question, grading_mode: mode, units: mode === 'number' ? units.split('\n').map(unit => unit.trim()).filter(Boolean) : [], require_unit: mode === 'number' && requireUnit};
}
