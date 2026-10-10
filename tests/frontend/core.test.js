import {describe,it,expect} from 'vitest';
import {label,isActive,countdown,phaseInfo,modeLabel,historyRows,parseBank,withCorrection,grading,startSummary,generationStatus,apiError,explainError} from '../../quiz_app/static/core.js';
describe('pure dashboard rules',()=>{
 it('labels players and tells active games apart',()=>{
  expect(label({player_names:{a1111:'Alex',b2222:'Alex'}},'a1111')).toBe('Alex (joueur 1)');
  expect(label({},'Camille')).toBe('Camille');
  expect(isActive({})).toBe(false);expect(isActive({id:'g',phase:'answering'})).toBe(true);expect(isActive({id:'g',phase:'finished'})).toBe(false);
 });
 it('counts down timed phases against their configured duration',()=>{
  expect(countdown({phase:'registration',deadline:40,settings:{registration_seconds:60}},10)).toEqual({seconds:30,ratio:0.5});
  expect(countdown({phase:'answering',deadline:1},10)).toEqual({seconds:0,ratio:0});
  expect(countdown({phase:'interval',deadline:15},10)).toEqual({seconds:5,ratio:1});
  expect(countdown({phase:'paused'})).toBeNull();
  expect(countdown({phase:'interval',deadline:Date.now()/1000+5,settings:{interval_seconds:10}}).seconds).toBe(5);
 });
 it('names phases, modes and history rows',()=>{
  for(const phase of ['registration','answering','interval','paused','finished','cancelled'])expect(phaseInfo(phase).label).not.toBe('Prêt');
  expect(phaseInfo(undefined)).toMatchObject({label:'Prêt',tone:'idle'});
  expect(modeLabel({mode:'simulation'})).toBe('Simulation');expect(modeLabel({mode:'native',rehearsal:true})).toBe('Répétition');expect(modeLabel({mode:'native'})).toBe('Validée');
  const session={player_names:{p1:'Aïcha'},rounds:[{question:{question:'Capitale ?'},results:[{player:'p1',answer:'Paris',points:100,source:'jev',score:0.9},{player:'p2',points:0,source:'fallback'}]},{}]};
  expect(historyRows(session)).toEqual([{title:'Question 1 · Capitale ?',answers:['Aïcha · Paris · 100 pts · jev 0.90','p2 · sans réponse · 0 pts · repli local']},{title:'Question 2 · ',answers:[]}]);
  expect(historyRows({})).toEqual([]);
 });
 it('validates the editable bank container',()=>{
  expect(parseBank('[]')).toEqual([]);
  expect(()=>parseBank('{}')).toThrow('liste JSON');
  expect(()=>parseBank('{')).toThrow();
 });
 it('copies jev criteria and fallback aliases, dropping retired correction fields',()=>{
  const legacy={id:'president',question:'Président ?',answer:'Faye',grading_mode:'person_name',units:['km'],require_unit:true,explanation:'x'};
  expect(withCorrection(legacy,' Diomaye Faye ',' Toute autre réponse ',' Bassirou Diomaye Faye \n\n Faye ')).toEqual({
   id:'president',question:'Président ?',explanation:'x',criteria:{true:'Diomaye Faye',false:'Toute autre réponse'},aliases:['Bassirou Diomaye Faye','Faye']});
  expect(withCorrection({id:'q'},'a','b','').aliases).toEqual([]);
 });
 it('explains grading sources and summarizes the next game',()=>{
  expect(grading({source:'jev',score:0.876})).toBe(' · jev 0.88');expect(grading({source:'local'})).toBe(' · règle locale');expect(grading({})).toBe('');
  const settings={question_seconds:30,registration_seconds:60,nb_players_expected:2,max_players:10};
  expect(startSummary(1,settings,false)).toBe('1 question · 30 s par question · inscriptions 60 s · 2 à 10 joueurs');
  expect(startSummary(3,settings,true)).toBe('3 questions · 30 s par question · inscriptions 60 s · 2 à 10 joueurs · réglages modifiés, non enregistrés');
 });
 it('describes every generation state',()=>{
  expect(generationStatus({status:'running',started:100,request:{count:12,themes:'anime',difficulty:'moyenne'}},230)).toContain('prépare 12 questions (anime, moyenne) depuis 2 min 10 s');
  expect(generationStatus({status:'running',started:300},230)).toContain('prépare depuis 0 min 0 s');
  expect(generationStatus({status:'done',started:100,finished:190,cost_usd:1.5})).toContain('Lot prêt en 1 min 30 s · coût 1.50 $');
  expect(generationStatus({status:'done',applied:'questions.before-merge-1.json'})).toContain('Sauvegarde : questions.before-merge-1.json');
  expect(generationStatus({status:'failed',error:'boom'})).toBe('🚨 La génération a échoué : boom');
  expect(generationStatus({status:'cancelled'})).toContain('annulée');expect(generationStatus({status:'idle'})).toBe('');expect(generationStatus({})).toBe('');
 });
 it('turns server, validation, network and incident errors into French explanations',()=>{
  expect(apiError(409,{error:'GAME_ACTIVE',message:'Cancel first'})).toMatchObject({code:'GAME_ACTIVE',message:'Cancel first'});
  expect(apiError(422,{detail:[{loc:['body','settings','port']},{}]})).toMatchObject({code:'VALIDATION',message:'Champs : settings › port, '});
  expect(apiError(403,{error:'ORIGIN_FORBIDDEN'})).toMatchObject({code:'ORIGIN_FORBIDDEN',message:'ORIGIN_FORBIDDEN'});
  expect(apiError(500,{detail:'Internal'}).message).toBe('Internal');expect(apiError(500,null).code).toBe('UNKNOWN');
  expect(explainError(apiError(409,{error:'GAME_ACTIVE',message:'Cancel first'}))).toEqual({title:'Une partie est déjà en cours',hint:expect.stringContaining('Arrêtez-la'),detail:'Cancel first'});
  expect(explainError(apiError(403,{error:'ORIGIN_FORBIDDEN'})).detail).toBe('');
  expect(explainError('PUBLICATION_UNCERTAIN: Pasted message did not match')).toMatchObject({title:'Envoi incertain',detail:'Pasted message did not match'});
  expect(explainError('incident sans code')).toMatchObject({title:'Erreur inattendue',detail:'incident sans code'});
  expect(explainError(new TypeError('Load failed')).title).toBe('Serveur injoignable');
  expect(explainError(Object.assign(new Error('Indiquez des thèmes.'),{code:'INPUT'}))).toEqual({title:'Formulaire incomplet',hint:'Indiquez des thèmes.',detail:''});
 });
});
