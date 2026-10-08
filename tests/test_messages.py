"""Player-facing French copy and native WhatsApp formatting contracts."""

import pytest
from quiz_app.engine import Engine,new_session,report,split_message
from quiz_app.messages import REGISTRATION_CLOSED,STOP,cancellation,quantity,question_prompt,registration,scoreboard,score_line,solution,next_question_delay
from quiz_app.models import Result,Round
from quiz_app.transport import Simulator


@pytest.mark.parametrize('count,expected',[(0,'0 joueurs'),(1,'1 joueur'),(2,'2 joueurs')])
def test_french_quantity(count,expected):
    assert quantity(count,'joueur')==expected


def test_announcements_use_configured_commands_and_durations(settings,question):
    settings.join_command='!inscription';settings.answer_prefix='!rep'
    settings.nb_players_expected=2;settings.max_players=50
    settings.registration_seconds=45;settings.question_seconds=20
    text=registration(settings)
    assert text.startswith('🎮 *LE QUIZ VA COMMENCER !*\n\n')
    for expected in ('*!inscription*','*45 s*','*2 joueurs*','*50 joueurs*'):assert expected in text
    assert '*COMMENT RÉPONDRE ?*' in text
    assert '*!rep* suivi d’un espace et de ta réponse' in text
    assert 'Exemple : *!rep Paris*' in text
    assert '_Seule ta première réponse envoyée pendant la question, avant STOP, compte._' in text
    assert '!r Paris' not in text
    prompt=question_prompt(question,2,3,settings)
    assert '*QUESTION 2 / 3*' in prompt and question.question in prompt
    assert '*!rep ta réponse*' in prompt and '*20 s*' in prompt
    assert '_Seule ta première réponse compte._' in prompt
    assert REGISTRATION_CLOSED.startswith('🔒 *INSCRIPTIONS TERMINÉES*')
    assert STOP.startswith('🛑 *STOP') and '_Les réponses sont fermées' in STOP
    assert 'Inscrits : *1 joueur*' in cancellation(1,2)
    assert 'Minimum requis : *2 joueurs*' in cancellation(1,2)


def test_solution_preserves_significant_characters_and_optional_explanation(question):
    q=question.model_copy(update={'criteria':question.criteria.model_copy(update={'true':'C++'}),'explanation':''})
    assert solution(q)=='✅ *LA BONNE RÉPONSE*\n\n🎯 *C++*'
    q=q.model_copy(update={'explanation':'Un langage de programmation.'})
    assert solution(q).endswith('💡 _Un langage de programmation._')
    q=q.model_copy(update={'criteria':q.criteria.model_copy(update={'true':'-5'})})
    assert '*-5*' in solution(q)


@pytest.mark.parametrize('seconds,expected',[(0,'La prochaine question arrive maintenant'),(1,'Prochaine question dans 1 seconde !'),(10,'Prochaine question dans 10 secondes !')])
def test_next_question_delay_uses_the_configured_wait(seconds,expected):
    assert expected in next_question_delay(seconds)
    assert next_question_delay(seconds).endswith('_Tenez-vous prêts !_')


@pytest.mark.parametrize('rank,badge',[(1,'🥇'),(2,'🥈'),(3,'🥉'),(4,'▫️')])
def test_score_line_badges_and_optional_breakdown(rank,badge):
    assert score_line(rank,'Camille',1)==f'{badge} {rank}. *Camille* — *1 point*'
    line=score_line(rank,'Camille',100,'Q1: 100 pts · Q2: 0 pts')
    assert '*100 points*' in line and '_Par question :_ Q1: 100 pts · Q2: 0 pts' in line


def test_french_final_report_ties_and_per_question_points(settings,question):
    session=new_session(settings,[question],'simulation')
    session.players=['a','b','c'];session.player_names={'a':'Camille','b':'Robin','c':'Alex'}
    session.rounds=[Round(question=question,start_marker='q',stop_marker='s',results=[Result(player='a',points=100),Result(player='b',points=100),Result(player='c',points=0)])]
    final=report(session,True)
    assert final.startswith('🎉 *QUIZ TERMINÉ !*\n\n🏆 *CLASSEMENT FINAL*')
    assert '🥇 1. *Camille* — *100 points*' in final
    assert '🥇 1. *Robin* — *100 points*' in final
    assert '🥉 3. *Alex* — *0 points*' in final
    assert '_Par question :_ Q1: 100 pts' in final
    assert final.endswith('👏 _Merci à tous pour votre participation !_')
    assert '📊 *CLASSEMENT PROVISOIRE*' in report(session)
    assert 'Par question' not in report(session)
    assert scoreboard([],False)=='📊 *CLASSEMENT PROVISOIRE*'


def test_layout_aware_splitting_preserves_text_and_whatsapp_formatting():
    blocks=[score_line(1,'Camille',100),score_line(2,'Robin',20),score_line(3,'Alex',0)]
    text=scoreboard(blocks,True)
    chunks=split_message(text,95)
    assert len(chunks)>1 and ''.join(chunks)==text
    assert all(len(chunk)<=95 for chunk in chunks)
    assert all(chunk.count('*')%2==0 and chunk.count('_')%2==0 for chunk in chunks)
    assert split_message('abc\ndef\nghi',7)==['abc\n','def\nghi']
    assert split_message('abcdefgh',3)==['abc','def','gh']
    assert split_message('',3)==['']
    with pytest.raises(ValueError):split_message('a',0)


def test_all_game_publications_are_french_and_clean(tmp_path,settings):
    from quiz_app.models import Question
    q=Question(id='capital',question='Quelle est la capitale de la France ?',criteria={'true':'Paris','false':'Autre'},explanation='Paris est la capitale française.')
    now=[100.];sim=Simulator();engine=Engine(new_session(settings,[q],'simulation'),sim,tmp_path/'session.json',lambda:now[0])
    engine.begin();sim.inject('Camille','!join')
    now[0]=engine.session.deadline;engine.tick()
    sim.inject('Camille','!r Paris');now[0]=engine.session.deadline;engine.tick()
    now[0]=engine.session.deadline;engine.tick()
    outgoing=[message.body for message in sim.messages if message.outgoing]
    assert 'Exemple : *!r Paris*' in outgoing[0]
    assert 'avant STOP' in outgoing[0]
    assert engine.session.phase=='finished' and len(outgoing)==6
    for heading in ('LE QUIZ VA COMMENCER','INSCRIPTIONS TERMINÉES','QUESTION 1 / 1','STOP','LA BONNE RÉPONSE','CLASSEMENT FINAL'):
        assert any(heading in body for body in outgoing)
    assert all('[quiz:' not in body and '[validation:' not in body for body in outgoing)
    assert all(word not in '\n'.join(outgoing) for word in ('registration','Reply','Answer:','standings','by question'))
    assert engine.session.rounds[0].results[0].points==100
