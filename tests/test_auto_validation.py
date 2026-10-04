from pathlib import Path
from unittest.mock import MagicMock,patch
import pytest
from quiz_app.models import Message
from quiz_app.errors import QuizError
from quiz_app.storage import read_json
from quiz_app.transport import Simulator
from scripts.validate_auto import first_join,wait_for_join,observe_window,verify_round,validate,main


def native(body,identity='member-one',**kwargs):
    return Message(author='Camille',author_id=identity,body=body,fingerprint=body,**kwargs)


def test_join_and_timeout():
    assert first_join([native('!join',outgoing=True),native('hello')],'!join') is None
    assert first_join([native(' !JOIN ')],'!join').author_id=='member-one'
    with pytest.raises(QuizError,match='identity'):first_join([native('!join',identity='')],'!join')
    transport=MagicMock();transport.preview.return_value=[native('!join')]
    with patch('scripts.validate_auto.time.monotonic',side_effect=[0,0]):
        assert wait_for_join(transport,'join','!join',30).author=='Camille'
    transport.preview.return_value=None
    with patch('scripts.validate_auto.time.monotonic',side_effect=[0,0,31]),patch('scripts.validate_auto.time.sleep'):
        with pytest.raises(QuizError,match='No other account'):wait_for_join(transport,'join','!join',30)
    with patch('scripts.validate_auto.time.monotonic',side_effect=[0,0,31]),patch('scripts.validate_auto.time.sleep'):
        assert observe_window(transport,'question',30)==[]


def test_round_identity_order_and_first_answer(settings):
    replies=[native('!r Paris'),native('!r Londres'),native('!r Paris')]
    assert verify_round(replies,native('!join'),settings)==100
    assert verify_round([replies[0],native(''),*replies[1:]],native('!join'),settings)==100
    with pytest.raises(QuizError,match='order'):verify_round(replies[::-1][:2],native('!join'),settings)
    for change in [{'author_id':'another-member'},{'edited':True}]:
        altered=[replies[0].model_copy(update=change),*replies[1:]]
        with pytest.raises(QuizError,match='authors'):verify_round(altered,native('!join'),settings)
    with patch('scripts.validate_auto.correct_round') as grade:
        grade.return_value=[MagicMock(answer='Londres',points=0)]
        with pytest.raises(QuizError,match='expected score'):verify_round(replies,native('!join'),settings)


def test_automatic_native_validation_mocked(tmp_path,settings):
    (tmp_path/'.env').write_bytes((Path(__file__).parents[1]/'.env.example').read_bytes())
    sim=Simulator();publish=sim.send
    def send(text,marker):
        publish(text,marker)
        bodies=['!join'] if marker.endswith(':join]') else ['!r Paris','!r Londres','!r Paris'] if marker.endswith(':question]') else []
        for body in bodies:
            sim.inject('Camille',body)
            sim.messages[-1]=sim.messages[-1].model_copy(update={'author_id':'member-one'})
    sim.send=send
    with patch('scripts.validate_auto.AXReader'),patch('scripts.validate_auto.AXSender'),patch('scripts.validate_auto.DatabaseReader'),patch('scripts.validate_auto.DatabaseTransport',return_value=sim),patch('scripts.validate_auto.time.sleep'),patch('scripts.validate_auto.time.monotonic',side_effect=[0,0,0,0,61]):
        validate('Fictional group',180,60,tmp_path)
    assert read_json(tmp_path/'data/transport-validation.json')=={'group':'Fictional group','validated':True,'schema':2}
    evidence=list((tmp_path/'data/diagnostics').glob('*-evidence.json'))[0]
    assert read_json(evidence)['points']==100
    assert len(read_json(evidence)['messages'])==3
    for arguments in [('',180,60),('Group',10,60),('Group',180,181)]:
        with pytest.raises(QuizError):validate(*arguments,tmp_path)
    with patch('sys.argv',['auto','--group','Fictional group']),patch('scripts.validate_auto.validate') as run:
        main();assert run.call_args.args[:3]==('Fictional group',180,60)
