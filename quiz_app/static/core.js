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
    (round.results || []).map(result => `${index + 1}. ${label(session, result.player)}: ${result.points} points · ${result.answer || 'sans réponse'}${grading(result)}`));
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
/** Copy one question with jev criteria and fallback aliases, dropping retired correction fields. */
export function withCorrection(question, criterionTrue, criterionFalse, aliases) {
  const {answer, grading_mode, units, require_unit, ...rest} = question;
  return {...rest, criteria: {true: criterionTrue.trim(), false: criterionFalse.trim()},
    aliases: aliases.split('\n').map(alias => alias.trim()).filter(Boolean)};
}
/** Describe how one answer was graded: jev score against the threshold, or the local fallback. */
export function grading(result) {
  if (result.source === 'jev') return ` · jev ${result.score.toFixed(2)}`;
  return ({fallback: ' · repli local', local: ' · règle locale'})[result.source] || '';
}
/** Explain a tester verdict with its decision source and, for the fallback, the matching reference. */
export function verdictText(result) {
  const reference = result.alias ? `référence « ${result.alias} » · ` : '';
  return `${result.accepted ? 'Acceptée' : 'Refusée'} · ${reference}${result.reason}`;
}
