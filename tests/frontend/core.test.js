import {describe,it,expect} from 'vitest';
import {summary,remaining,parseBank,label} from '../../quiz_app/static/core.js';
describe('pure dashboard rules',()=>{
 it('formats complete evidence safely',()=>{
  expect(summary({})).toBe('No active game.');
  expect(label({player_names:{a1111:'Alex',b2222:'Alex'}},'a1111')).toBe('Alex [1111]');
  expect(summary({id:'test'})).toContain('waiting');
  expect(summary({id:'test',players:['id'],player_names:{id:'Camille'},rounds:[{results:[{player:'id',points:100}]}]})).toContain('Camille');
  expect(summary({id:'test',players:['<script>'],error:'incident',rounds:[{results:[{player:'Camille',answer:'Paris',points:100},{player:'Robin',points:0}]},{}]})).toContain('no answer');
 });
 it('counts only active deadlines',()=>{
  expect(remaining({phase:'registration',deadline:11},10)).toBe('1s');
  expect(remaining({phase:'answering',deadline:1},10)).toBe('0s');
  expect(remaining({phase:'finished'})).toBe('—');
  expect(remaining({phase:'interval',deadline:Date.now()/1000+5})).toBe('5s');
 });
 it('validates the editable bank container',()=>{
  expect(parseBank('[]')).toEqual([]);
  expect(()=>parseBank('{}')).toThrow('array');
  expect(()=>parseBank('{')).toThrow();
 });
});
