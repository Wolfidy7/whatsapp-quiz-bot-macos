import asyncio
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from quiz_app.app import create_app,Controller,StartRequest,Injection,run_clock
from quiz_app.errors import QuizError
from quiz_app.models import Session
from quiz_app.storage import write_json

@pytest.fixture
def root(tmp_path):
    project=Path(__file__).parents[1]
    (tmp_path/'.env').write_text((project/'.env.example').read_text())
    write_json(tmp_path/'data/questions.json',[{'id':'capital','question':'Capital?','answer':'Paris'}])
    return tmp_path

def test_api(root):
    with TestClient(create_app(root,background=False)) as client:
        assert client.get('/').status_code==200
        assert client.get('/static/core.js').status_code==200
        assert client.get('/api/settings').json()['max_players']==20
        assert client.get('/api/capabilities').json()=={'native_ready':False}
        assert client.get('/api/session').json()=={}
        bank=client.get('/api/questions').json()
        assert client.put('/api/questions',json=bank).status_code==200
        assert client.put('/api/questions',json=[]).status_code==409
        assert client.post('/api/test-answer',json={'question':bank[0],'answer':'PARIS'}).json()=={'accepted':True,'alias':'Paris','reason':'Correspondance exacte après normalisation.'}
        assert client.post('/api/start',json={'mode':'native','question_ids':['capital']}).status_code==409
        assert client.post('/api/start',json={'mode':'simulation','question_ids':['missing']}).status_code==409
        assert client.post('/api/start',json={'mode':'simulation','question_ids':['capital','capital']}).status_code==409
        session=client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).json()
        assert session['phase']=='registration'
        assert client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).status_code==409
        assert client.post('/api/inject',json={'author':'Camille','body':'!join'}).json()['players']==['Camille']
        assert client.post('/api/recover/'+session['id']).status_code==409
        assert client.post('/api/cancel').json()['phase']=='cancelled'
        assert client.post('/api/recover/bad').status_code==409
        recovered=client.post('/api/recover/'+session['id']).json()
        assert recovered['phase']=='paused'
        assert client.post('/api/resume').status_code==409 # cancelled game cannot resume
        assert client.post('/api/cancel').status_code==200
        assert client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).status_code==200
        assert client.post('/api/start',json={'mode':'simulation','question_ids':[]}).status_code==422
        assert client.get('/api/session',headers={'host':'attacker.test'}).status_code==403
        assert client.post('/api/cancel',headers={'origin':'https://attacker.test'}).status_code==403
        assert client.get('/api/session',headers={'origin':'http://testserver'}).status_code==200

def test_controller_errors(root):
    controller=Controller(root);controller.tick()
    with pytest.raises(QuizError):controller.cancel()
    request=StartRequest(mode='simulation',question_ids=['capital'])
    with patch('quiz_app.engine.Engine.begin',side_effect=QuizError('PUBLICATION_UNCERTAIN','unknown')):
        assert controller.start(request)['phase']=='paused'
    controller.tick()
    controller.engine.transport=object()
    with pytest.raises(QuizError):controller.inject(Injection(author='A',body='!join'))
    controller.cancel()
    with patch('quiz_app.app.AXReader') as reader,patch('quiz_app.app.AXSender'),patch('quiz_app.app.DatabaseReader'):
        write_json(root/'data/transport-validation.json',{'group':'Test','validated':True,'schema':2})
        assert controller.transport('native','Test',40,'fake.sqlite').sender==__import__('quiz_app.app',fromlist=['AXSender']).AXSender.return_value.publish
        with pytest.raises(QuizError):controller.transport('native','Other',40,'fake.sqlite')

def test_recovery_and_background(root):
    with TestClient(create_app(root,background=True)) as client:
        session=client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).json()
    # A restart does not load or replay the archive automatically.
    controller=Controller(root)
    assert controller.state()=={}
    assert controller.recover(session['id'])['phase']=='paused'
    saved_phase=controller.engine.session.resume_phase
    controller.engine.save()
    controller.engine=None
    assert controller.recover(session['id'])['resume_phase']==saved_phase
    assert controller.resume()['phase']=='registration'

def test_timer(root):
    controller=Controller(root)
    async def scenario():
        task=asyncio.create_task(run_clock(controller))
        await asyncio.sleep(.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(scenario())

def test_entrypoint():
    import runpy
    with patch('uvicorn.run') as run:
        runpy.run_module('quiz_app.__main__',run_name='__main__')
        assert run.call_args.kwargs['host']=='127.0.0.1'


def test_payload_lock_and_storage_failure(root):
    from quiz_app.storage import locked
    with TestClient(create_app(root,background=False)) as client:
        assert client.post('/api/start',content='x'*1_000_001).status_code==413
        write_json(root/'data/transport-validation.json',{'group':'Test','validated':True,'schema':2})
        assert client.get('/api/capabilities').json()['native_ready'] is True
    with locked(root/'data/service.lock'):
        with pytest.raises(QuizError):
            with TestClient(create_app(root,background=False)):pass
    controller=Controller(root)
    controller.start(StartRequest(mode='simulation',question_ids=['capital']))
    with patch.object(controller.engine,'tick',side_effect=QuizError('STORAGE_UNAVAILABLE','disk')):
        controller.tick()
    assert controller.state()['phase']=='paused'
    assert 'STORAGE_UNAVAILABLE' in controller.state()['error']


def test_dashboard_automatic_cancellation_and_new_game(root):
    env=root/'.env';env.write_text(env.read_text().replace('NB_PLAYERS_EXPECTED=1','NB_PLAYERS_EXPECTED=2'))
    app=create_app(root,background=False)
    with TestClient(app) as client:
        assert client.get('/api/settings').json()['nb_players_expected']==2
        session=client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).json()
        assert session['settings']['nb_players_expected']==2
        client.post('/api/inject',json={'author':'Camille','body':'!join'})
        controller=app.state.controller
        controller.engine.clock=lambda:session['deadline']
        controller.tick()
        state=client.get('/api/session').json()
        assert state['phase']=='cancelled' and state['rounds']==[]
        assert 'ENROLLMENT_INCOMPLETE' in state['error']
        assert client.post('/api/start',json={'mode':'simulation','question_ids':['capital']}).status_code==200


def test_web_settings_snapshot_and_live_scores(root):
    from quiz_app.config import load_settings
    app=create_app(root,background=False)
    with TestClient(app) as client:
        defaults=client.get('/api/settings').json();defaults.update(nb_players_expected=2,max_players=5,question_seconds=10)
        assert client.put('/api/settings',json=defaults).status_code==200
        assert load_settings(root/'.env').nb_players_expected==2
        bad=dict(defaults,nb_players_expected=6)
        assert client.put('/api/settings',json=bad).status_code==422
        assert client.put('/api/settings',json=dict(defaults,unexpected='bad')).status_code==422
        accented={'id':'accent','question':'Un mot ?','answer':'Été'}
        trial={'question':accented,'answer':'ete','ignore_accents':False}
        assert client.post('/api/test-answer',json=trial).json()['accepted'] is False
        trial['ignore_accents']=True
        assert client.post('/api/test-answer',json=trial).json()['accepted'] is True
        session=client.post('/api/start',json={'mode':'simulation','question_ids':['capital'],'settings':defaults}).json()
        controller=app.state.controller
        client.post('/api/inject',json={'author':'Camille','body':'!join'})
        client.post('/api/inject',json={'author':'Robin','body':'!join'})
        controller.engine.clock=lambda:controller.engine.session.deadline
        controller.tick()
        controller.engine.clock=lambda:controller.engine.session.deadline-1
        state=client.post('/api/inject',json={'author':'Camille','body':'!r Paris'}).json()
        assert state['live']['provisional'] is True
        assert state['live']['ranking'][0]['points']==100
        assert state['live']['ranking'][0]['confirmed_points']==0
        assert controller.engine.session.rounds[-1].results==[]
        state=client.post('/api/inject',json={'author':'Robin','body':'!r Paris'}).json()
        assert [r['points'] for r in state['live']['ranking']]==[100,20]
        client.put('/api/settings',json=dict(defaults,question_seconds=99))
        assert client.get('/api/session').json()['settings']['question_seconds']==10
        controller.engine.clock=lambda:controller.engine.session.deadline
        controller.tick()
        state=client.get('/api/session').json()
        assert state['live']['provisional'] is False
        assert [r['confirmed_points'] for r in state['live']['ranking']]==[100,20]
        assert client.post('/api/cancel').json()['phase']=='cancelled'


def test_stop_signals_while_whatsapp_work_owns_lock(root):
    from threading import Thread,Event
    controller=Controller(root)
    controller.start(StartRequest(mode='simulation',question_ids=['capital']))
    entered=Event();released=Event()
    def work():
        with controller.lock:
            entered.set();released.wait(3)
    worker=Thread(target=work);worker.start();assert entered.wait(1)
    try:
        assert controller.cancel()=={'stop_requested':True}
        assert controller.stop_requested.is_set()
    finally:released.set();worker.join(3)
    controller.tick();assert controller.state()['phase']=='cancelled'
    with patch.object(controller.engine,'save') as save:
        controller.tick();controller.tick()
        save.assert_not_called()


def test_real_rehearsal_is_explicit_and_recovery_keeps_mode(root):
    from quiz_app.transport import Simulator
    controller=Controller(root)
    with patch('quiz_app.app.AXReader'),patch('quiz_app.app.AXSender'),patch('quiz_app.app.DatabaseReader'),patch('quiz_app.app.DatabaseTransport',return_value=Simulator()):
        state=controller.start(StartRequest(mode='native',question_ids=['capital'],rehearsal=True))
        assert state['rehearsal'] is True
        controller.cancel();controller.engine=None
        assert controller.recover(state['id'])['phase']=='paused'
        assert not (root/'data/transport-validation.json').exists()
    with patch.object(controller,'initialize',side_effect=QuizError('GAME_CANCELLED','Arrêt')):
        controller.engine=None
        assert controller.start(StartRequest(mode='simulation',question_ids=['capital']))['phase']=='cancelled'


def test_simulation_recovery_keeps_deleted_first_reply_and_sequence(root):
    controller=Controller(root)
    controller.start(StartRequest(mode='simulation',question_ids=['capital']))
    controller.inject(Injection(author='Camille',body='!join'))
    controller.engine.clock=lambda:controller.engine.session.deadline
    controller.tick()
    controller.engine.clock=lambda:controller.engine.session.deadline-1
    controller.inject(Injection(author='Camille',body='!r Paris'))
    deleted=controller.engine.transport.messages.pop()
    controller.engine.save()
    session_id=controller.engine.session.id
    controller.engine=None
    controller.recover(session_id)
    assert controller.engine.transport.sequence>=deleted.sequence
    controller.engine.clock=lambda:controller.engine.session.deadline-1
    controller.resume()
    controller.inject(Injection(author='Camille',body='!r London'))
    assert controller.engine.session.phase=='answering'
    assert controller.engine.transport.messages[-1].sequence>deleted.sequence
    controller.engine.clock=lambda:controller.engine.session.deadline
    controller.tick()
    assert controller.engine.session.rounds[0].results[0].answer=='Paris'
    assert controller.engine.session.rounds[0].results[0].points==100
