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
    CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY,ZSORT INTEGER,ZSTANZAID TEXT,ZTEXT TEXT,ZISFROMME INTEGER,ZMESSAGEDATE REAL,ZPUSHNAME TEXT,ZFROMJID TEXT,ZGROUPMEMBER INTEGER,ZCHATSESSION INTEGER);
    INSERT INTO ZWACHATSESSION VALUES (1,'Test',1,0),(2,'Other',1,0);
    INSERT INTO ZWAGROUPMEMBER VALUES (1,'Camille',NULL,'member-a');
    INSERT INTO ZWAMESSAGE VALUES (1,1,'q','Q',1,812592001,NULL,'self',NULL,1);
    INSERT INTO ZWAMESSAGE VALUES (2,2,'a','!r Paris',0,812592002,NULL,'member-a',1,1);
    INSERT INTO ZWAMESSAGE VALUES (3,3,'b','!r Paris',0,812592003,NULL,'member-a',1,1);
    INSERT INTO ZWAMESSAGE VALUES (4,4,'s','STOP',1,812592004,NULL,'self',NULL,1);
    INSERT INTO ZWAMESSAGE VALUES (5,5,'late','!r London',0,812592005,'Robin','member-b',NULL,1);
    INSERT INTO ZWAMESSAGE VALUES (6,1,'private','OTHER GROUP',0,812592005,'Private','private',NULL,2);
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
    db.executemany('INSERT INTO ZWAMESSAGE VALUES (?,?,?, ?,0,812592005,?,?,NULL,1)',[(i,i,f'id-{i}',f'!r reply {i}','Camille','member-a') for i in range(100,200)])
    db.commit();db.close()
    rows=DatabaseReader(source,'Test').recent(100)
    assert len(rows)==100 and rows[0].body=='!r reply 100' and rows[-1].body=='!r reply 199'


def test_group_address_is_not_a_player():
    message=parse_row((1,1,'id','!join',False,0,'Group','group@g.us'),1)
    assert message.author_id=='' and message.author==''


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
