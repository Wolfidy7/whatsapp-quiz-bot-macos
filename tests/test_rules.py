from decimal import Decimal, ROUND_HALF_UP
import pytest
from pydantic import ValidationError
from quiz_app.grading import normalize, fallback_verdict, extract_answer
from quiz_app.models import Question, Message, Result, Round
from quiz_app.scoring import points_for_rank, standings
from quiz_app.engine import collect_players, correct_round, grade_answers, split_message
from quiz_app.errors import QuizError

@pytest.mark.parametrize('text,expected', [('  PARIS ! ','paris'),('école','ecole'),('E\u0301cole','ecole'),("L’Île", "l'ile"),('C++','c++'),('C#','c#'),('-5','-5'),('hello\n world.','hello world')])
def test_normalize(text,expected):
    assert normalize(text) == expected

def test_accents_optional():
    assert normalize('école',False)=='école'

@pytest.mark.parametrize('answer,accepted', [('PARIS!',True),('ville de Paris',True),('Pari',False),('Paris ou Londres',False),('pas Paris',False),('Paris France',False),('',False)])
def test_alias(question,answer,accepted):
    assert fallback_verdict(question,answer).accepted is accepted

@pytest.mark.parametrize('body,expected',[('!R Paris','Paris'),('!r  Paris  ','Paris'),('!r','invalid'),('!r   ','invalid'),('Paris','invalid'),('!rParis','invalid'),('!r \n Paris','Paris')])
def test_extract(body,expected):
    assert extract_answer(body,'!r') == (None if expected=='invalid' else expected)

@pytest.mark.parametrize('players',[1,2,20,50])
def test_score_all_ranks(players):
    for rank in range(1,players+1):
        expected = 100 if players==1 else int((Decimal(100)-Decimal(80)*Decimal(rank-1)/Decimal(players-1)).quantize(Decimal(1),rounding=ROUND_HALF_UP))
        assert points_for_rank(rank,players)==expected
    assert points_for_rank(25,50)==61

@pytest.mark.parametrize('args',[(0,1),(2,1),(1,0),(1,2,10,20),(1,2,100,0)])
def test_invalid_score(args):
    with pytest.raises(ValueError): points_for_rank(*args)

def test_ties():
    rows=standings(['A','B','C'],[[Result(player='A',points=100),Result(player='B',points=100)]])
    assert [row['rank'] for row in rows]==[1,1,3]
    assert rows[-1]['points']==0

def msg(author,body,outgoing=False):
    return Message(author=author,body=body,outgoing=outgoing,fingerprint=f'{author}:{body}')

def test_registration(settings):
    settings.max_players=2
    assert collect_players([msg('A','!JOIN'),msg('A','!join'),msg('bot','!join',True),msg('C','hello'),msg('B','!join'),msg('D','!join')],settings)==['A','B']
    with pytest.raises(QuizError): collect_players([msg('','!join')],settings)

def test_first_answer(question,settings):
    round_=Round(question=question,start_marker='Q',stop_marker='S',observed=[msg('A','hello'),msg('A','!r wrong'),msg('A','!r Paris'),msg('B','!r'),msg('outsider','!r Paris'),msg('B','!R Paris'),msg('bot','!r Paris',True)])
    results=correct_round(round_,['A','B','C'],settings)
    assert [(r.player,r.points) for r in results]==[('A',0),('B',100),('C',0)]
    round_.observed=[msg('','!r Paris')]
    with pytest.raises(QuizError): correct_round(round_,['A'],settings)

def test_question_blank():
    with pytest.raises(ValidationError): Question(id='x',question=' ',criteria={'true':'Paris','false':'Autre'})

def test_split():
    assert ''.join(split_message('abcde',2))=='abcde'
    assert split_message('',2)==['']


def test_settings_blank_group(settings):
    from quiz_app.models import Settings
    with pytest.raises(ValidationError):Settings.model_validate(dict(settings.model_dump(),whatsapp_group=" "))


def test_stable_sender_ids_and_identical_labels(settings,question):
    from quiz_app.engine import new_session,display_name
    messages=[msg('Alex','!join').model_copy(update={'author_id':'member-1111'}),msg('Alex','!join').model_copy(update={'author_id':'member-2222'})]
    players=collect_players(messages,settings)
    assert players==['member-1111','member-2222']
    session=new_session(settings,[question],'native');session.player_names=dict.fromkeys(players,'Alex')
    assert display_name(session,players[0])=='Alex (joueur 1)'
    round_=Round(question=question,start_marker='q',stop_marker='s',observed=[msg('Alex','!r Paris').model_copy(update={'author_id':'member-2222'})])
    assert correct_round(round_,players,settings)[1].points==100
