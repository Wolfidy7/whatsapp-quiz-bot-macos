from pathlib import Path
from unittest.mock import patch
import pytest
from quiz_app.engine import Engine,new_session,report
from quiz_app.errors import QuizError
from quiz_app.models import Question
from quiz_app.repository import load_session
from quiz_app.transport import Simulator

@pytest.mark.parametrize('players,questions',[(20,30),(50,1),(1,2)])
def test_complete_game(tmp_path,settings,question,players,questions,monkeypatch):
    monkeypatch.setattr("quiz_app.storage.os.fsync",lambda fd:None)
    settings.max_players=players;settings.max_questions=questions
    bank=[question.model_copy(update={'id':f'q{i}'}) for i in range(questions)]
    now=[100.]
    simulator=Simulator();session=new_session(settings,bank,'simulation')
    engine=Engine(session,simulator,tmp_path/'game.json',lambda:now[0]);engine.begin()
    for index in range(players): simulator.inject(f'P{index:02}','!join')
    engine.tick();assert len(session.players)==players
    now[0]=session.deadline;engine.tick();assert session.phase=='answering'
    for index in range(questions):
        for player in session.players: simulator.inject(player,'!r PARIS!')
        engine.tick();now[0]=session.deadline;engine.tick()
        assert session.phase=='interval'
        simulator.inject(session.players[0],'!r Paris') # between rounds excluded
        engine.tick();now[0]=session.deadline;engine.tick()
    assert session.phase=='finished'
    assert session.rounds[0].results[0].points==100
    assert session.rounds[0].results[-1].points==(100 if players==1 else 20)
    assert len(session.rounds)==questions
    assert all(len(round_.observed)==players for round_ in session.rounds)
    assert load_session(tmp_path/'game.json')==session
    assert 'by question' in report(session,True)
    count=len(simulator.messages);engine.tick();assert len(simulator.messages)==count
    engine.cancel();assert session.phase=='cancelled'

def test_uncertain_send_no_replay(tmp_path,settings,question):
    simulator=Simulator();session=new_session(settings,[question],'simulation')
    engine=Engine(session,simulator,tmp_path/'game.json',lambda:100)
    with patch.object(simulator,'send',side_effect=QuizError('PUBLICATION_UNCERTAIN','unknown')):
        with pytest.raises(QuizError): engine.begin()
    assert load_session(engine.path).outbox[0].status=='pending'
    with pytest.raises(QuizError): engine.begin()
    assert len(simulator.messages)==0
    session.outbox[0].status='sent';engine.begin() # explicitly confirmed reservation is not replayed
    assert len(simulator.messages)==0

def test_empty_enrollment_pauses(tmp_path,settings,question):
    now=[100.];session=new_session(settings,[question],'simulation')
    engine=Engine(session,Simulator(),tmp_path/'game.json',lambda:now[0]);engine.begin()
    now[0]=session.deadline;engine.tick()
    assert session.phase=='paused' and 'NO_PLAYERS' in session.error
    assert session.resume_phase=='registration'

def test_changed_answer_pauses(tmp_path,settings,question):
    now=[100.];sim=Simulator();session=new_session(settings,[question],'simulation')
    engine=Engine(session,sim,tmp_path/'game.json',lambda:now[0]);engine.begin()
    sim.inject('Camille','!join');now[0]=session.deadline;engine.tick()
    sim.inject('Camille','!r Paris');engine.tick()
    sim.messages.pop();engine.tick()
    assert session.phase=='paused' and 'HISTORY_CHANGED' in session.error

def test_recovery_pending_and_begin(tmp_path,settings,question):
    sim=Simulator();session=new_session(settings,[question],'simulation')
    engine=Engine(session,sim,tmp_path/'game.json',lambda:100)
    with pytest.raises(QuizError):engine.recover()
    with patch.object(sim,'send',side_effect=QuizError('PUBLICATION_UNCERTAIN','unknown')):
        with pytest.raises(QuizError):engine.begin()
    engine.pause(QuizError('PUBLICATION_UNCERTAIN','unknown'))
    with pytest.raises(QuizError):engine.recover() # marker is absent, never replay
    item=session.outbox[0];sim.send(item.text,item.marker)
    engine.recover()
    assert engine.session.phase=='registration'
    assert engine.session.outbox[0].status=='sent'
    assert len(sim.messages)==1 and engine.session.deadline>100


def test_unclassified_transport_failure(tmp_path,settings,question):
    engine=Engine(new_session(settings,[question],'simulation'),Simulator(),tmp_path/'game.json',lambda:100)
    with patch.object(engine.transport,'send',side_effect=RuntimeError('unknown')):
        with pytest.raises(QuizError,match='Transport failed'):engine.begin()
    assert load_session(engine.path).outbox[0].status=='pending'


def test_preview_gap_preserves_observations(tmp_path,settings,question):
    engine=Engine(new_session(settings,[question],'simulation'),Simulator(),tmp_path/'game.json',lambda:100)
    with patch.object(engine.transport,'preview',return_value=None):
        assert engine.observe('Q',None,[])==[]
