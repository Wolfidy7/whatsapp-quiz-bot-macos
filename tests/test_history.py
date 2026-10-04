import pytest
from quiz_app.errors import QuizError
from quiz_app.models import Message
from quiz_app.history import window,merge_pages,reconcile
from quiz_app.native import clean_description,parse_description,ordered_page,collect_history,NativeTransport

def message(id,body='',outgoing=False):
    return Message(author='Camille',body=body,outgoing=outgoing,fingerprint=str(id))

def test_window():
    q=message(1,'Q',True); a=message(2,'answer'); s=message(3,'S',True)
    assert window([q,a,s],'Q','S')==[a]
    assert window([q,a],'Q')==[a]
    for rows in ([a,s],[q,a],[s,q],[q,q,a,s]):
        with pytest.raises(QuizError): window(rows,'Q','S')

def test_pages():
    a,b,c,d=[message(i) for i in range(4)]
    assert merge_pages([a,b,c],[b,c,d])==[a,b,c,d]
    for older,newer in [([a],[d]),([a,a],[a,a,d]),([a,b],[b,c])]:
        with pytest.raises(QuizError): merge_pages(older,newer)
    assert reconcile([a],[a,b])==[a,b]
    with pytest.raises(QuizError): reconcile([a,b],[b])

@pytest.mark.parametrize('description,body,outgoing',[
 ('Message from Camille, !r Paris, 09:00, Received in Test','!r Paris',False),
 ('Your message, Q, 09:00, Sent to Test, Delivered','Q',True),
 ('Reply to You.\nMessage from Camille, !r Paris, 09:00, Received in Test.\nQuoted message.\nQ','!r Paris',False),
 ('Your message, STOP, 09:00, Sent to Test, Sent, Edited','STOP',True),
 ('Message from Camille, hello, world, 09:00, Received in Test, Edited','hello, world',False),
])
def test_parser(description,body,outgoing):
    row=parse_description(description,'Test','Today')
    assert row.body==body and row.outgoing==outgoing

def test_parser_failure():
    assert clean_description('\u200eÉcole')=='École'
    assert parse_description('Your reaction 👍','Test','Today') is None
    with pytest.raises(QuizError): parse_description('Message from missing metadata','Test','Today')

def test_order():
    a,b=message(1),message(2)
    assert ordered_page([(1,a),(2,b)])==[a,b]
    for rows in ([(2,a),(1,b)],[(1,a),(1,b)]):
        with pytest.raises(QuizError): ordered_page(rows)

class View:
    def __init__(self,pages): self.pages=pages;self.index=0;self.restored=0
    def latest(self): self.index=0;self.restored+=1
    def page(self): return self.pages[self.index]
    def older(self):
        if self.index+1==len(self.pages): return False
        self.index+=1;return True

def test_collection():
    q,a,b,c,s=message(1,'Q',True),message(2),message(3),message(4),message(5,'S',True)
    view=View([[b,c,s],[q,a,b,c]])
    sends=[]
    transport=NativeTransport(view,lambda text,marker:sends.append((text,marker)),3)
    assert transport.segment('Q','S')==[a,b,c]
    assert view.restored==2
    transport.send('hello','M');assert sends==[('hello','M')]
    for pages,limit in [([[a]],3),([[b,s],[q,a,b]],0),([[b,s],[q,a]],3)]:
        view=View(pages)
        with pytest.raises(QuizError): collect_history(view,'Q','S',limit)
        assert view.index==0

def test_edit_freezes_first_observation():
    original=message(1,'!r London')
    edited=original.model_copy(update={'body':'!r Paris','edited':True})
    with pytest.raises(QuizError):reconcile([original],[edited])
    flag_only=original.model_copy(update={'edited':True})
    assert reconcile([original],[flag_only])[0].body=='!r London'
    assert reconcile([original],[flag_only])[0].edited is False


def test_collect_one_hundred_across_screens():
    from quiz_app.native import collect_recent
    rows=[message(i,f'message {i}') for i in range(100)]
    pages=[rows[max(0,90-index*8):100-index*8] for index in range(12)]
    pages.append(rows[:4])
    view=View(pages)
    assert collect_recent(view,100,50)==rows
    assert view.index==0
    assert collect_recent(View([rows[:5]]),100,50)==rows[:5]
    assert collect_recent(View([rows]),10,2)==rows[-10:]
    with pytest.raises(QuizError):collect_recent(View(pages),100,1)
    for count,budget in [(0,1),(1,0)]:
        with pytest.raises(ValueError):collect_recent(View(pages),count,budget)


def test_verified_native_single_anchor():
    row=message(1,'long message').model_copy(update={'native_id':'row-1'})
    before=message(0,'older');after=message(2,'newer')
    assert merge_pages([before,row],[row,after])==[before,row,after]
    distinct=row.model_copy(update={'native_id':'row-2','fingerprint':'different-native-row'})
    with pytest.raises(QuizError):merge_pages([before,distinct],[row,after])


def test_fast_native_preview():
    q,a,b,c=message(1,'Q',True),message(2),message(3),message(4)
    view=View([[q,a,b]])
    transport=NativeTransport(view,lambda text,marker:None,10)
    assert transport.preview('Q')==[a,b]
    view.pages=[[a,b,c]]
    assert transport.preview('Q')==[a,b,c]
    view.pages=[[message(100)]]
    assert transport.preview('Q') is None
    assert transport.preview('absent') is None
    assert view.restored==0 # no history traversal while STOP deadline is running


def test_unrelated_edits_do_not_change_quiz_attempts():
    from quiz_app.history import reconcile_game
    from quiz_app.models import Message
    old=Message(author='Camille',author_id='one',body='typo',fingerprint='message-one')
    new=old.model_copy(update={'body':'corrected'})
    extra=Message(author='Robin',author_id='two',body='!r Paris',fingerprint='message-two')
    assert reconcile_game([old],[new,extra],'!join','!r')==[old,extra]
    assert new.body=='corrected' # the source observation is not mutated
    for changed in [{'body':'!join'},{'body':'!r Paris'},{'author_id':'different'},{'fingerprint':'different'}]:
        with pytest.raises(QuizError):reconcile_game([old],[old.model_copy(update=changed)],'!join','!r')
    for command in ['!join','!r Paris']:
        answer=old.model_copy(update={'body':command})
        with pytest.raises(QuizError):reconcile_game([answer],[answer.model_copy(update={'body':'corrected'})],'!join','!r')
    sent=old.model_copy(update={'outgoing':True})
    with pytest.raises(QuizError):reconcile_game([sent],[sent.model_copy(update={'body':'changed'})],'!join','!r')
    with pytest.raises(QuizError):reconcile_game([old],[],'!join','!r')
