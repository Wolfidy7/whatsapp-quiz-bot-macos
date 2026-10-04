from pathlib import Path
from unittest.mock import patch
import os
import pytest
from quiz_app.config import load_settings,parse_env
from quiz_app.storage import locked,write_json,read_json,atomic_write
from quiz_app.repository import validate_questions,save_bank,load_bank,load_session
from quiz_app.errors import QuizError

@pytest.mark.parametrize('text',['X','PORT=1\nPORT=2','PORT="broken','WHATSAPP_GROUP=Test\nUNKNOWN=1'])
def test_invalid_env(tmp_path,text):
    path=tmp_path/'.env';path.write_text(text)
    with pytest.raises(QuizError): load_settings(path)

def test_env(tmp_path):
    assert parse_env('# comment\n\nPORT=8765')['port']=='8765'
    example=Path(__file__).parents[1]/'.env.example'
    for replacement in [('MIN_POINTS=20','MIN_POINTS=200'),('ANSWER_PREFIX="!r"','ANSWER_PREFIX="!join"')]:
        path=tmp_path/'.env';path.write_text(example.read_text().replace(*replacement))
        with pytest.raises(QuizError): load_settings(path)
    with pytest.raises(QuizError): load_settings(tmp_path/'missing')

def test_backup_permissions(tmp_path):
    path=tmp_path/'nested/state.json'
    write_json(path,{'v':1});write_json(path,{'v':2})
    assert read_json(path)=={'v':2}
    assert read_json(path.with_suffix('.backup.json'))=={'v':1}
    assert path.stat().st_mode & 0o777==0o600
    with locked(path.with_suffix('.lock')):
        with pytest.raises(QuizError): write_json(path,{'v':3})
    assert read_json(path)=={'v':2}

def test_corruption_and_interruption(tmp_path):
    path=tmp_path/'state.json';write_json(path,{'v':1})
    with patch('quiz_app.storage.os.replace',side_effect=OSError('disk')):
        with pytest.raises(QuizError): write_json(path,{'v':2})
    assert read_json(path)=={'v':1}
    assert not list(tmp_path.glob('.quiz-*'))
    path.write_text('{broken')
    with pytest.raises(QuizError): read_json(path)
    with pytest.raises(QuizError): write_json(path,{})
    with pytest.raises(QuizError): read_json(tmp_path/'missing')

def test_bank(tmp_path,question):
    path=tmp_path/'bank.json'
    assert save_bank(path,[question.model_dump()])==[question]
    assert load_bank(path)==[question]
    for value in [[],[question.model_dump()]*2,[dict(question.model_dump(),aliases=[' '])],[{'id':'x'}]]:
        with pytest.raises(QuizError): validate_questions(value)
    write_json(path,{'wrong':'schema'})
    with pytest.raises(QuizError): load_session(path)

def test_snapshot_invariants(tmp_path,settings,question):
    from quiz_app.engine import new_session
    from quiz_app.models import Round,Result,Dispatch
    session=new_session(settings,[question],'simulation')
    path=tmp_path/'session.json'
    changes=[
        {'players':['A','A']},
        {'players':[f'P{i}' for i in range(21)]},
        {'questions':[question,question]},
        {'outbox':[Dispatch(marker='m',text='m')]*2},
        {'phase':'answering'},
        {'rounds':[Round(question=question,start_marker='q',stop_marker='s')]*2},
        {'rounds':[Round(question=question.model_copy(update={'id':'other'}),start_marker='q',stop_marker='s')]},
        {'rounds':[Round(question=question,start_marker='q',stop_marker='s',results=[Result(player='A')])]}
    ]
    for change in changes:
        write_json(path,session.model_copy(update=change).model_dump(mode='json'))
        with pytest.raises(QuizError):load_session(path)
