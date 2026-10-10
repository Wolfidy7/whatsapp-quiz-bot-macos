import {it,expect,vi,afterEach,beforeEach} from 'vitest';
import {readFileSync} from 'node:fs';
const question={id:'capital',question:'Quelle est la capitale ?',criteria:{true:'Paris',false:'Toute autre ville'},aliases:[]};
const defaults=Object.fromEntries(readFileSync('.env.example','utf8').split('\n').filter(line=>line&&!line.startsWith('#')).map(line=>{const [key,...parts]=line.split('=');return [key.toLowerCase(),JSON.parse(parts.join('='))];}));
let bank,session,failure,accepted,generation;
const byId=id=>document.getElementById(id);
async function settle(){for(let i=0;i<30;i++)await Promise.resolve();}
async function click(id){byId(id).click();await settle();}
beforeEach(()=>{vi.resetModules();vi.useFakeTimers();bank=[question];session={};failure=null;accepted=true;generation={status:'idle',events:[],batch:null};document.documentElement.innerHTML=readFileSync('quiz_app/static/index.html','utf8');});
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
  if(path==='/api/generation'&&options.method==='POST')generation={status:'running',request:payload,started:Date.now()/1000-65,events:['Chargement du skill generate-questions'],batch:null};
  if(path==='/api/generation/cancel')generation={...generation,status:'cancelled'};
  if(path==='/api/generation/apply'){generation={...generation,applied:'questions.before-merge-1.json'};bank=[{...question,id:'new'}];}
  if(path.startsWith('/api/generation'))return response(generation);
  if(path.startsWith('/api/recover'))session={id:'fake',phase:'paused',error:'RECOVERY_REQUIRED'};
  const value=path==='/api/questions'?bank:path==='/api/settings'?defaults:path==='/api/test-answer'?{accepted,alias:null,reason:accepted?'Score jev 0.920 ≥ seuil 0.800.':'Score jev 0.100 < seuil 0.800.',score:accepted?0.92:0.1,source:'jev'}:session;
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
 const trial=JSON.parse(fetch.mock.calls.find(([path])=>path==='/api/test-answer')[1].body);expect(trial.ignore_accents).toBe(false);expect(trial.jev_threshold).toBe(0.8);expect(trial.jev_model).toBe('jev-latest');
 expect(byId('setting-jev_threshold').step).toBe('any');expect(byId('advanced-settings').contains(byId('setting-jev_model'))).toBe(true);
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
it('edits and tests draft jev criteria, saves them and rejects stale selections',async()=>{
 bank=[{...question,criteria:{true:'Diomaye Faye',false:'Toute autre réponse'},aliases:['Bassirou Diomaye Faye']},
  {id:'legacy',question:'Ancienne ?',answer:'Harry Potter',grading_mode:'person_name'},{id:'blank',question:'Vide ?'}];
 mockApi();await import('../../quiz_app/static/app.js');
 expect(byId('criteria-true').value).toBe('Diomaye Faye');expect(byId('criteria-false').value).toBe('Toute autre réponse');expect(byId('aliases').value).toBe('Bassirou Diomaye Faye');
 byId('candidate').value='Bassirou';byId('setting-jev_threshold').value='0.9';await click('check');
 const trial=JSON.parse(fetch.mock.calls.at(-1)[1].body);expect(trial.question.criteria.true).toBe('Diomaye Faye');expect(trial.jev_threshold).toBe(0.9);
 expect(byId('verdict').textContent).toBe('Acceptée · Score jev 0.920 ≥ seuil 0.800.');
 byId('question').value='blank';byId('question').dispatchEvent(new Event('change'));await settle();expect(byId('criteria-true').value).toBe('');
 byId('question').value='legacy';byId('question').dispatchEvent(new Event('change'));await settle();
 expect(byId('criteria-true').value).toBe('Harry Potter');expect(byId('criteria-false').value).toBe('');expect(byId('aliases').value).toBe('');
 byId('criteria-false').value='Tout autre personnage';byId('aliases').value=' Potter Harry \n\n';await click('apply-correction');
 const draft=JSON.parse(byId('bank').value);expect(draft[1]).toEqual({id:'legacy',question:'Ancienne ?',criteria:{true:'Harry Potter',false:'Tout autre personnage'},aliases:['Potter Harry']});
 expect(bank[1].grading_mode).toBe('person_name');expect(byId('verdict').textContent).toContain('Enregistrez');
 await click('save');expect(bank[1].criteria.false).toBe('Tout autre personnage');expect(byId('question').value).toBe('legacy');
 byId('question').value='capital';byId('question').dispatchEvent(new Event('change'));await settle();
 const edited=JSON.parse(byId('bank').value);edited[0].criteria.true='Macky Sall';byId('bank').value=JSON.stringify(edited);
 byId('bank').dispatchEvent(new Event('change'));await settle();expect(byId('criteria-true').value).toBe('Macky Sall');
 accepted=false;await click('check');expect(JSON.parse(fetch.mock.calls.at(-1)[1].body).question.criteria.true).toBe('Macky Sall');expect(byId('verdict').textContent).toMatch(/^Refusée/);
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
it('generates a batch in the background, reviews it and replaces the bank only after confirmation',async()=>{
 mockApi();vi.stubGlobal('confirm',vi.fn(()=>false));await import('../../quiz_app/static/app.js');
 expect(byId('gen-status').textContent).toBe('Aucune génération en cours.');expect(byId('gen-review').hidden).toBe(true);
 byId('gen-themes').value='';await click('generate');expect(fetch.mock.calls.some(([path,opts])=>path==='/api/generation'&&opts.method==='POST')).toBe(false);
 byId('gen-themes').value='  anime, sport ';byId('gen-count').value='12';byId('gen-difficulty').value='difficile';await click('generate');
 expect(JSON.parse(fetch.mock.calls.find(([path,opts])=>path==='/api/generation'&&opts.method==='POST')[1].body)).toEqual({themes:'anime, sport',count:12,difficulty:'difficile'});
 expect(byId('generate').disabled).toBe(true);expect(byId('generate-cancel').disabled).toBe(false);expect(byId('gen-form-fields').disabled).toBe(true);
 expect(byId('gen-status').textContent).toContain('Génération en cours · 1 min');expect(byId('gen-events').textContent).toBe('Chargement du skill generate-questions');
 generation={...generation,status:'done',finished:generation.started+90,cost_usd:1.5,report:'Compte rendu',events:[...generation.events,'Contrôle du lot (check_questions.py)'],
  batch:{questions:[{id:'new',question:'<b>Qui ?</b>',answer:'Weah'}],errors:[],warnings:['new : alias « Dante » = premier mot']}};
 await vi.advanceTimersByTimeAsync(1000);
 expect(byId('gen-status').textContent).toBe('Lot prêt en 1 min 30 s · coût 1.50 $. Vérifiez-le avant de remplacer la banque.');
 expect(byId('gen-questions').textContent).toBe('<b>Qui ?</b> → Weah');expect(byId('gen-questions').querySelector('b')).toBeNull();
 expect(byId('gen-checks').textContent).toBe('⚠️ new : alias « Dante » = premier mot');expect(byId('gen-report').textContent).toBe('Compte rendu');expect(byId('gen-apply').disabled).toBe(false);
 const polls=fetch.mock.calls.length;await vi.advanceTimersByTimeAsync(1000);expect(fetch.mock.calls.slice(polls).some(([path])=>path==='/api/generation')).toBe(false);
 await click('gen-apply');expect(confirm).toHaveBeenCalledWith(expect.stringContaining('1 questions'));expect(fetch.mock.calls.some(([path])=>path==='/api/generation/apply')).toBe(false);
 confirm.mockReturnValue(true);await click('gen-apply');expect(byId('gen-status').textContent).toBe('Banque remplacée. Sauvegarde : questions.before-merge-1.json.');
 expect(byId('gen-apply').disabled).toBe(true);expect(byId('question-list').querySelector('input').value).toBe('new');
 generation={...generation,applied:null,batch:{...generation.batch,errors:['new : alias cité comme piège'],warnings:[]}};await click('generate');
 generation={...generation,status:'done',started:1,finished:1,cost_usd:null,batch:{questions:[],errors:['Le lot n’a pas été écrit'],warnings:[]}};await vi.advanceTimersByTimeAsync(1000);
 expect(byId('gen-checks').textContent).toBe('❌ Le lot n’a pas été écrit');expect(byId('gen-apply').disabled).toBe(true);expect(byId('gen-status').textContent).toContain('0 min 0 s.');
 await click('generate');await click('generate-cancel');expect(byId('gen-status').textContent).toBe('Génération annulée.');expect(byId('generate').disabled).toBe(false);
});
