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
    settings.max_players=players
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
    assert all('[quiz:' not in message.body for message in simulator.messages if message.outgoing)
    assert all(item.marker not in item.text for item in session.outbox)
    assert session.rounds[0].results[0].points==100
    assert session.rounds[0].results[-1].points==(100 if players==1 else 20)
    assert len(session.rounds)==questions
    assert all(len(round_.observed)==players for round_ in session.rounds)
    assert load_session(tmp_path/'game.json')==session
    assert 'Par question' in report(session,True)
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


@pytest.mark.parametrize('delay',[0,1,7])
def test_next_question_notice_matches_deadline_and_is_absent_after_last_round(tmp_path,settings,question,delay):
    from quiz_app.messages import next_question_delay
    settings.interval_seconds=delay
    now=[100.];sim=Simulator()
    bank=[question,question.model_copy(update={'id':'second'})]
    engine=Engine(new_session(settings,bank,'simulation'),sim,tmp_path/'game.json',lambda:now[0])
    engine.begin();sim.inject('Camille','!join')
    now[0]=engine.session.deadline;engine.tick()
    for index in range(2):
        sim.inject('Camille','!r Paris')
        now[0]=engine.session.deadline;engine.tick()
        text=sim.messages[-1].body
        assert 'LA BONNE RÉPONSE' in text and 'CLASSEMENT PROVISOIRE' in text
        if index==0:
            assert text.endswith(next_question_delay(delay))
            assert text.index('CLASSEMENT PROVISOIRE')<text.index('question')
        else:
            assert 'Prochaine question' not in text and 'prochaine question' not in text
        assert engine.session.deadline==now[0]+delay
        if delay:
            now[0]=engine.session.deadline-.01;engine.tick()
            assert engine.session.phase=='interval'
        now[0]=engine.session.deadline;engine.tick()
    assert engine.session.phase=='finished'

def test_empty_enrollment_cancels(tmp_path,settings,question):
    now=[100.];session=new_session(settings,[question],'simulation')
    engine=Engine(session,Simulator(),tmp_path/'game.json',lambda:now[0]);engine.begin()
    now[0]=session.deadline;engine.tick()
    assert session.phase=='cancelled' and 'ENROLLMENT_INCOMPLETE' in session.error
    assert session.resume_phase==''
    assert session.rounds==[]

def test_deleted_answer_keeps_first_attempt_without_pausing(tmp_path,settings,question):
    now=[100.];sim=Simulator();session=new_session(settings,[question],'simulation')
    engine=Engine(session,sim,tmp_path/'game.json',lambda:now[0]);engine.begin()
    sim.inject('Camille','!join');now[0]=session.deadline;engine.tick()
    sim.inject('Camille','!r Paris');engine.tick()
    sim.messages.pop();engine.tick()
    assert session.phase=='answering' and session.error==''
    sim.inject('Camille','!r London');engine.tick()
    now[0]=session.deadline;engine.tick()
    assert session.phase=='interval' and session.rounds[0].results[0].points==100
    assert session.rounds[0].results[0].answer=='Paris'

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


@pytest.mark.parametrize('enrolled,phase',[(0,'cancelled'),(1,'cancelled'),(2,'answering'),(3,'answering')])
def test_minimum_enrollment_at_deadline(tmp_path,settings,question,enrolled,phase):
    settings.nb_players_expected=2;settings.max_players=5
    now=[100.];sim=Simulator();session=new_session(settings,[question],'simulation')
    engine=Engine(session,sim,tmp_path/'game.json',lambda:now[0]);engine.begin()
    assert 'Minimum : *2 joueurs*' in sim.messages[0].body
    for index in range(enrolled):
        sim.inject(f'P{index}','!join')
        sim.inject(f'P{index}','!JOIN')
    sim.send('!join','bot-registration')
    engine.tick()
    assert session.phase=='registration' and session.rounds==[]
    now[0]=session.deadline;engine.tick()
    assert session.phase==phase and len(session.players)==enrolled
    assert len(session.rounds)==(1 if phase=='answering' else 0)
    assert load_session(engine.path)==session
    if phase=='cancelled':
        assert f'Inscrits : *{enrolled} joueur' in sim.messages[-1].body
        assert all(item.status=='sent' for item in session.outbox)
        count=len(sim.messages);engine.tick();assert len(sim.messages)==count
        with pytest.raises(QuizError,match='Only a paused'):engine.recover()


def test_late_registration_does_not_prevent_cancellation(tmp_path,settings,question):
    settings.nb_players_expected=2
    now=[100.];sim=Simulator();engine=Engine(new_session(settings,[question],'simulation'),sim,tmp_path/'game.json',lambda:now[0])
    engine.begin();sim.inject('Camille','!join')
    send=sim.send
    def late_join(text,label):
        send(text,label)
        if label.endswith('join-stop.0]'):sim.inject('Robin','!join')
    sim.send=late_join
    now[0]=engine.session.deadline;engine.tick()
    assert engine.session.phase=='cancelled' and engine.session.players==['Camille']
    assert engine.session.rounds==[]


def test_uncertain_cancellation_requires_recovery_without_replay(tmp_path,settings,question):
    settings.nb_players_expected=2
    now=[100.];sim=Simulator();engine=Engine(new_session(settings,[question],'simulation'),sim,tmp_path/'game.json',lambda:now[0])
    engine.begin();now[0]=engine.session.deadline
    send=sim.send
    def uncertain(text,label):
        if 'cancel-enrollment' in label:raise QuizError('PUBLICATION_UNCERTAIN','Inspect cancellation')
        send(text,label)
    sim.send=uncertain
    engine.tick()
    assert engine.session.phase=='paused' and engine.session.resume_phase=='registration'
    assert engine.session.rounds==[] and engine.session.outbox[-1].status=='pending'
    with pytest.raises(QuizError):engine.recover()
    pending=engine.session.outbox[-1];send(pending.text,pending.marker)
    engine.recover();engine.tick()
    assert engine.session.phase=='cancelled' and engine.session.rounds==[]
    assert sum('cancel-enrollment' in message.native_id for message in sim.messages)==1


def test_cooperative_stop_is_terminal_and_never_delivers(tmp_path,settings,question):
    from threading import Event
    stop=Event();sim=Simulator();engine=Engine(new_session(settings,[question],'simulation'),sim,tmp_path/'session.json',lambda:100,stop.is_set)
    engine.begin();stop.set();engine.tick()
    assert engine.session.phase=='cancelled' and len(sim.messages)==1
    with pytest.raises(QuizError,match='Arrêt'):engine.deliver('No send','private')
    engine.handle_incident(QuizError('GAME_CANCELLED','Arrêt'))
    assert engine.session.phase=='cancelled'
