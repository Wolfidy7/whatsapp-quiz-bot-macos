import json
from pathlib import Path
from unittest.mock import patch,MagicMock
import pytest
from quiz_app.transport import Simulator
from quiz_app.errors import QuizError
from quiz_app.storage import read_json
from scripts.validate_transport import validate,main
from scripts.probe_whatsapp import main as probe
from scripts.check_coverage import verify


def test_controlled_validation(tmp_path):
    (tmp_path/'.env').write_text((Path(__file__).parents[1]/'.env.example').read_text())
    expected=[{'author':'Camille','body':'!r Paris'},{'author':'Camille','body':'!r London'},{'author':'Robin','body':'!r Paris'}]
    fixture=tmp_path/'expected.json';fixture.write_text(json.dumps(expected))
    simulator=Simulator()
    def replies(seconds):
        for item in expected:simulator.inject(**item)
    with patch('scripts.validate_transport.DatabaseReader'),patch('scripts.validate_transport.AXReader'),patch('scripts.validate_transport.AXSender'),patch('scripts.validate_transport.DatabaseTransport',return_value=simulator),patch('scripts.validate_transport.time.sleep',side_effect=replies):
        validate(fixture,10,tmp_path)
    assert read_json(tmp_path/'data/transport-validation.json')['validated'] is True
    simulator=Simulator()
    with patch('scripts.validate_transport.DatabaseReader'),patch('scripts.validate_transport.AXReader'),patch('scripts.validate_transport.AXSender'),patch('scripts.validate_transport.DatabaseTransport',return_value=simulator),patch('scripts.validate_transport.time.sleep'):
        with pytest.raises(QuizError):validate(fixture,10,tmp_path)
    fixture.write_text('[]')
    with pytest.raises(QuizError):validate(fixture,10,tmp_path)
    with patch('sys.argv',['validate','--expected',str(fixture),'--seconds','10']),patch('scripts.validate_transport.validate') as run:
        main()
        assert run.call_args.args[1]==10


def test_probe_readonly(capsys):
    with patch('sys.argv',['probe','--group','Test']),patch('scripts.probe_whatsapp.AXReader') as Reader:
        reader=Reader.return_value;reader.page.return_value=[];reader.older.return_value=False
        probe()
        assert 'Rows: 0' in capsys.readouterr().out
        assert reader.latest.call_count==2
        reader.older.return_value=True
        with patch('scripts.probe_whatsapp.merge_pages',return_value=[]):probe()


def test_coverage_gate(tmp_path):
    path=tmp_path/'coverage.json'
    report={'totals':{'missing_lines':0,'covered_branches':9,'num_branches':10},'files':{name:{'summary':{'missing_branches':0}} for name in ['quiz_app/grading.py','quiz_app/normalization.py','quiz_app/numeric.py','quiz_app/scoring.py']}}
    path.write_text(json.dumps(report));verify(path)
    for totals in [{'missing_lines':1},{'covered_branches':8}]:
        changed=json.loads(json.dumps(report));changed['totals'].update(totals);path.write_text(json.dumps(changed))
        with pytest.raises(SystemExit):verify(path)
    for name in report['files']:
        changed=json.loads(json.dumps(report));changed['files'][name]['summary']['missing_branches']=1;path.write_text(json.dumps(changed))
        with pytest.raises(SystemExit):verify(path)


def test_direct_read_cli(tmp_path,capsys):
    from scripts.read_messages import main as read_main
    from quiz_app.models import Message
    output=tmp_path/'diagnostic.json'
    with patch('scripts.read_messages.load_settings') as settings,patch('scripts.read_messages.DatabaseReader') as Reader:
        settings.return_value.whatsapp_database='fake.sqlite'
        Reader.return_value.recent.return_value=[Message(author='Camille',body='test',fingerprint='1')]
        with patch('sys.argv',['read','--group','Test','--count','100']):read_main()
        assert 'Recovered 1 native records' in capsys.readouterr().out
        with patch('sys.argv',['read','--group','Test','--output',str(output)]):read_main()
        assert read_json(output)[0]['author']=='Camille'


def test_validation_reservation_and_exclusive_lock(tmp_path):
    from quiz_app.storage import locked
    from scripts.validate_transport import publish_reserved,valid_fixture
    assert not valid_fixture([{'author':'A','body':'ok','extra':True}]*3)
    assert not valid_fixture([{'author':'A','body':' '}]*3)
    path=tmp_path/'reservation.json'
    sender=MagicMock()
    def fail(text,marker):
        assert read_json(path)[0]['status']=='pending'
        raise QuizError('PUBLICATION_UNCERTAIN','verify')
    sender.send.side_effect=fail
    with pytest.raises(QuizError):publish_reserved(sender,'question','marker',path,[])
    assert read_json(path)[0]['status']=='pending'
    with locked(tmp_path/'data/service.lock'):
        with pytest.raises(QuizError,match='Another process'):validate(tmp_path/'unused',30,tmp_path)
