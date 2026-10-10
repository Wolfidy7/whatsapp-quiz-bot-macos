from pathlib import Path
import sqlite3
from unittest.mock import patch,MagicMock
import pytest
from quiz_app.database_reader import readonly,DatabaseReader,DatabaseTransport,parse_row,timestamp,ordered_rows,boundary,resolve_group
from quiz_app.errors import QuizError

@pytest.fixture
def source(tmp_path):
    path=tmp_path/'ChatStorage.sqlite'
    db=sqlite3.connect(path)
    db.executescript('''
    CREATE TABLE ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY,ZPARTNERNAME TEXT,ZSESSIONTYPE INTEGER,ZREMOVED INTEGER);
    CREATE TABLE ZWAGROUPMEMBER (Z_PK INTEGER PRIMARY KEY,ZCONTACTNAME TEXT,ZFIRSTNAME TEXT,ZMEMBERJID TEXT);
    CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY,ZSORT INTEGER,ZSTANZAID TEXT,ZTEXT TEXT,ZISFROMME INTEGER,ZMESSAGEDATE REAL,ZPUSHNAME TEXT,ZFROMJID TEXT,ZGROUPMEMBER INTEGER,ZCHATSESSION INTEGER,ZMESSAGETYPE INTEGER DEFAULT 0);
    INSERT INTO ZWACHATSESSION VALUES (1,'Test',1,0),(2,'Other',1,0);
    INSERT INTO ZWAGROUPMEMBER VALUES (1,'Camille',NULL,'member-a');
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (1,1,'q','Q',1,812592001,NULL,'self',NULL,1);
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (2,2,'a','!r Paris',0,812592002,NULL,'member-a',1,1);
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (3,3,'b','!r Paris',0,812592003,NULL,'member-a',1,1);
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (4,4,'s','STOP',1,812592004,NULL,'self',NULL,1);
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (5,5,'late','!r London',0,812592005,'Robin','member-b',NULL,1);
    INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (6,1,'private','OTHER GROUP',0,812592005,'Private','private',NULL,2);
    ''');db.commit();db.close()
    return path

def test_readonly_complete_window(source):
    reader=DatabaseReader(source,'Test')
    rows=reader.segment('Q','STOP')
    assert len(rows)==2 and rows[0].body==rows[1].body
    assert rows[0].fingerprint!=rows[1].fingerprint
    assert rows[0].author_id==rows[1].author_id
    assert rows[0].author=='Camille' and rows[0].timestamp.endswith('+00:00')
    assert len(reader.segment('Q'))==4
    assert len(reader.recent(100))==5
    assert [row.body for row in reader.recent(2)]==['STOP','!r London']
    with readonly(source) as db:
        with pytest.raises(sqlite3.OperationalError):db.execute('DELETE FROM ZWAMESSAGE')
    assert len(reader.recent(100))==5

def test_group_and_boundary_errors(source):
    with readonly(source) as db:
        with pytest.raises(QuizError):resolve_group(db,'Missing')
        with pytest.raises(QuizError):boundary(db,1,'missing')
    reader=DatabaseReader(source,'Test')
    with pytest.raises(QuizError):reader.segment('STOP','Q')
    for count in [0,10001]:
        with pytest.raises(ValueError):reader.recent(count)
    db=sqlite3.connect(source)
    db.execute("INSERT INTO ZWACHATSESSION VALUES (3,'Test',1,0)");db.commit();db.close()
    with pytest.raises(QuizError):reader.recent(1)

def test_source_unavailable(tmp_path):
    with pytest.raises(QuizError):DatabaseReader(tmp_path/'missing','Test').recent(1)
    path=tmp_path/'bad';path.write_text('not a database')
    with pytest.raises(QuizError):DatabaseReader(path,'Test').recent(1)

def test_rows_timestamp_and_aliases():
    row=(1,1,None,None,False,None,None,None)
    result=parse_row(row,3)
    assert result.body=='' and result.author=='' and result.timestamp==''
    assert result.fingerprint=='db:3:1'
    assert parse_row((1,1,'id','hello',False,0,None,'unknown'),3).author.startswith('Participant ')
    assert timestamp(0)=='2001-01-01T00:00:00+00:00'
    for date in [float('nan'),float('inf'),'wrong']:
        with pytest.raises(QuizError):timestamp(date)
    for rows in [[row,row],[tuple([1,None,*row[2:]])],[(1,1,'same','a',False,0,'A','id'),(2,2,'same','b',False,0,'A','id')]]:
        with pytest.raises(QuizError):ordered_rows(rows,1)

def test_transport_confirmation(source):
    reader=DatabaseReader(source,'Test');sender=MagicMock()
    transport=DatabaseTransport(reader,sender)
    assert len(transport.preview('Q'))==4
    assert len(transport.segment('Q','STOP'))==2
    transport.send('hello','Q');sender.assert_called_once_with('hello','Q')
    with patch('quiz_app.database_reader.time.sleep'):
        with pytest.raises(QuizError,match='Outgoing marker'):transport.send('unknown','missing')
    with patch.object(reader,'segment',side_effect=QuizError('SOURCE_UNAVAILABLE','source')):
        with pytest.raises(QuizError,match='source'):transport.send('hello','Q')

def test_one_hundred_in_single_read(source):
    db=sqlite3.connect(source)
    db.executemany('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (?,?,?, ?,0,812592005,?,?,NULL,1)',[(i,i,f'id-{i}',f'!r reply {i}','Camille','member-a') for i in range(100,200)])
    db.commit();db.close()
    rows=DatabaseReader(source,'Test').recent(100)
    assert len(rows)==100 and rows[0].body=='!r reply 100' and rows[-1].body=='!r reply 199'


def test_group_address_is_not_a_player():
    message=parse_row((1,1,'id','!join',False,0,'Group','group@g.us'),1)
    assert message.author_id=='' and message.author==''


@pytest.mark.parametrize('kind',[1,2,3,6,7,10,11,12,14,15,46,63,66,999])
def test_nontext_records_are_ignored_before_metadata_validation(source,kind):
    db=sqlite3.connect(source)
    db.execute('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZCHATSESSION,ZMESSAGETYPE) VALUES (99,NULL,?, ?,0,?,1,?)',('ignored','!r Paris','invalid timestamp',kind))
    db.execute('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZCHATSESSION,ZMESSAGETYPE) VALUES (100,NULL,?,NULL,0,?,1,0)',('empty','invalid timestamp'))
    db.commit();db.close()
    reader=DatabaseReader(source,'Test')
    assert len(reader.recent(100))==5
    assert [m.fingerprint for m in reader.segment('Q','STOP')]==['db:1:a','db:1:b']


def test_unreadable_blob_and_media_caption_cannot_confirm_publication(source):
    from quiz_app.models import NativeDelivery
    db=sqlite3.connect(source)
    db.execute('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZCHATSESSION,ZMESSAGETYPE) VALUES (99,NULL,?, ?,0,?,1,0)',('blob',sqlite3.Binary(b'\xff'),'bad date'))
    db.execute('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZCHATSESSION,ZMESSAGETYPE) VALUES (100,100,?, ?,1,?,1,1)',('caption','Caption','bad date'))
    db.commit();db.close()
    reader=DatabaseReader(source,'Test')
    assert len(reader.recent(100))==5
    assert reader.sent_identity(NativeDelivery(text='Caption',group_id=1,after=5)) is None


def test_native_game_continues_after_deleted_registration_answer_and_media(source,tmp_path,settings,question):
    from quiz_app.engine import Engine,new_session
    now=[100.]
    reader=DatabaseReader(source,'Test')
    transport=DatabaseTransport(reader,lambda text,key:append_native(source,text),tmp_path/'receipts.json')
    engine=Engine(new_session(settings,[question],'native'),transport,tmp_path/'session.json',lambda:now[0])
    engine.begin()
    join=append_native(source,'!join',outgoing=0)
    engine.tick();assert len(engine.session.players)==1
    db=sqlite3.connect(source);db.execute('DELETE FROM ZWAMESSAGE WHERE ZSTANZAID=?',(join.split(':',2)[2],));db.commit();db.close()
    now[0]=engine.session.deadline;engine.tick();assert engine.session.phase=='answering'
    answer=append_native(source,'!r Paris',outgoing=0)
    engine.tick()
    db=sqlite3.connect(source)
    db.execute('UPDATE ZWAMESSAGE SET ZTEXT=NULL,ZMESSAGETYPE=15 WHERE ZSTANZAID=?',(answer.split(':',2)[2],))
    db.execute("INSERT INTO ZWAMESSAGE (ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZCHATSESSION,ZMESSAGETYPE) VALUES (NULL,'sticker','!r Rome',0,'invalid',1,11)")
    db.commit();db.close()
    append_native(source,'!r London',outgoing=0)
    engine.tick();assert engine.session.phase=='answering' and engine.session.error==''
    now[0]=engine.session.deadline;engine.tick()
    assert engine.session.phase=='interval'
    assert engine.session.rounds[0].results[0].answer=='Paris'
    assert engine.session.rounds[0].results[0].points==100
    now[0]=engine.session.deadline;engine.tick()
    assert engine.session.phase=='finished' and engine.session.error==''


def test_native_contact_names_and_encoded_push(source):
    from quiz_app.database_reader import contact_names,named_rows
    contacts=source.with_name('ContactsV2.sqlite')
    db=sqlite3.connect(contacts)
    db.executescript('''CREATE TABLE ZWAADDRESSBOOKCONTACT (ZWHATSAPPID TEXT,ZLID TEXT,ZFULLNAME TEXT,ZGIVENNAME TEXT,ZBUSINESSNAME TEXT);
    INSERT INTO ZWAADDRESSBOOKCONTACT VALUES ('member-a','lid-a','Camille',NULL,NULL),('member-b',NULL,NULL,'Robin',NULL),(NULL,'blank',NULL,NULL,NULL),(NULL,'business',NULL,NULL,'Fictional business');''')
    db.commit();db.close()
    assert contact_names(source,set())=={}
    assert contact_names(source,{'business'})['business']=={'Fictional business'}
    assert contact_names(source,{'blank'})=={}
    assert DatabaseReader(source,'Test').recent(1)[0].author=='Robin'
    row=(1,1,'m','!join',False,0,None,'lid-a@lid')
    assert named_rows([row],source)[0][6]=='Camille'
    db=sqlite3.connect(contacts);db.execute("INSERT INTO ZWAADDRESSBOOKCONTACT VALUES ('member-a',NULL,'Conflicting label',NULL,NULL)");db.commit();db.close()
    with pytest.raises(QuizError,match='disagree'):DatabaseReader(source,'Test').recent(100)


def append_native(path,text,*,outgoing=1,group=1,stanza=None,sort=None):
    db=sqlite3.connect(path)
    key=db.execute('SELECT MAX(Z_PK)+1 FROM ZWAMESSAGE').fetchone()[0]
    sequence=sort if sort is not None else db.execute('SELECT MAX(ZSORT)+1 FROM ZWAMESSAGE WHERE ZCHATSESSION=?',(group,)).fetchone()[0]
    db.execute('INSERT INTO ZWAMESSAGE (Z_PK,ZSORT,ZSTANZAID,ZTEXT,ZISFROMME,ZMESSAGEDATE,ZPUSHNAME,ZFROMJID,ZGROUPMEMBER,ZCHATSESSION) VALUES (?,?,?,?,?,812592006,NULL,?,NULL,?)',(key,sequence,stanza or f'native-{key}',text,outgoing,'self' if outgoing else 'member-a',group))
    db.commit();db.close()
    return f'db:{group}:{stanza or f"native-{key}"}'


def test_clean_delivery_identity_boundaries_and_repeated_text(source,tmp_path):
    from quiz_app.storage import read_json
    receipt=tmp_path/'private/deliveries.json'
    calls=[]
    def send(text,key):
        fence=read_json(receipt)[key]
        assert fence['native_id']=='' and fence['text']==text
        assert fence['after']>=5
        calls.append((text,key));append_native(source,text)
    reader=DatabaseReader(source,'Test');transport=DatabaseTransport(reader,send,receipt)
    transport.send('Question 1','private-q1')
    first=transport.deliveries['private-q1'].native_id
    append_native(source,'!r Paris',outgoing=0)
    transport.send('STOP','private-stop1')
    append_native(source,'!r late',outgoing=0)
    transport.send('Question 2','private-q2')
    append_native(source,'!r Mars',outgoing=0)
    transport.send('STOP','private-stop2')
    assert first.startswith('db:1:')
    assert [m.body for m in transport.segment('private-q1','private-stop1')]==['!r Paris']
    assert [m.body for m in transport.segment('private-q2','private-stop2')]==['!r Mars']
    restored=DatabaseTransport(reader,MagicMock(),receipt)
    assert restored.segment('private-q1','private-stop1')==transport.segment('private-q1','private-stop1')
    assert restored.preview('private-q2') is not None
    with pytest.raises(QuizError,match='requires explicit verification'):restored.send('Question 1','private-q1')
    restored.sender.assert_not_called()
    assert all(key not in text for text,key in calls)
    assert receipt.stat().st_mode & 0o777==0o600


def test_clean_delivery_timeout_and_explicit_recovery(source,tmp_path):
    receipt=tmp_path/'receipts.json';reader=DatabaseReader(source,'Test');sender=MagicMock()
    transport=DatabaseTransport(reader,sender,receipt)
    with patch('quiz_app.database_reader.time.sleep'):
        with pytest.raises(QuizError,match='not confirmed'):transport.send('STOP','pending')
    assert transport.deliveries['pending'].native_id==''
    sender.assert_called_once_with('STOP','pending')
    with pytest.raises(QuizError,match='explicit verification'):transport.send('STOP','pending')
    append_native(source,'STOP')
    restored=DatabaseTransport(reader,MagicMock(),receipt)
    assert restored.segment('pending')==[]
    assert restored.deliveries['pending'].native_id.startswith('db:1:')
    restored.sender.assert_not_called()
    assert DatabaseTransport(reader,MagicMock(),receipt).deliveries['pending'].native_id


def test_clean_delivery_ambiguity_and_changed_group(source,tmp_path):
    reader=DatabaseReader(source,'Test');delivery=reader.reservation('same')
    assert reader.sent_identity(delivery) is None
    append_native(source,'same',outgoing=0)
    append_native(source,'same',group=2)
    assert reader.sent_identity(delivery) is None
    append_native(source,'same');append_native(source,'same')
    with pytest.raises(QuizError,match='Several new'):reader.sent_identity(delivery)
    with pytest.raises(QuizError,match='identity changed'):
        reader.sent_identity(delivery.model_copy(update={'group_id':2}))
    receipt=tmp_path/'receipts.json'
    def duplicate(text,key):append_native(source,text);append_native(source,text)
    transport=DatabaseTransport(reader,duplicate,receipt)
    with pytest.raises(QuizError,match='Several new'):transport.send('duplicate','pending')
    assert transport.deliveries['pending'].native_id==''


def test_native_boundaries_and_corrupt_receipts(source,tmp_path):
    from quiz_app.database_reader import identity_boundary,load_deliveries
    from quiz_app.storage import write_json
    reader=DatabaseReader(source,'Test')
    assert [m.body for m in reader.segment('db:1:q','db:1:s')]==['!r Paris','!r Paris']
    with readonly(source) as db:
        assert identity_boundary(db,1,'db:1:q')==1
        for key in ('db:2:q','db:1:missing','db:1:a'):
            with pytest.raises(QuizError):identity_boundary(db,1,key)
    append_native(source,'Q',stanza='q')
    with readonly(source) as db:
        with pytest.raises(QuizError):identity_boundary(db,1,'db:1:q')
    assert load_deliveries(None)=={}
    receipt=tmp_path/'receipts.json';write_json(receipt,{'bad':{'wrong':True}})
    sender=MagicMock()
    with pytest.raises(QuizError,match='ledger'):DatabaseTransport(reader,sender,receipt)
    sender.assert_not_called()
    with pytest.raises(QuizError,match='private delivery ledger'):DatabaseTransport(reader,sender).save_deliveries()


def test_receipt_write_failure_prevents_publication(source,tmp_path):
    sender=MagicMock();transport=DatabaseTransport(DatabaseReader(source,'Test'),sender,tmp_path/'receipts.json')
    with patch('quiz_app.database_reader.write_json',side_effect=QuizError('STORAGE_UNAVAILABLE','disk')):
        with pytest.raises(QuizError,match='disk'):transport.send('Question','private-key')
    sender.assert_not_called()


def test_complete_clean_native_quiz_and_archive_recovery(source,tmp_path,settings,question):
    from quiz_app.engine import Engine,new_session
    from quiz_app.messages import STOP
    from quiz_app.repository import load_session
    settings.nb_players_expected=1;settings.max_players=20
    bank=[question.model_copy(update={'id':f'question-{i}'}) for i in range(3)]
    now=[100.];reader=DatabaseReader(source,'Test');posted=[]
    def send(text,key):
        assert key not in text and '[quiz:' not in text
        posted.append(text);append_native(source,text)
    receipt=tmp_path/'native-deliveries.json'
    transport=DatabaseTransport(reader,send,receipt)
    engine=Engine(new_session(settings,bank,'native'),transport,tmp_path/'session.json',lambda:now[0])
    engine.begin();append_native(source,'!join',outgoing=0)
    now[0]=engine.session.deadline;engine.tick()
    for _ in range(3):
        append_native(source,'!r Paris',outgoing=0)
        now[0]=engine.session.deadline;engine.tick()
        assert engine.session.phase=='interval'
        now[0]=engine.session.deadline;engine.tick()
    assert engine.session.phase=='finished'
    assert all(round_.results[0].points==100 for round_ in engine.session.rounds)
    assert posted.count(STOP)==3
    assert '300 points' in posted[-1]
    snapshot=load_session(engine.path)
    restored=Engine(snapshot,DatabaseTransport(reader,MagicMock(),receipt),engine.path,lambda:now[0])
    restored.tick();restored.transport.sender.assert_not_called()
    assert restored.transport.segment(snapshot.rounds[0].start_marker,snapshot.rounds[0].stop_marker)[0].body=='!r Paris'


def test_pending_send_recovered_after_receipt_commit_failure(source,tmp_path):
    from quiz_app.storage import write_json
    reader=DatabaseReader(source,'Test');receipt=tmp_path/'receipts.json'
    transport=DatabaseTransport(reader,lambda text,key:append_native(source,text),receipt)
    writes=[]
    def commit(path,value):
        writes.append(value)
        if len(writes)==2:raise QuizError('STORAGE_UNAVAILABLE','disk')
        write_json(path,value)
    with patch('quiz_app.database_reader.write_json',side_effect=commit):
        with pytest.raises(QuizError,match='disk'):transport.send('Question','private')
    from quiz_app.storage import read_json
    assert read_json(receipt)['private']['native_id']==''
    restored=DatabaseTransport(reader,MagicMock(),receipt)
    assert restored.segment('private')==[]
    restored.sender.assert_not_called()
