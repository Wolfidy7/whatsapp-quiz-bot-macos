import argparse
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from quiz_app.engine import Engine,new_session
from quiz_app.errors import QuizError
from quiz_app.transport import Simulator
from scripts.play_rehearsal import check_enrollment,drive,play,main


@pytest.mark.parametrize("use_overrides",[True,False])
def test_real_rehearsal_command_is_fully_simulated(tmp_path,question,use_overrides):
    (tmp_path/'.env').write_bytes((Path(__file__).parents[1]/'.env.example').read_bytes())
    if not use_overrides:
        env=tmp_path/'.env'
        text=env.read_text().replace('WHATSAPP_GROUP="Test"','WHATSAPP_GROUP="Fictional group"').replace('MAX_PLAYERS=20','MAX_PLAYERS=2').replace('MAX_QUESTIONS=30','MAX_QUESTIONS=3').replace('REGISTRATION_SECONDS=60','REGISTRATION_SECONDS=1').replace('QUESTION_SECONDS=30','QUESTION_SECONDS=1')
        env.write_text(text)
    bank=tmp_path/'custom-questions.json' if use_overrides else tmp_path/'data/questions.json'
    bank.parent.mkdir(parents=True,exist_ok=True)
    bank.write_text(json.dumps([question.model_copy(update={'id':f'q{i}'}).model_dump() for i in range(3)]))
    args=argparse.Namespace(group='Fictional group',players=2,questions=bank,join_seconds=1,seconds=1) if use_overrides else argparse.Namespace(group=None,players=None,questions=None,join_seconds=None,seconds=None)
    clock=[100.];holder=[];sim=Simulator();injected=set()
    def construct(session,transport,path,actual_clock):
        engine=Engine(session,sim,path,lambda:clock[0]);holder.append(engine);return engine
    def advance(seconds):
        engine=holder[-1];key=(engine.session.phase,len(engine.session.rounds))
        if key not in injected:
            if engine.session.phase=='registration':
                for player in ['Camille','Robin']:sim.inject(player,'!join')
            if engine.session.phase=='answering':
                for player in ['Camille','Robin']:sim.inject(player,'!r Paris')
            injected.add(key)
        clock[0]+=seconds
    with patch('scripts.play_rehearsal.AXReader'),patch('scripts.play_rehearsal.AXSender'),patch('scripts.play_rehearsal.DatabaseReader'),patch('scripts.play_rehearsal.Engine',side_effect=construct),patch('scripts.play_rehearsal.time.sleep',side_effect=advance):
        play(args,tmp_path)
    session=holder[0].session
    assert session.phase=='finished' and len(session.rounds)==3
    assert session.settings.whatsapp_group=='Fictional group'
    assert session.settings.max_players==2 and session.settings.registration_seconds==1
    assert session.settings.question_seconds==1
    assert [[r.points for r in q.results] for q in session.rounds]==[[100,20]]*3
    assert not (tmp_path/'data/transport-validation.json').exists()
    args.players=0
    with pytest.raises(QuizError,match='settings'):play(args,tmp_path)


def test_missing_enrollment_pauses_without_questions(tmp_path,settings,question):
    settings.max_players=2;settings.registration_seconds=1
    now=[100.];sim=Simulator();engine=Engine(new_session(settings,[question],'simulation'),sim,tmp_path/'session.json',lambda:now[0])
    engine.session.deadline=101.
    check_enrollment(engine,2)
    with patch('scripts.play_rehearsal.time.sleep',side_effect=lambda seconds:now.__setitem__(0,now[0]+seconds)):
        with pytest.raises(QuizError,match='received 0'):drive(engine)
    assert engine.session.phase=='paused' and engine.session.rounds==[]
    assert len(sim.messages)==1
    with patch('sys.argv',['rehearsal']),patch('scripts.play_rehearsal.play') as run:
        main();assert all(value is None for value in vars(run.call_args.args[0]).values())
        run.side_effect=QuizError('STORAGE_BUSY','Service already active')
        with pytest.raises(SystemExit,match='STORAGE_BUSY'):main()
