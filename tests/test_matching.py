"""Correction contracts: jev threshold, explicit local fallback, safe defaults and frozen snapshots."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quiz_app.app import create_app
from quiz_app.engine import Engine, grade_answers, new_session
from quiz_app.grading import evaluate_answer, fallback_verdict, jev_scorer, noul_question, offline
from quiz_app.live import live_view
from quiz_app.models import Question
from quiz_app.repository import load_bank, load_session, save_bank
from quiz_app.transport import Simulator


def rule(true="Diomaye Faye", **options):
    return Question(**{
        "id": "fact1_senegal_president", "question": "Qui est le président actuel du Sénégal ?",
        "criteria": {"true": true, "false": "Toute autre réponse"}, **options,
    })


class FakeJev:
    """Deterministic jev stand-in: a probability per normalized answer, None means unavailable."""

    def __init__(self, scores):
        self.scores, self.calls = scores, []

    def __call__(self, question, answers):
        self.calls.append((question.id, dict(answers)))
        return {key: self.scores.get(answer.casefold()) for key, answer in answers.items()}


@pytest.mark.parametrize("score,accepted,sign", [(0.8, True, "≥"), (0.95, True, "≥"), (0.79, False, "<"), (0.0, False, "<")])
def test_jev_threshold_is_inclusive(score, accepted, sign):
    verdict = evaluate_answer(rule(aliases=["Bassirou Diomaye Faye"]), "Diomaye Faye", score, 0.8)
    assert (verdict.accepted, verdict.source, verdict.score, verdict.alias) == (accepted, "jev", score, None)
    assert verdict.reason == f"Score jev {score:.3f} {sign} seuil 0.800."


@pytest.mark.parametrize("answer,accepted,alias", [
    ("  diomaye FAYE ! ", True, "Diomaye Faye"), ("Bassirou Diomaye Faye", True, "Bassirou Diomaye Faye"),
    ("Faye Diomaye", False, None), ("Diomaye", False, None), ("", False, None),
])
def test_fallback_uses_true_criterion_and_aliases_exactly(answer, accepted, alias):
    verdict = evaluate_answer(rule(aliases=["Bassirou Diomaye Faye"]), answer, None, 0.8)
    assert (verdict.accepted, verdict.alias, verdict.source, verdict.score) == (accepted, alias, "fallback", None)
    assert verdict.reason.startswith("Repli local (jev indisponible) : ")


def test_fallback_accents_follow_the_setting():
    question = rule("Été")
    assert fallback_verdict(question, "ete").accepted
    assert not fallback_verdict(question, "ete", False).accepted


def test_jev_never_receives_aliases():
    question = rule(aliases=["Bassirou Diomaye Faye"])
    noul = noul_question(question)
    assert (noul.id, noul.true, noul.false) == ("fact1_senegal_president", "Diomaye Faye", "Toute autre réponse")
    assert noul.instructions.startswith(
        "Question posée à un joueur de quiz : « Qui est le président actuel du Sénégal ? »\n"
        "Bonne réponse attendue : Diomaye Faye.\n")
    assert "autre entité, même étroitement liée" in noul.instructions
    assert noul.instructions.endswith("le titre de l'œuvre au lieu de ce qui est demandé.")
    assert "Bassirou" not in repr(noul)


def test_scorer_factory(monkeypatch):
    assert jev_scorer("", "jev-latest") is offline
    assert offline(rule(), {"a": "x", "b": "y"}) == {"a": None, "b": None}
    seen = []

    class Client:
        def __init__(self, key, model):
            seen.append((key, model))

        def score_many(self, noul, answers):
            seen.append((noul.true, answers))
            return {key: 0.9 for key in answers}

    monkeypatch.setattr("quiz_app.grading.JevClient", Client)
    assert jev_scorer("sk", "jev-1")(rule(), {"a": "Faye"}) == {"a": 0.9}
    assert seen == [("sk", "jev-1"), ("Diomaye Faye", {"a": "Faye"})]


@pytest.mark.parametrize("value", [
    {"criteria": {"true": "Diomaye Faye"}}, {"criteria": {"false": "Autre"}},
    {"criteria": {"true": "  ", "false": "Autre"}}, {"criteria": {"true": "Faye", "false": " "}},
    {"criteria": {"true": ".!?", "false": "Autre"}}, {"criteria": {"true": "Faye", "false": "Autre", "x": 1}},
    {"aliases": ["   "]}, {"aliases": ["!!"]}, {"answer": "Faye"}, {"grading_mode": "exact"},
])
def test_invalid_questions_rejected(value):
    base = {"id": "q", "question": "Qui ?", "criteria": {"true": "Faye", "false": "Autre"}}
    with pytest.raises(ValidationError):
        Question(**{**base, **value})


def test_grading_mixes_jev_and_fallback_and_ranks_in_order(settings):
    scorer = FakeJev({"bassirou": 0.91, "macky sall": 0.02, "diomaye faye": None})
    first = {"A": "Macky Sall", "B": "Bassirou", "C": "Diomaye Faye", "D": "Faye Diomaye"}
    settings.max_players = 5
    results = grade_answers(first, ["A", "B", "C", "D", "E"], rule(), settings, scorer)
    assert scorer.calls == [("fact1_senegal_president", first)]
    assert [(r.player, r.accepted, r.rank, r.points, r.source, r.score) for r in results] == [
        ("A", False, None, 0, "jev", 0.02), ("B", True, 1, 100, "jev", 0.91),
        ("C", True, 2, 80, "fallback", None), ("D", False, None, 0, "fallback", None),
        ("E", False, None, 0, "", None),
    ]
    assert grade_answers({}, ["A"], rule(), settings, scorer)[0].source == "" and len(scorer.calls) == 1


def test_editor_storage_and_jev_tester(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text((Path(__file__).parents[1] / ".env.example").read_text())
    calls = []

    def factory(key, model):
        calls.append((key, model))
        return FakeJev({"bassirou": 0.85})

    monkeypatch.setattr("quiz_app.app.jev_scorer", factory)
    question = rule(aliases=["Bassirou Diomaye Faye"])
    with TestClient(create_app(tmp_path, background=False)) as client:
        assert client.put("/api/questions", json=[question.model_dump()]).status_code == 200
        assert load_bank(tmp_path / "data/questions.json") == [question]
        trial = {"question": question.model_dump(), "answer": "Bassirou"}
        assert client.post("/api/test-answer", json=trial).json() == {
            "accepted": True, "alias": None, "reason": "Score jev 0.850 ≥ seuil 0.800.", "score": 0.85, "source": "jev"}
        strict = client.post("/api/test-answer", json=dict(trial, jev_threshold=0.9, jev_model="jev-2")).json()
        assert strict["accepted"] is False and calls[-1] == ("", "jev-2")
        offline_trial = client.post("/api/test-answer", json=dict(trial, answer="Bassirou Diomaye Faye")).json()
        assert offline_trial["accepted"] and offline_trial["source"] == "fallback"
        for invalid in ({"jev_threshold": 1.5}, {"jev_model": "bad model"}):
            assert client.post("/api/test-answer", json=dict(trial, **invalid)).status_code == 422
        legacy = {"id": "old", "question": "Qui ?", "answer": "Faye"}
        assert client.put("/api/questions", json=[legacy]).status_code == 422
    assert calls[0] == ("", "jev-latest")
    with pytest.raises(Exception, match="BANK_INVALID|criteria"):
        save_bank(tmp_path / "legacy.json", [{"id": "old", "question": "Qui ?", "answer": "Faye"}])


def test_simulation_scores_with_jev_at_stop_and_locally_while_open(tmp_path, settings):
    now = [100.]
    simulator = Simulator()
    scorer = FakeJev({"bassirou": 0.9, "macky": 0.1})
    session = new_session(settings, [rule()], "simulation")
    engine = Engine(session, simulator, tmp_path / "game.json", lambda: now[0], scorer=scorer)
    engine.begin()
    for name in ["Camille", "Robin"]:
        simulator.inject(name, "!join")
    now[0] = session.deadline
    engine.tick()
    for player, answer in zip(session.players, ["Macky", "Bassirou"]):
        simulator.inject(player, f"!r {answer}")
    engine.tick()
    assert [row["points"] for row in live_view(session)["ranking"]] == [0, 0] and scorer.calls == []
    now[0] = session.deadline
    engine.tick()
    assert len(scorer.calls) == 1
    assert [(r.points, r.source) for r in session.rounds[0].results] == [(0, "jev"), (100, "jev")]
    assert "🎯 *Diomaye Faye*" in simulator.messages[-1].body
    assert load_session(engine.path) == session
