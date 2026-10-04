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
        assert client.post('/api/test-answer',json={'question':bank[0],'answer':'PARIS'}).json()=={'accepted':True,'alias':'Paris'}
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
        assert controller.transport('native','Test',40,'fake.sqlite').sender==__import__('quiz_app.app',fromlist=['AXSender']).AXSender.return_value.send
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
