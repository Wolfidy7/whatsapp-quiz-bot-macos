import json
from scripts.check_questions import check, main
from quiz_app.models import Question
from quiz_app.repository import load_bank

def q(id_='weah', question='Quel footballeur a remporté le Ballon d\'Or 1995 ?', true='George Weah',
      false="La réponse est fausse si elle : désigne un autre joueur (Samuel Eto'o, Drogba…), même mal écrit ; ne donne que le prénom « George » ; ou ne contient pas le nom Weah.",
      aliases=('Weah',)):
    return Question(id=id_, question=question, criteria={'true': true, 'false': false}, aliases=list(aliases))

def write(path, questions):
    path.write_text(json.dumps([x.model_dump() for x in questions], ensure_ascii=False)); return path

def test_valid_question_passes_and_naming_clauses_are_not_traps():
    assert check([q()], []) == ([], [])
    year = q('bastille', 'En quelle année a eu lieu la prise de la Bastille ?', '1789',
             'La réponse est fausse si elle donne une autre année que 1789, en chiffres ou en lettres (1788, mille sept cent quatre-vingt-treize…).', ['1789', 'en 1789'])
    pox = q('jenner', 'Contre quelle maladie Jenner a-t-il créé un vaccin ?', 'La variole',
            'La réponse est fausse si elle : désigne une autre maladie (rage, rougeole…), même mal écrite ; ou désigne la vaccine au lieu de la variole.', ['variole'])
    teeth = q('dents', 'Combien de dents de lait ?', '20', 'La réponse est fausse si elle donne un autre nombre que 20 (18, 24, vingt-quatre…).', ['20', 'vingt'])
    assert check([year, pox, teeth], []) == ([], [])

def test_authoring_errors_are_blocking():
    bad = [
        q('form', false='Toute autre réponse'),
        q('accepted', false='La réponse est fausse si elle ne contient ni Weah ni une orthographe proche (Wea).'),
        q('instruction', true='George Weah, y compris Weah seul'),
        q('given', question='Quel joueur, George Weah ou un autre, a gagné en 1995 ?'),
        q('first', aliases=['George']),
        q('echo', question='Quel joueur libérien a gagné le Ballon d\'Or 1995 ?', aliases=['libérien']),
        q('trap', aliases=['Drogba']),
    ]
    errors, _ = check(bad, [])
    for id_, text in [('form', 'doit commencer'), ('accepted', 'forme acceptée'), ('instruction', 'consigne'),
                      ('given', 'contient déjà la bonne réponse'), ('first', '« George » cité comme piège'),
                      ('echo', 'repris de la question'), ('trap', '« Drogba » cité comme piège')]:
        assert any(e.startswith(f'{id_} : ') and text in e for e in errors), (id_, errors)

def test_bank_conflicts_and_warnings():
    existing = q('weah')
    errors, warnings = check([q('weah', question='Autre ?'), q('copy'), q('dante', 'Qui a écrit La Divine Comédie ?', 'Dante Alighieri',
                              'La réponse est fausse si elle désigne un autre poète (Pétrarque…), même mal écrit ; ou ne contient pas le nom Dante.', ['Dante', '24'])], [existing])
    assert errors == ['weah : identifiant déjà utilisé dans la banque']
    assert any(w.startswith('copy : question déjà présente') for w in warnings)
    assert any(w.startswith('dante : alias « Dante » = premier mot') for w in warnings)
    assert not any('« 24 »' in w for w in warnings)

def test_cli_reports_merges_with_backup_and_rejects(tmp_path, capsys):
    bank = write(tmp_path / 'questions.json', [q('old')])
    batch = write(tmp_path / 'batch.json', [q('new')])
    assert main([str(batch), '--bank', str(bank)]) == 0 and len(load_bank(bank)) == 1
    assert main([str(batch), '--bank', str(bank), '--merge']) == 0
    assert [x.id for x in load_bank(bank)] == ['old', 'new']
    assert len(list(tmp_path.glob('questions.before-merge-*.json'))) == 1
    assert '✅ Ajoutées' in capsys.readouterr().out
    assert main([str(batch), '--bank', str(bank), '--merge']) == 1 and len(load_bank(bank)) == 2
    fresh = tmp_path / 'fresh.json'
    assert main([str(batch), '--bank', str(fresh), '--merge']) == 0 and 'Sauvegarde : aucune' in capsys.readouterr().out
    (tmp_path / 'broken.json').write_text('[{"id": "x"}]')
    assert main([str(tmp_path / 'broken.json'), '--bank', str(bank)]) == 1
    assert main([str(tmp_path / 'missing.json'), '--bank', str(bank)]) == 1
    assert 'Lecture impossible' in capsys.readouterr().out

def test_cli_replace_discards_bank_after_backup(tmp_path, capsys):
    bank = write(tmp_path / 'questions.json', [q('old'), q('new', question='Ancienne ?')])
    batch = write(tmp_path / 'batch.json', [q('new')])
    assert main([str(batch), '--bank', str(bank), '--replace']) == 0
    assert [x.id for x in load_bank(bank)] == ['new']
    backups = list(tmp_path.glob('questions.before-merge-*.json'))
    assert len(backups) == 1 and [x.id for x in load_bank(backups[0])] == ['old', 'new']
    assert '2 retirées' in capsys.readouterr().out
