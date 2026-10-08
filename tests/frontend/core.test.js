import {describe,it,expect} from 'vitest';
import {summary,remaining,parseBank,label,withCorrection} from '../../quiz_app/static/core.js';
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

it('copies correction modes without retaining incompatible units',()=>{
 const question={id:'length',question:'Longueur ?',answer:'12 km'};
 expect(withCorrection(question,'number',' km \n\nkilomètres ',true)).toEqual({...question,grading_mode:'number',units:['km','kilomètres'],require_unit:true});
 expect(withCorrection(question,'number','',false).require_unit).toBe(false);
 expect(withCorrection(question,'person_name','km',true)).toEqual({...question,grading_mode:'person_name',units:[],require_unit:false});
 expect(question).not.toHaveProperty('grading_mode');
});
