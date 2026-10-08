"""Correction contracts: full names, exact decimals, safe defaults and frozen snapshots."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quiz_app.app import create_app
from quiz_app.engine import Engine, new_session
from quiz_app.grading import evaluate_answer, match_answer
from quiz_app.live import live_view
from quiz_app.models import Question
from quiz_app.repository import load_bank, load_session, save_bank
from quiz_app.transport import Simulator


def rule(answer="Harry Potter", **options):
    return Question(**{"id": "character", "question": "Qui est ce personnage ?", "answer": answer, **options})


@pytest.mark.parametrize("answer,accepted", [
    ("Potter Harry", True), ("  POTTER\nHarry ! ", True), ("Harry Potter", True),
    ("Harry", False), ("Potter", False), ("Harry Poter", False), ("pas Harry Potter", False),
    ("Harry Potter ou Ron Weasley", False), ("Harry Harry Potter", False), ("", False),
])
def test_complete_name_order(answer, accepted):
    question = rule(grading_mode="person_name")
    verdict = evaluate_answer(question, answer)
    assert verdict.accepted is accepted
    assert verdict.alias == ("Harry Potter" if accepted else None)
    assert verdict.reason


def test_names_repeats_punctuation_aliases_and_accents():
    repeated = rule("Tony Tony Chopper", grading_mode="person_name")
    assert match_answer(repeated, "Chopper Tony Tony")[0]
    assert not match_answer(repeated, "Chopper Tony")[0]
    accented = rule("Émile Zola", aliases=["Émile-Édouard Zola"], grading_mode="person_name")
    assert match_answer(accented, "zola emile") == (True, "Émile Zola")
    assert not match_answer(accented, "zola emile", False)[0]
    assert match_answer(accented, "Zola E\u0301mile", False)[0]
    assert match_answer(accented, "Zola Émile-Édouard") == (True, "Émile-Édouard Zola")
    assert not match_answer(accented, "Zola Émile Édouard")[0]
    assert match_answer(rule("Jean d’Arc", grading_mode="person_name"), "d'Arc Jean")[0]
    assert not match_answer(rule("Jean d'Arc", grading_mode="person_name"), "Arc Jean d")[0]
    assert not match_answer(rule(), "Potter Harry")[0]
    assert "ordre des mots" in evaluate_answer(rule(grading_mode="person_name"), "Potter Harry").reason
    assert "exacte" in evaluate_answer(rule(grading_mode="person_name"), "Harry Potter").reason


@pytest.mark.parametrize("answer,accepted", [
    ("12", True), ("12.00", True), ("+012,000!", True), ("12,0 KM", True),
    ("12 kilomètres", True), ("12kilometres", True), ("12.000000000000000001", False),
    ("12 m", False), ("1 2", False), ("douze", False), ("12 ou 13", False),
    ("pas 12", False), ("NaN", False), ("Infinity", False), ("1.2e1", False),
    ("24/2", False), ("12 + 0", False), ("", False), ("1,200", False),
])
def test_exact_numbers_and_optional_units(answer, accepted):
    verdict = evaluate_answer(rule("12", grading_mode="number", units=["km", "kilomètres"]), answer)
    assert verdict.accepted is accepted
    assert verdict.alias == ("12" if accepted else None)
    assert verdict.reason


def test_required_units_negative_zero_and_decimal_precision():
    question = rule("-5 kg", grading_mode="number", units=["kg", "kilogrammes"], require_unit=True)
    assert match_answer(question, "-05,000kilogrammes") == (True, "-5 kg")
    for answer in ["-5", "5 kg", "-5 g", "-5 kg kg"]:
        assert not match_answer(question, answer)[0]
    assert match_answer(rule("0", grading_mode="number"), "-0.00")[0]
    assert match_answer(rule("0.5", grading_mode="number"), ",50")[0]
    assert not match_answer(rule("0.5", grading_mode="number"), "0.50 m")[0]
    alias = rule("12", aliases=["13"], grading_mode="number")
    assert match_answer(alias, "13,00") == (True, "13")
    precise = rule("123456789012345678901234567890.123456789", grading_mode="number")
    assert match_answer(precise, "123456789012345678901234567890,1234567890")[0]
    assert not match_answer(precise, "123456789012345678901234567891.123456789")[0]
    accented = rule("12 mètres", grading_mode="number", units=["mètres"], require_unit=True)
    assert match_answer(accented, "12 metres")[0]
    assert not match_answer(accented, "12 metres", False)[0]


@pytest.mark.parametrize("options", [
    {"grading_mode": "fuzzy"}, {"answer": ".!?"}, {"aliases": ["   "]}, {"aliases": ["!!"]},
    {"units": ["km"]}, {"require_unit": True},
    {"grading_mode": "number", "answer": "douze"},
    {"grading_mode": "number", "answer": "12", "aliases": ["douze"]},
    {"grading_mode": "number", "answer": "12", "units": [""]},
    {"grading_mode": "number", "answer": "12", "units": ["!!"]},
    {"grading_mode": "number", "answer": "12", "units": ["x" * 41]},
    {"grading_mode": "number", "answer": "12", "require_unit": True},
    {"grading_mode": "number", "answer": "12", "units": ["km"], "require_unit": True},
    {"grading_mode": "number", "answer": "12 m", "units": ["km"]},
])
def test_invalid_rules_rejected(options):
    with pytest.raises(ValidationError):
        rule(**options)


def test_editor_storage_and_snapshot(tmp_path, settings):
    from pathlib import Path
    (tmp_path / ".env").write_text((Path(__file__).parents[1] / ".env.example").read_text())
    name = rule(grading_mode="person_name")
    number = rule("12 km", id="distance", grading_mode="number", units=["km"], require_unit=True)
    with TestClient(create_app(tmp_path, background=False)) as client:
        saved = client.put("/api/questions", json=[name.model_dump(), number.model_dump()])
        assert saved.status_code == 200
        assert load_bank(tmp_path / "data/questions.json") == [name, number]
        session = client.post("/api/start", json={"mode": "simulation", "question_ids": [name.id]}).json()
        assert session["questions"][0]["grading_mode"] == "person_name"
        candidate = client.post("/api/test-answer", json={"question": name.model_dump(), "answer": "Potter Harry"}).json()
        assert candidate["accepted"] and candidate["alias"] == "Harry Potter"
        assert "ordre des mots" in candidate["reason"]
        numeric = client.post("/api/test-answer", json={"question": number.model_dump(), "answer": "12,000 km"}).json()
        assert numeric["accepted"] and "numérique" in numeric["reason"]
        assert client.post("/api/test-answer", json={"question": number.model_dump(), "answer": "12"}).json()["accepted"] is False
        invalid = dict(number.model_dump(), answer="douze")
        assert client.put("/api/questions", json=[invalid]).status_code == 422
        assert client.post("/api/test-answer", json={"question": invalid, "answer": "12"}).status_code == 422
        exact = rule()
        assert client.put("/api/questions", json=[exact.model_dump()]).status_code == 200
        assert client.get("/api/session").json()["questions"][0]["grading_mode"] == "person_name"
        assert load_session(tmp_path / "data/sessions" / f"{session['id']}.json").questions == [name]
    # Older banks remain exact without introducing a migration or semantic guess.
    saved = save_bank(tmp_path / "legacy.json", [{"id": "old", "question": "Who?", "answer": "Harry Potter"}])
    assert saved[0].grading_mode == "exact"
    assert not match_answer(saved[0], "Potter Harry")[0]


def test_simulation_scores_inverted_names_and_numeric_values(tmp_path, settings):
    now = [100.]
    simulator = Simulator()
    questions = [rule(grading_mode="person_name"), rule("12", id="number", grading_mode="number")]
    session = new_session(settings, questions, "simulation")
    engine = Engine(session, simulator, tmp_path / "game.json", lambda: now[0])
    engine.begin()
    for name in ["Camille", "Robin"]:
        simulator.inject(name, "!join")
    now[0] = session.deadline
    engine.tick()
    for index, answers in enumerate([("Potter Harry", "Harry Potter"), ("12,00", "12.0")]):
        for player, answer in zip(session.players, answers):
            simulator.inject(player, f"!r {answer}")
        engine.tick()
        preview = live_view(session)["ranking"]
        assert [row["points"] for row in preview] == [100 * (index + 1), 20 * (index + 1)]
        now[0] = session.deadline
        engine.tick()
        assert [result.points for result in session.rounds[index].results] == [100, 20]
        assert all(result.reason for result in session.rounds[index].results)
        now[0] = session.deadline
        engine.tick()
    assert session.phase == "finished"
    assert load_session(engine.path) == session
