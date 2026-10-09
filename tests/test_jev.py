import json
import threading
import httpx
import pytest
from quiz_app.jev import API_URL,JevClient,JevUnavailable,NoulQuestion,request_body

QUESTION=NoulQuestion(id='fact1_senegal_president',instructions='Qui est le président actuel du Sénégal ?',true='Diomaye Faye',false='Toute autre réponse')

def reply(noul=0.93,status=200):
    return httpx.Response(status,json={'model':'jev-1.13.0','answers':{QUESTION.id:{'type':'noul','noul':noul}},'usage':{'input_tokens':1,'output_tokens':1}})

def client(handler,**options):
    sleeps=[]
    jev=JevClient('sk-test','jev-latest',http=httpx.Client(transport=httpx.MockTransport(handler)),sleep=sleeps.append,**options)
    return jev,sleeps

def test_request_contract_and_success():
    seen=[]
    def handler(request):
        seen.append(request);return reply(0.93)
    jev,sleeps=client(handler)
    assert jev.score(QUESTION,'Bassirou Diomaye Faye')==0.93 and sleeps==[]
    request=seen[0]
    assert str(request.url)==API_URL and request.method=='POST'
    assert request.headers['authorization']=='Bearer sk-test'
    assert json.loads(request.content)=={'model':'jev-latest','state':'Bassirou Diomaye Faye','questions':{QUESTION.id:{
        'type':'noul','instructions':'Qui est le président actuel du Sénégal ?','criteria':{'true':'Diomaye Faye','false':'Toute autre réponse'}}}}
    assert request_body('m',QUESTION,'x')['state']=='x'

def test_integer_bounds_are_probabilities():
    assert client(lambda request:reply(1))[0].score(QUESTION,'x')==1.0
    assert client(lambda request:reply(0))[0].score(QUESTION,'x')==0.0

def test_retries_overload_and_network_errors_with_backoff():
    responses=iter([httpx.ConnectTimeout('slow'),reply(status=429),reply(0.2)])
    def handler(request):
        item=next(responses)
        if isinstance(item,Exception):raise item
        return item
    jev,sleeps=client(handler)
    assert jev.score(QUESTION,'Macky Sall')==0.2 and sleeps==[0.5,1.0]

def test_exhausted_retries_are_unavailable():
    calls=[]
    def handler(request):
        calls.append(1);return reply(status=529)
    jev,sleeps=client(handler)
    with pytest.raises(JevUnavailable,match='plusieurs tentatives'):jev.score(QUESTION,'x')
    assert len(calls)==3 and sleeps==[0.5,1.0]

@pytest.mark.parametrize('response',[
    httpx.Response(401,json={'error':'bad key'}),
    httpx.Response(422,json={'error':'state'}),
    httpx.Response(200,text='not json'),
    httpx.Response(200,json={'answers':{}}),
    httpx.Response(200,json=[]),
    reply(1.2),reply(-0.1),reply(True),reply('0.9'),reply(None),
])
def test_definitive_failures_do_not_retry(response):
    calls=[]
    def handler(request):
        calls.append(1);return response
    with pytest.raises(JevUnavailable):client(handler)[0].score(QUESTION,'x')
    assert len(calls)==1

def test_score_many_is_parallel_ordered_and_isolates_failures():
    barrier=threading.Barrier(3,timeout=5)
    def handler(request):
        state=json.loads(request.content)['state']
        barrier.wait()
        return reply(status=401) if state=='?' else reply(0.9 if state=='Diomaye Faye' else 0.1)
    jev,_=client(handler)
    scores=jev.score_many(QUESTION,{'b':'Diomaye Faye','a':'Macky Sall','c':'?'})
    assert list(scores)==['b','a','c'] and scores=={'b':0.9,'a':0.1,'c':None}
    assert jev.score_many(QUESTION,{})=={}

def test_default_http_client_has_timeout():
    assert JevClient('k','m').http.timeout.read==8.0
