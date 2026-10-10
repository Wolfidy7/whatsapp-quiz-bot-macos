/** Resolve a frozen display label, keeping identical names distinguishable. */
export function label(session, key) {
  const name = session.player_names?.[key] || key;
  const duplicates = Object.values(session.player_names || {}).filter(value => value === name).length;
  return duplicates > 1 ? `${name} (joueur ${Object.keys(session.player_names).indexOf(key) + 1})` : name;
}
/** Phases that keep a game running and its deadline-driven countdown. */
const TIMED = {registration: 'registration_seconds', answering: 'question_seconds', interval: 'interval_seconds'};
/** Tell whether a session snapshot still owns the game. */
export function isActive(session) {
  return Boolean(session.id) && !['finished', 'cancelled'].includes(session.phase);
}
/** Seconds left and the elapsed share of the current timed phase, using an injectable clock. */
export function countdown(session, now = Date.now() / 1000) {
  const key = TIMED[session.phase];
  if (!key) return null;
  const seconds = Math.max(0, Math.ceil(session.deadline - now));
  const total = session.settings?.[key] || seconds || 1;
  return {seconds, ratio: Math.min(1, seconds / total)};
}
/** Label, emoji and color tone of each game phase. */
export function phaseInfo(phase) {
  return ({
    registration: {label: 'Inscriptions', emoji: '📝', tone: 'live', text: 'Les joueurs rejoignent la partie.'},
    answering: {label: 'Question en cours', emoji: '❓', tone: 'live', text: 'Les réponses arrivent.'},
    interval: {label: 'Pause', emoji: '☕', tone: 'live', text: 'Résultats publiés, la suite arrive.'},
    paused: {label: 'En pause', emoji: '⏸️', tone: 'bad', text: 'Une vérification est nécessaire.'},
    finished: {label: 'Terminée', emoji: '🏁', tone: 'good', text: 'Merci à tous les joueurs !'},
    cancelled: {label: 'Arrêtée', emoji: '⛔', tone: 'bad', text: 'La partie a été arrêtée.'},
  })[phase] || {label: 'Prêt', emoji: '🎯', tone: 'idle', text: ''};
}
/** Mode names shown during a game. */
export function modeLabel(session) {
  if (session.mode === 'simulation') return 'Simulation';
  return session.rehearsal ? 'Répétition' : 'Validée';
}
/** Rounds with each player's answer, points and grading source, for the history tab. */
export function historyRows(session) {
  return (session.rounds || []).map((round, index) => ({
    title: `Question ${index + 1} · ${round.question?.question || ''}`,
    answers: (round.results || []).map(result =>
      `${label(session, result.player)} · ${result.answer || 'sans réponse'} · ${result.points} pts${grading(result)}`),
  }));
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
/** Summarize the next game from the settings form, so Start never hides what it will use. */
export function startSummary(count, settings, dirty) {
  const parts = [`${count} question${count > 1 ? 's' : ''}`, `${settings.question_seconds} s par question`,
    `inscriptions ${settings.registration_seconds} s`, `${settings.nb_players_expected} à ${settings.max_players} joueurs`];
  return `${parts.join(' · ')}${dirty ? ' · réglages modifiés, non enregistrés' : ''}`;
}
/** Describe a background question generation for its status line. */
export function generationStatus(state, now = Date.now() / 1000) {
  const seconds = state.started ? Math.max(0, Math.round((state.finished || now) - state.started)) : 0;
  const elapsed = `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
  const cost = typeof state.cost_usd === 'number' ? ` · coût ${state.cost_usd.toFixed(2)} $` : '';
  const done = state.applied ? `🔁 Banque remplacée. Sauvegarde : ${state.applied}.`
    : `🎉 Lot prêt en ${elapsed}${cost}. Vérifiez-le avant de remplacer la banque.`;
  const request = state.request ? ` ${state.request.count} questions (${state.request.themes}, ${state.request.difficulty})` : '';
  return ({idle: '', running: `⏳ Claude prépare${request} depuis ${elapsed}. Vous pouvez fermer la page : la génération continue sur le Mac.`,
    done, failed: `🚨 La génération a échoué : ${state.error}`, cancelled: '⏹️ Génération annulée.'})[state.status] || '';
}
/** French title and next step for every error code the server or browser can report. */
const ERRORS = {
  GAME_ACTIVE: ['Une partie est déjà en cours', 'Arrêtez-la avec le bouton « Arrêter la partie » avant d’en lancer une autre.'],
  TRANSPORT_UNVALIDATED: ['Transport WhatsApp non validé', 'Choisissez « Répétition WhatsApp », ou lancez d’abord le test de transport contrôlé.'],
  BANK_INVALID: ['Questions invalides', 'Vérifiez les questions sélectionnées ou le JSON de la banque.'],
  UI_UNAVAILABLE: ['WhatsApp n’est pas utilisable', 'Sur le Mac : WhatsApp au premier plan, aucune fenêtre de dialogue, session déverrouillée.'],
  WHATSAPP_UNAVAILABLE: ['WhatsApp est introuvable', 'Vérifiez que WhatsApp Desktop est installé et ouvert sur le Mac.'],
  GROUP_AMBIGUOUS: ['Groupe WhatsApp introuvable', 'Le nom du groupe (onglet Réglages) doit correspondre exactement à une seule conversation.'],
  PUBLICATION_UNCERTAIN: ['Envoi incertain', 'Un message n’a peut-être pas été publié. Vérifiez le groupe, puis reprenez la partie.'],
  HISTORY_INCOMPLETE: ['Lecture des messages impossible', 'L’historique WhatsApp n’a pas pu être lu de façon fiable. Réessayez dans un instant.'],
  HISTORY_CHANGED: ['Lecture des messages impossible', 'L’historique WhatsApp a changé pendant la lecture. Réessayez dans un instant.'],
  AUTHOR_AMBIGUOUS: ['Joueur ambigu', 'Deux auteurs ne peuvent pas être distingués dans le groupe.'],
  STORAGE_BUSY: ['Fichiers occupés', 'Un autre serveur du quiz tourne déjà sur ce Mac. Fermez-le, puis réessayez.'],
  STORAGE_UNAVAILABLE: ['Enregistrement impossible', 'Les fichiers du quiz sont inaccessibles. Vérifiez l’espace disque du Mac.'],
  STORAGE_INVALID: ['Fichier du quiz illisible', 'Un fichier de data/ est corrompu. Restaurez une sauvegarde.'],
  CONFIG_INVALID: ['Réglages invalides', 'Corrigez les valeurs dans l’onglet Réglages.'],
  SESSION_INVALID: ['Archive invalide', 'Vérifiez l’identifiant : 32 caractères, chiffres et lettres a à f.'],
  RECOVERY_INVALID: ['Reprise impossible', 'Cette partie ne peut pas être reprise. Arrêtez-la.'],
  SESSION_LOCKED: ['Partie déjà ouverte', 'Elle est utilisée par un autre processus.'],
  RECOVERY_REQUIRED: ['Partie en pause', 'Aucun message n’a été renvoyé. Vérifiez le groupe, puis reprenez ou arrêtez la partie.'],
  NO_GAME: ['Aucune partie chargée', 'Lancez une partie ou rouvrez une archive.'],
  MODE_INVALID: ['Réservé à la simulation', 'Les faux joueurs ne fonctionnent qu’en mode Simulation.'],
  GAME_CANCELLED: ['Partie arrêtée', 'L’arrêt a été demandé pendant le démarrage.'],
  GENERATION_ACTIVE: ['Génération déjà en cours', 'Attendez qu’elle se termine ou annulez-la.'],
  GENERATION_NOT_READY: ['Aucun lot à appliquer', 'Lancez une génération et attendez qu’elle se termine.'],
  GENERATION_FAILED: ['La génération a échoué', 'Vérifiez que Claude Code est installé et connecté sur le Mac, puis relancez.'],
  BATCH_INVALID: ['Le lot contient des erreurs', 'La banque n’a pas été modifiée. Relancez la génération.'],
  HOST_FORBIDDEN: ['Adresse non autorisée', 'Ouvrez le tableau de bord via 127.0.0.1 ou l’adresse Tailscale déclarée dans REMOTE_HOSTS.'],
  ORIGIN_FORBIDDEN: ['Requête refusée', 'Ouvrez le tableau de bord directement depuis son adresse, sans passer par une autre page.'],
  PAYLOAD_TOO_LARGE: ['Fichier trop volumineux', 'La limite est de 1 Mo.'],
  VALIDATION: ['Champs invalides', 'Corrigez les champs indiqués.'],
  NETWORK: ['Serveur injoignable', 'Vérifiez que le serveur tourne sur le Mac et, à distance, que Tailscale est connecté.'],
  INPUT: ['Formulaire incomplet', ''],
};
/** Build an Error carrying the server's code and detail from a failed API response. */
export function apiError(status, body) {
  const value = body && typeof body === 'object' ? body : {};
  const code = status === 422 ? 'VALIDATION' : value.error || 'UNKNOWN';
  const fields = Array.isArray(value.detail) ? value.detail.map(item => (item.loc || []).filter(part => part !== 'body').join(' › ')) : [];
  const message = value.message || (fields.length ? `Champs : ${fields.join(', ')}` : typeof value.detail === 'string' ? value.detail : '');
  return Object.assign(new Error(message || code), {code});
}
/** Turn any error, or a session incident « CODE: detail », into a title, a next step and a raw detail. */
export function explainError(error) {
  const text = typeof error === 'string' ? error : error.message || '';
  const match = typeof error === 'string' ? /^([A-Z_]+): ?(.*)$/s.exec(error) : null;
  const code = match ? match[1] : error.code || (error instanceof TypeError ? 'NETWORK' : 'UNKNOWN');
  const detail = match ? match[2] : text;
  const [title, hint] = ERRORS[code] || ['Erreur inattendue', ''];
  return {title, hint: code === 'INPUT' ? detail : hint, detail: code === 'INPUT' || detail === code ? '' : detail};
}
