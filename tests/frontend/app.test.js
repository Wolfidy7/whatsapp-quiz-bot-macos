import {it,expect,vi,afterEach,beforeEach} from 'vitest';
import {readFileSync} from 'node:fs';
const question={id:'capital',question:'Quelle est la capitale ?',answer:'Paris'};
const defaults=Object.fromEntries(readFileSync('.env.example','utf8').split('\n').filter(line=>line&&!line.startsWith('#')).map(line=>{const [key,...parts]=line.split('=');return [key.toLowerCase(),JSON.parse(parts.join('='))];}));
let bank,session,failure,accepted;
const byId=id=>document.getElementById(id);
async function settle(){for(let i=0;i<30;i++)await Promise.resolve();}
async function click(id){byId(id).click();await settle();}
beforeEach(()=>{vi.resetModules();vi.useFakeTimers();bank=[question];session={};failure=null;accepted=true;document.documentElement.innerHTML=readFileSync('quiz_app/static/index.html','utf8');});
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();});
function response(value,ok=true){return {ok,json:async()=>value};}
function mockApi() {
 vi.stubGlobal('fetch',vi.fn(async(path,options)=>{
  const payload=options.body?JSON.parse(options.body):undefined;
  if(failure){const value=failure;failure=null;return response(value,false);}
  if(path==='/api/questions'&&options.method==='PUT')bank=payload;
  if(path==='/api/start')session={id:'fake',mode:payload.mode,phase:'registration',players:[],rounds:[],deadline:Date.now()/1000+60,settings:payload.settings};
  if(path==='/api/inject'){session.players=[payload.author];session.player_names={[payload.author]:payload.author};}
  if(path==='/api/cancel')session.phase='cancelled';
  if(path.startsWith('/api/recover'))session={id:'fake',phase:'paused',error:'RECOVERY_REQUIRED'};
  const value=path==='/api/questions'?bank:path==='/api/settings'?defaults:path==='/api/test-answer'?{accepted,alias:accepted?'Paris':null,reason:accepted?'Correspondance exacte.':'Aucune référence correspondante.'}:session;
  return response(value);
 }));
}
it('edits settings, starts snapshots, renders live rankings and stops a game',async()=>{
 mockApi();URL.createObjectURL=vi.fn(()=>'blob:fake');URL.revokeObjectURL=vi.fn();
 const anchor=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 await import('../../quiz_app/static/app.js');
 expect(byId('setting-max_players').value).toBe('20');expect(byId('participants').textContent).toContain('attente');
 byId('setting-whatsapp_group').value='Groupe fictif';byId('setting-poll_seconds').value='0.5';byId('setting-ignore_accents').checked=false;
 await click('save-settings');expect(byId('settings-status').textContent).toContain('enregistrés');
 expect(JSON.parse(fetch.mock.calls.find(([path,opts])=>path==='/api/settings'&&opts.method==='PUT')[1].body).ignore_accents).toBe(false);
 await click('save');await click('check');expect(byId('verdict').textContent).toContain('Acceptée');accepted=false;await click('check');expect(byId('verdict').textContent).toContain('Refusée');
 expect(JSON.parse(fetch.mock.calls.find(([path])=>path==='/api/test-answer')[1].body).ignore_accents).toBe(false);
 byId('mode').value='simulation';byId('mode').dispatchEvent(new Event('change'));expect(byId('mode-help').textContent).toContain('aucun message');
 await click('start');expect(byId('phase').textContent).toBe('INSCRIPTIONS');expect(byId('start').disabled).toBe(true);expect(byId('cancel').disabled).toBe(false);
 const payload=JSON.parse(fetch.mock.calls.find(([path])=>path==='/api/start')[1].body);expect(payload.settings.whatsapp_group).toBe('Groupe fictif');expect(payload.settings.poll_seconds).toBe(.5);expect(payload.question_ids).toEqual(['capital']);
 await click('inject');expect(byId('players').textContent).toBe('1');expect(byId('participants').textContent).toContain('Camille');
 session.outbox=[{status:'pending',text:'Réservation'},{status:'sent',text:'Envoyé'}];session.phase='answering';session.rounds=[{question,results:[]}];
 session.live={provisional:true,ranking:[{rank:1,name:'<script>Camille</script>',points:100,round_points:100,answered:true},{rank:4,name:'Robin',points:20,round_points:0,answered:false}]};
 await vi.advanceTimersByTimeAsync(1000);expect(byId('prompt').textContent).toBe(question.question);expect(byId('pending').textContent).toBe('Réservation');expect(byId('ranking-status').textContent).toBe('PROVISOIRE');expect(byId('ranking').textContent).toContain('100 pts');expect(byId('ranking').querySelector('script')).toBeNull();
 byId('setting-whatsapp_group').value='Ne pas écraser';await vi.advanceTimersByTimeAsync(1000);expect(byId('setting-whatsapp_group').value).toBe('Ne pas écraser');
 await click('stop-now');expect(byId('phase').textContent).toBe('ARRÊTÉ');expect(byId('start').disabled).toBe(false);
 byId('mode').value='rehearsal';byId('mode').dispatchEvent(new Event('change'));await click('start');expect(session.mode).toBe('native');await click('cancel');
 byId('mode').value='native';await click('start');await click('cancel');await click('recover');expect(byId('notice').textContent).toBe('RECOVERY_REQUIRED');await click('resume');
 await click('export');expect(anchor).toHaveBeenCalled();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');
 Object.defineProperty(byId('import'),'files',{value:[{text:async()=>JSON.stringify(bank)}],configurable:true});byId('import').dispatchEvent(new Event('change'));await settle();expect(byId('bank').value).toContain(question.question);
 Object.defineProperty(byId('import'),'files',{value:[],configurable:true});byId('import').dispatchEvent(new Event('change'));await settle();
 for(const value of [{message:'stockage indisponible'},{detail:'schéma invalide'},{error:'UNKNOWN'}]){failure=value;await click('save');expect(byId('notice').textContent.length).toBeGreaterThan(0);}
 byId('bank').value='{';await click('save');expect(byId('notice').textContent.length).toBeGreaterThan(0);
});
it('validates forms and selections before any start or settings write',async()=>{
 mockApi();await import('../../quiz_app/static/app.js');
 byId('setting-max_players').value='';await click('start');await click('save-settings');expect(fetch.mock.calls.filter(([path,opts])=>path==='/api/start'||path==='/api/settings'&&opts.method==='PUT')).toHaveLength(0);
 byId('setting-max_players').value='20';byId('question-list').querySelector('input').checked=false;await click('start');expect(byId('notice').textContent).toContain('Sélectionnez');
});
it('edits and tests draft correction modes, saves them and rejects stale selections',async()=>{
 bank=[{...question,answer:'Harry Potter',grading_mode:'person_name'},
  {id:'distance',question:'Distance ?',answer:'12 km',grading_mode:'number',units:['km','kilomètres'],require_unit:true}];
 mockApi();await import('../../quiz_app/static/app.js');
 expect(byId('grading-mode').value).toBe('person_name');expect(byId('numeric-options').hidden).toBe(true);
 byId('candidate').value='Potter Harry';await click('check');
 expect(JSON.parse(fetch.mock.calls.at(-1)[1].body).question.grading_mode).toBe('person_name');
 byId('question').value='distance';byId('question').dispatchEvent(new Event('change'));await settle();
 expect(byId('numeric-options').hidden).toBe(false);expect(byId('units').value).toBe('km\nkilomètres');expect(byId('require-unit').checked).toBe(true);
 byId('units').value=' km \n\nkilomètres\nKM ';await click('apply-correction');
 const draft=JSON.parse(byId('bank').value);expect(draft[0].grading_mode).toBe('person_name');expect(draft[1].units).toEqual(['km','kilomètres','KM']);
 expect(bank[1].units).toEqual(['km','kilomètres']);expect(byId('verdict').textContent).toContain('Enregistrez');
 byId('candidate').value='12,0 km';await click('check');expect(JSON.parse(fetch.mock.calls.at(-1)[1].body).question.require_unit).toBe(true);
 await click('save');expect(bank[1].units).toEqual(['km','kilomètres','KM']);expect(byId('question').value).toBe('distance');
 byId('question').value='distance';byId('question').dispatchEvent(new Event('change'));await settle();
 byId('grading-mode').value='exact';byId('grading-mode').dispatchEvent(new Event('change'));expect(byId('numeric-options').hidden).toBe(true);
 await click('apply-correction');expect(JSON.parse(byId('bank').value)[1].units).toEqual([]);await click('save');expect(bank[1].require_unit).toBe(false);
 byId('question').value='capital';byId('question').dispatchEvent(new Event('change'));await settle();
 const edited=JSON.parse(byId('bank').value);edited[0].answer='Hermione Granger';byId('bank').value=JSON.stringify(edited);
 byId('bank').dispatchEvent(new Event('change'));await settle();await click('check');expect(JSON.parse(fetch.mock.calls.at(-1)[1].body).question.answer).toBe('Hermione Granger');
 byId('bank').value='[]';await click('check');expect(byId('notice').textContent).toContain('brouillon JSON');
});
it('keeps Stop usable during an in-flight Start and avoids overlapping polling requests',async()=>{
 mockApi();await import('../../quiz_app/static/app.js');const original=fetch;let releaseStart,releasePoll;
 vi.stubGlobal('fetch',vi.fn((path,options)=>{
  if(path==='/api/start')return new Promise(resolve=>{releaseStart=()=>resolve(response({phase:'cancelled',stop_requested:true}));});
  if(path==='/api/cancel')return Promise.resolve(response({stop_requested:true}));
  if(path==='/api/session')return new Promise(resolve=>{releasePoll=()=>resolve(response({}));});
  return original(path,options);
 }));
 byId('start').click();await settle();expect(byId('cancel').disabled).toBe(false);expect(byId('start').disabled).toBe(true);
 await click('cancel');expect(byId('notice').textContent).toContain('Arrêt demandé');
 await vi.advanceTimersByTimeAsync(3000);expect(fetch.mock.calls.filter(([path])=>path==='/api/session')).toHaveLength(1);
 releasePoll();releaseStart();await settle();expect(byId('phase').textContent).toBe('ARRÊTÉ');expect(byId('notice').textContent).toBe('Partie arrêtée.');
});
