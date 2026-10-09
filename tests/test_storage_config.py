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


@pytest.mark.parametrize('value',['0','-1','21','1.5','not-a-number','1001'])
def test_invalid_minimum_enrollment(tmp_path,value):
    example=(Path(__file__).parents[1]/'.env.example').read_text()
    path=tmp_path/'.env';path.write_text(example.replace('NB_PLAYERS_EXPECTED=1',f'NB_PLAYERS_EXPECTED={value}'))
    with pytest.raises(QuizError) as failure:load_settings(path)
    assert failure.value.code=='CONFIG_INVALID'


def test_minimum_defaults_and_snapshot_compatibility(tmp_path,settings,question):
    from quiz_app.engine import new_session
    example=(Path(__file__).parents[1]/'.env.example').read_text()
    path=tmp_path/'.env';path.write_text(example.replace('NB_PLAYERS_EXPECTED=1\n',''))
    assert load_settings(path).nb_players_expected==1
    session=new_session(settings,[question],'simulation').model_dump(mode='json')
    del session['settings']['nb_players_expected']
    archive=tmp_path/'archive.json';write_json(archive,session)
    assert load_session(archive).settings.nb_players_expected==1
    session['settings']['nb_players_expected']=21
    write_json(archive,session)
    with pytest.raises(QuizError,match='schema'):load_session(archive)


def test_web_settings_atomic_roundtrip_and_failure(tmp_path,settings):
    from quiz_app.config import save_settings
    path=tmp_path/'.env';settings.whatsapp_group='Groupe "fictif"'
    save_settings(path,settings)
    assert load_settings(path)==settings and path.stat().st_mode & 0o777==0o600
    before=path.read_bytes()
    with patch('quiz_app.config.os.replace',side_effect=OSError('disk')):
        with pytest.raises(QuizError,match='enregistrer'):save_settings(path,settings)
    assert path.read_bytes()==before and not list(tmp_path.glob('.settings-*'))


def test_jev_key_stays_outside_settings_and_survives_saves(tmp_path,settings):
    from quiz_app.config import save_settings,load_api_key
    path=tmp_path/'.env'
    assert load_api_key(path)=='' and settings.jev_threshold==0.8 and settings.jev_model=='jev-latest'
    save_settings(path,settings)
    assert load_api_key(path)==''
    path.write_text(path.read_text().replace('JEV_API_KEY=""','JEV_API_KEY="sk-secret"'))
    loaded=load_settings(path)
    assert 'jev_api_key' not in loaded.model_dump() and 'sk-secret' not in loaded.model_dump_json()
    loaded.jev_threshold=0.65
    save_settings(path,loaded)
    assert load_api_key(path)=='sk-secret' and load_settings(path).jev_threshold==0.65


def test_jev_settings_bounds_and_unreadable_key(tmp_path):
    base=Path(__file__).parents[1]/'.env.example'
    for line in ('JEV_THRESHOLD=1.5','JEV_THRESHOLD=-0.1','JEV_MODEL="bad model"'):
        path=tmp_path/'.env';path.write_text('\n'.join(row for row in base.read_text().splitlines() if not row.startswith(line.split('=')[0]+'='))+'\n'+line+'\n')
        with pytest.raises(QuizError):load_settings(path)
    from quiz_app.config import load_api_key
    path=tmp_path/'broken';path.write_text('X')
    with pytest.raises(QuizError):load_api_key(path)
    with pytest.raises(QuizError):load_api_key(tmp_path)
