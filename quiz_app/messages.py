"""French player-facing copy with native WhatsApp bold and italic formatting."""

from quiz_app.models import Question, Settings

REGISTRATION_CLOSED = "🔒 *INSCRIPTIONS TERMINÉES*\n\n_La liste des joueurs est maintenant figée._"
STOP = "🛑 *STOP — TEMPS ÉCOULÉ !*\n\n_Les réponses sont fermées pour cette question._"


def quantity(count: int, noun: str) -> str:
    """Format a count with a regular French plural; callers supply a singular noun."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def registration(settings: Settings) -> str:
    """Explain enrollment, configured player limits and answer rules before the first question."""
    return (
        "🎮 *LE QUIZ VA COMMENCER !*\n\n"
        f"✍️ Pour participer, envoie *{settings.join_command}*.\n"
        f"⏳ Inscriptions ouvertes pendant *{settings.registration_seconds} s*.\n"
        f"👥 Minimum : *{quantity(settings.nb_players_expected, 'joueur')}* · "
        f"Maximum : *{quantity(settings.max_players, 'joueur')}*.\n\n"
        "_Inscris-toi avant la fermeture pour pouvoir répondre !_\n\n"
        "📝 *COMMENT RÉPONDRE ?*\n\n"
        f"Envoie *{settings.answer_prefix}* suivi d’un espace et de ta réponse.\n"
        f"💬 Exemple : *{settings.answer_prefix} Paris*.\n\n"
        "_Seule ta première réponse envoyée pendant la question, avant STOP, compte._"
    )


def cancellation(count: int, minimum: int) -> str:
    """Explain a cancelled enrollment with actual and required player counts."""
    return (
        "🚫 *PARTIE ANNULÉE*\n\n"
        f"👥 Inscrits : *{quantity(count, 'joueur')}*.\n"
        f"🎯 Minimum requis : *{quantity(minimum, 'joueur')}*.\n\n"
        "_Le nombre minimum n’a pas été atteint avant la fin des inscriptions._"
    )


def question_prompt(question: Question, index: int, total: int, settings: Settings) -> str:
    """Present a question, one-based round number, answer command and response duration."""
    return (
        f"🧠 *QUESTION {index} / {total}*\n\n"
        f"{question.question}\n\n"
        f"⏱️ Tu as *{settings.question_seconds} s* pour répondre.\n"
        f"✍️ Envoie *{settings.answer_prefix} ta réponse*.\n\n"
        "_Seule ta première réponse compte._"
    )


def solution(question: Question) -> str:
    """Reveal the official answer and an optional explanation, preserving their exact content."""
    explanation = f"\n\n💡 _{question.explanation}_" if question.explanation else ""
    return f"✅ *LA BONNE RÉPONSE*\n\n🎯 *{question.answer}*{explanation}"


def next_question_delay(seconds: int) -> str:
    """Announce the configured inter-round wait, using an immediate cue when there is no delay."""
    if seconds == 0:
        return "⚡ *La prochaine question arrive maintenant !*\n\n_Tenez-vous prêts !_"
    return f"⏳ *Prochaine question dans {quantity(seconds, 'seconde')} !*\n\n_Tenez-vous prêts !_"


def score_line(rank: int, name: str, points: int, details: str | None = None) -> str:
    """Format one ranking entry, sharing medals for ties and optionally listing round points."""
    badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "▫️")
    breakdown = f"\n_Par question :_ {details}" if details is not None else ""
    return f"{badge} {rank}. *{name}* — *{quantity(points, 'point')}*{breakdown}"


def scoreboard(entries: list[str], final: bool) -> str:
    """Join ranking entries under a French heading and thank the players after the final round."""
    heading = "🎉 *QUIZ TERMINÉ !*\n\n🏆 *CLASSEMENT FINAL*" if final else "📊 *CLASSEMENT PROVISOIRE*"
    sections = [heading, *entries]
    if final:
        sections.append("👏 _Merci à tous pour votre participation !_")
    return "\n\n".join(sections)
