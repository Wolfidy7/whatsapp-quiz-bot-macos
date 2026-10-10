import {describe,it,expect} from 'vitest';
import {summary,remaining,parseBank,label,withCorrection,grading,verdictText,generationStatus} from '../../quiz_app/static/core.js';
describe('pure dashboard rules',()=>{
 it('formats complete evidence safely',()=>{
  expect(summary({})).toBe('Aucune partie active.');
  expect(label({player_names:{a1111:'Alex',b2222:'Alex'}},'a1111')).toBe('Alex (joueur 1)');
  expect(summary({id:'test'})).toContain('en attente');
  expect(summary({id:'test',players:['id'],player_names:{id:'Camille'},rounds:[{results:[{player:'id',points:100}]}]})).toContain('Camille');
  expect(summary({id:'test',players:['<script>'],error:'incident',rounds:[{results:[{player:'Camille',answer:'Paris',points:100},{player:'Robin',points:0}]},{}]})).toContain('sans réponse');
 });
 it('counts only active deadlines',()=>{
  expect(remaining({phase:'registration',deadline:11},10)).toBe('1s');
  expect(remaining({phase:'answering',deadline:1},10)).toBe('0s');
  expect(remaining({phase:'finished'})).toBe('—');
  expect(remaining({phase:'interval',deadline:Date.now()/1000+5})).toBe('5s');
 });
 it('validates the editable bank container',()=>{
  expect(parseBank('[]')).toEqual([]);
  expect(()=>parseBank('{}')).toThrow('liste JSON');
  expect(()=>parseBank('{')).toThrow();
 });
});

it('copies jev criteria and fallback aliases, dropping retired correction fields',()=>{
 const legacy={id:'president',question:'Président ?',answer:'Faye',grading_mode:'person_name',units:['km'],require_unit:true,explanation:'x'};
 expect(withCorrection(legacy,' Diomaye Faye ',' Toute autre réponse ',' Bassirou Diomaye Faye \n\n Faye ')).toEqual({
  id:'president',question:'Président ?',explanation:'x',criteria:{true:'Diomaye Faye',false:'Toute autre réponse'},aliases:['Bassirou Diomaye Faye','Faye']});
 expect(withCorrection({id:'q'},'a','b','').aliases).toEqual([]);
 expect(legacy).toHaveProperty('grading_mode');
});
it('explains jev and fallback grading',()=>{
 expect(grading({source:'jev',score:0.876})).toBe(' · jev 0.88');
 expect(grading({source:'fallback',score:null})).toBe(' · repli local');
 expect(grading({source:'local',score:null})).toBe(' · règle locale');
 expect(grading({})).toBe('');
 expect(summary({id:'t',rounds:[{results:[{player:'A',answer:'Faye',points:100,source:'jev',score:0.9},{player:'B',answer:'Sall',points:0,source:'fallback'}]}]}))
  .toContain('A: 100 points · Faye · jev 0.90\n1. B: 0 points · Sall · repli local');
 expect(verdictText({accepted:true,alias:null,reason:'Score jev 0.900 ≥ seuil 0.800.'})).toBe('Acceptée · Score jev 0.900 ≥ seuil 0.800.');
 expect(verdictText({accepted:true,alias:'Faye',reason:'Repli local'})).toBe('Acceptée · référence « Faye » · Repli local');
 expect(verdictText({accepted:false,alias:null,reason:'Score jev 0.100 < seuil 0.800.'})).toMatch(/^Refusée · /);
});
it('describes every generation state',()=>{
  expect(generationStatus({status:'running',started:100},230)).toContain('2 min 10 s');
  expect(generationStatus({status:'running',started:300},230)).toContain('0 min 0 s');
  expect(generationStatus({status:'failed',error:'GENERATION_FAILED'})).toBe('Échec de la génération : GENERATION_FAILED');
  expect(generationStatus({status:'idle'})).toBe('Aucune génération en cours.');expect(generationStatus({})).toBe('');
});
