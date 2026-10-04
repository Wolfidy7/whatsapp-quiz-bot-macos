/** Resolve a frozen display label, keeping identical names distinguishable. */
export function label(session, key) {
  const name = session.player_names?.[key] || key;
  const duplicates = Object.values(session.player_names || {}).filter(value => value === name).length;
  return duplicates > 1 ? `${name} [${key.slice(-4)}]` : name;
}
/** Format session evidence without exposing untrusted content as HTML. */
export function summary(session) {
  if (!session.id) return 'No active game.';
  const rows = (session.rounds || []).flatMap((round, index) =>
    (round.results || []).map(result => `${index + 1}. ${label(session, result.player)}: ${result.points} points · ${result.answer || 'no answer'}`));
  return [`Session: ${session.id}`, `Players: ${(session.players || []).map(key => label(session, key)).join(', ') || 'waiting'}`,
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
  if (!Array.isArray(value)) throw new Error('The question bank must be an array.');
  return value;
}
