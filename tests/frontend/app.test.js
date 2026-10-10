import {it,expect,vi,afterEach,beforeEach} from 'vitest';
import {readFileSync} from 'node:fs';
const question={id:'capital',question:'Quelle est la capitale ?',criteria:{true:'Paris',false:'Toute autre ville'},aliases:[]};
const defaults=Object.fromEntries(readFileSync('.env.example','utf8').split('\n').filter(line=>line&&!line.startsWith('#')).map(line=>{const [key,...parts]=line.split('=');return [key.toLowerCase(),JSON.parse(parts.join('='))];}));
let bank,session,generation,capabilities,failures,stopOnly,accepted;
const byId=id=>document.getElementById(id);
async function settle(){for(let i=0;i<40;i++)await Promise.resolve();}
async function click(id){byId(id).click();await settle();}
const toasts=()=>byId('toasts').textContent;
const posted=path=>fetch.mock.calls.filter(([url,options])=>url===`/api/${path}`&&options.method!=='GET');
const lastBody=path=>JSON.parse(posted(path).pop()[1].body);
beforeEach(()=>{
 vi.resetModules();vi.useFakeTimers();bank=[question];session={};capabilities={native_ready:false};failures=[];stopOnly=false;accepted=true;
 generation={status:'idle',events:[],batch:null};history.replaceState(null,'','/');delete window.quizReady;
 document.documentElement.innerHTML=readFileSync('quiz_app/static/index.html','utf8');
 Element.prototype.scrollIntoView=vi.fn();window.scrollTo=vi.fn();
});
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();});
function response(value,ok=true,status=200){return {ok,status,json:async()=>value};}
/** Answer one API call like the FastAPI server, with optional queued failures. */
function route(path,method,payload) {
 if(path==='/api/start'){session={id:'g1',mode:payload.mode,rehearsal:payload.rehearsal,phase:'registration',players:[],player_names:{},rounds:[],questions:payload.question_ids.map(id=>bank.find(item=>item.id===id)),deadline:Date.now()/1000+60,settings:payload.settings,live:{ranking:[],provisional:false}};return session;}
 if(path==='/api/inject'){session={...session,players:[...session.players,payload.author]};return session;}
 if(path==='/api/cancel'){if(stopOnly)return {stop_requested:true};session={...session,phase:'cancelled'};return session;}
 if(path==='/api/resume'){session={...session,phase:'answering',error:null};return session;}
 if(path.startsWith('/api/recover/')){session={id:'a'.repeat(32),mode:'native',rehearsal:true,phase:'paused',error:'RECOVERY_REQUIRED: Archive loaded paused; no messages replayed',outbox:[{status:'pending',text:'Réservation STOP'},{status:'sent',text:'ok'}],players:[],rounds:[],questions:[question],settings:defaults};return session;}
 if(path==='/api/generation'&&method==='POST'){generation={status:'running',request:payload,started:Date.now()/1000-65,events:['Lecture de docs/question-generation-prompt.md'],batch:null};return generation;}
 if(path==='/api/generation/cancel'){generation={...generation,status:'cancelled'};return generation;}
 if(path==='/api/generation/apply'){generation={...generation,applied:'questions.before-merge-1.json'};bank=[{...question,id:'new',question:'Nouvelle ?'}];return generation;}
 if(path==='/api/questions'&&method==='PUT')bank=payload;
 if(path==='/api/test-answer')return {accepted,alias:accepted?'Paris':null,reason:accepted?'Score jev 0.920 ≥ seuil 0.800.':'Score jev 0.100 < seuil 0.800.',score:accepted?0.92:0.1,source:'jev'};
 return ({'/api/questions':bank,'/api/settings':method==='PUT'?payload:defaults,'/api/session':session,'/api/capabilities':capabilities,'/api/generation':generation})[path];
}
function mockApi() {
 vi.stubGlobal('fetch',vi.fn(async(path,options)=>{
  const method=options.method||'GET';const payload=options.body?JSON.parse(options.body):undefined;
  const failure=failures.find(item=>!item.path||item.path===path);
  if(failure){failures.splice(failures.indexOf(failure),1);if(failure.network)throw new TypeError('Load failed');return failure.raw?{ok:false,status:500,json:async()=>{throw new SyntaxError('bad');}}:response(failure.body,false,failure.status);}
  return response(route(path,method,payload));
 }));
}
async function load(){mockApi();await import('../../quiz_app/static/app.js');await settle();}

it('opens on the play tab, switches tabs and keeps the selected one in the URL',async()=>{
 history.replaceState(null,'','/#reglages');await load();
 expect(window.quizReady).toBe(true);expect(byId('panel-reglages').hidden).toBe(false);expect(byId('panel-jouer').hidden).toBe(true);
 await click('tab-questions');expect(location.hash).toBe('#questions');expect(byId('tab-questions').getAttribute('aria-selected')).toBe('true');expect(byId('panel-questions').hidden).toBe(false);
 history.replaceState(null,'','/#inconnu');vi.resetModules();document.documentElement.innerHTML=readFileSync('quiz_app/static/index.html','utf8');await load();
 expect(location.hash).toBe('#jouer');expect(byId('setting-max_questions')).toBeNull();
});
it('starts a simulation and follows the live game to the podium',async()=>{
 await load();
 expect(byId('selection-count').textContent).toBe('1 sur 1 question sélectionnée');expect(byId('start-summary').textContent).toContain('1 question · ');
 expect(byId('modes').querySelector('.group-name').textContent).toBe('« Test »');
 expect(byId('modes').querySelector('[value="native"]').disabled).toBe(true);expect(byId('native-text').textContent).toContain('Indisponible');
 await click('select-none');expect(byId('selection-count').textContent).toBe('0 sur 1 question sélectionnée');expect(byId('start').disabled).toBe(true);
 await click('select-all');const box=byId('question-list').querySelector('input');box.checked=false;box.dispatchEvent(new Event('change'));expect(byId('start').disabled).toBe(true);
 box.checked=true;box.dispatchEvent(new Event('change'));
 byId('modes').querySelector('[value="simulation"]').checked=true;await click('start');
 expect(lastBody('start')).toMatchObject({mode:'simulation',rehearsal:false,question_ids:['capital']});expect(toasts()).toContain('C’est parti');
 expect(byId('live').hidden).toBe(false);expect(byId('setup').hidden).toBe(true);expect(byId('stop-now').hidden).toBe(false);
 expect(byId('phase').textContent).toBe('Inscriptions');expect(byId('remaining').textContent).toBe('60s');expect(byId('ranking').textContent).toContain('après la première question');
 expect(byId('ranking-status').hidden).toBe(true);expect(byId('simulation-tools').hidden).toBe(false);expect(byId('tab-jouer').querySelector('.dot').hidden).toBe(false);
 await click('inject');expect(byId('participants').textContent).toBe('Camille');expect(byId('players').textContent).toBe('1 / 20');
 session={...session,phase:'answering',deadline:Date.now()/1000+30,rounds:[{question,results:[]}],live:{provisional:true,ranking:[
  {rank:1,name:'<img src=x>',points:100,round_points:100,answered:true},{rank:4,name:'Robin',points:0,round_points:0,answered:false}]}};
 await vi.advanceTimersByTimeAsync(1000);
 expect(toasts()).toContain('Inscriptions closes');expect(byId('prompt').textContent).toBe(`❓ ${question.question}`);expect(byId('round').textContent).toBe('1 / 1');
 expect(byId('ranking-status').textContent).toBe('Provisoire');expect(byId('ranking').querySelector('img')).toBeNull();expect(byId('ranking').textContent).toContain('4');expect(byId('countdown').hidden).toBe(false);
 session={...session,phase:'finished',rounds:[{question,results:[{player:'Camille',answer:'Paris',points:100,source:'jev',score:0.92}]}],live:{provisional:false,ranking:[{rank:1,name:'Camille',points:100,round_points:100,answered:true}]}};
 await vi.advanceTimersByTimeAsync(1000);
 expect(toasts()).toContain('Bravo à Camille, 100 pts');expect(document.querySelectorAll('.confetti').length).toBeGreaterThan(0);
 expect(byId('new-game').hidden).toBe(false);expect(byId('stop-now').hidden).toBe(true);expect(byId('countdown').hidden).toBe(true);expect(byId('ranking-status').textContent).toBe('Confirmé');
 expect(byId('history').textContent).toContain('Camille · Paris · 100 pts · jev 0.92');
 await click('new-game');expect(byId('setup').hidden).toBe(false);expect(byId('live').hidden).toBe(true);
 await vi.advanceTimersByTimeAsync(5000);expect(document.querySelectorAll('.confetti').length).toBe(0);
});
it('stops games, explains pauses, resumes them and reopens archives',async()=>{
 await load();expect(byId('history').textContent).toContain('Aucune partie');
 await click('start');expect(lastBody('start')).toMatchObject({mode:'native',rehearsal:true});expect(toasts()).toContain('Ouverture de WhatsApp');
 stopOnly=true;await click('stop-now');expect(toasts()).toContain('Arrêt demandé');
 stopOnly=false;await click('stop-now');expect(toasts()).toContain('Partie arrêtée');expect(byId('history').textContent).toContain('Aucune question jouée');
 await click('tab-historique');await click('recover');expect(byId('archive-error').textContent).toContain('Collez');expect(byId('archive-error').hidden).toBe(false);
 byId('archive').value='a'.repeat(32);await click('recover');
 expect(byId('archive-error').hidden).toBe(true);expect(byId('panel-jouer').hidden).toBe(false);expect(toasts()).toContain('Archive ouverte');
 expect(byId('incident').textContent).toContain('Partie en pause');expect(byId('incident').textContent).toContain('Réservation STOP');expect(byId('live-mode').textContent).toBe('Répétition');
 byId('incident').querySelector('button').click();await settle();expect(toasts()).toContain('Partie reprise');expect(byId('incident').hidden).toBe(true);
 session={...session,phase:'paused',error:'UI_UNAVAILABLE: WhatsApp window unavailable',outbox:[]};await vi.advanceTimersByTimeAsync(1000);
 expect(toasts()).toContain('WhatsApp n’est pas utilisable');expect(byId('incident').textContent).toContain('Détail : WhatsApp window unavailable');
 session={...session,phase:'answering',error:'PUBLICATION_UNCERTAIN: Pending'};await vi.advanceTimersByTimeAsync(1000);
 expect(byId('incident').querySelector('button')).toBeNull();expect(byId('incident').textContent).toContain('Envoi incertain');
});
it('explains server, validation and network failures next to the failing action',async()=>{
 await load();
 failures.push({path:'/api/start',status:409,body:{error:'GAME_ACTIVE',message:'Cancel the current game before starting another'}});await click('start');
 expect(byId('start-error').textContent).toContain('Une partie est déjà en cours');expect(byId('start-error').textContent).toContain('Détail : Cancel the current game');
 expect(byId('toasts').querySelector('.toast.error')).not.toBeNull();expect(byId('start').disabled).toBe(false);
 failures.push({path:'/api/start',network:true});await click('start');expect(byId('start-error').textContent).toContain('Serveur injoignable');
 failures.push({path:'/api/start',raw:true});await click('start');expect(byId('start-error').textContent).toContain('Erreur inattendue');
 byId('setting-max_players').value='';byId('config').dispatchEvent(new Event('input'));await click('start');expect(byId('start-error').textContent).toContain('Certains réglages');
 await click('save-settings');expect(byId('settings-error').textContent).toContain('Certains champs');
 byId('setting-max_players').value='10';failures.push({path:'/api/settings',status:422,body:{detail:[{loc:['body','port'],msg:'bad'}]}});await click('save-settings');
 expect(byId('settings-error').textContent).toContain('Champs invalides');expect(byId('settings-error').textContent).toContain('port');
 expect(byId('toasts').children.length).toBe(4);byId('toasts').querySelector('button').click();expect(byId('toasts').children.length).toBe(3);
});
it('reports a dashboard that cannot load its data',async()=>{
 failures.push({path:'/api/settings',network:true});await load();
 expect(window.quizReady).toBe(true);expect(toasts()).toContain('Serveur injoignable');
 await click('select-all');expect(byId('selection-count').textContent).toBe('');
});
it('generates a batch in the background, reviews it and replaces the bank after confirmation',async()=>{
 vi.stubGlobal('confirm',vi.fn(()=>false));await load();
 expect(byId('gen-status').textContent).toBe('');expect(byId('gen-review').hidden).toBe(true);expect(byId('gen-progress').hidden).toBe(true);
 byId('gen-themes').value='';await click('generate');expect(posted('generation')).toHaveLength(0);expect(byId('gen-error').textContent).toContain('Indiquez des thèmes');
 byId('gen-themes').value='  anime, sport ';byId('gen-count').value='12';byId('gen-difficulty').value='difficile';await click('generate');
 expect(lastBody('generation')).toEqual({themes:'anime, sport',count:12,difficulty:'difficile'});expect(toasts()).toContain('Claude est au travail');
 expect(byId('generate').hidden).toBe(true);expect(byId('generate-cancel').hidden).toBe(false);expect(byId('gen-form-fields').disabled).toBe(true);expect(byId('gen-progress').hidden).toBe(false);
 expect(byId('gen-status').textContent).toContain('prépare 12 questions (anime, sport, difficile) depuis 1 min');expect(byId('gen-events').textContent).toContain('Lecture de docs');
 expect(byId('tab-questions').querySelector('.dot').hidden).toBe(false);
 generation={...generation,status:'done',finished:generation.started+90,cost_usd:1.5,report:'Compte rendu',batch:{questions:[{id:'new',question:'<b>Qui ?</b>',answer:'Weah'},{id:'n2',question:'Où ?',answer:'Dakar'}],errors:[],warnings:['new : alias « Dante » = premier mot']}};
 await vi.advanceTimersByTimeAsync(1000);
 expect(toasts()).toContain('Lot prêt');expect(byId('gen-status').textContent).toBe('🎉 Lot prêt en 1 min 30 s · coût 1.50 $. Vérifiez-le avant de remplacer la banque.');
 expect(byId('gen-total').textContent).toBe('2 questions');expect(byId('gen-questions').textContent).toBe('<b>Qui ?</b>✅ WeahOù ?✅ Dakar');expect(byId('gen-questions').querySelector('b')).toBeNull();
 expect(byId('gen-checks').textContent).toBe('⚠️ new : alias « Dante » = premier mot');expect(byId('gen-report').textContent).toBe('Compte rendu');expect(byId('gen-apply').disabled).toBe(false);
 const calls=fetch.mock.calls.length;await vi.advanceTimersByTimeAsync(1000);expect(fetch.mock.calls.slice(calls).some(([path])=>path==='/api/generation')).toBe(false);
 await click('gen-apply');expect(confirm).toHaveBeenCalledWith(expect.stringContaining('les 1 questions de la banque par ces 2 nouvelles'));expect(posted('generation/apply')).toHaveLength(0);
 confirm.mockReturnValue(true);await click('gen-apply');expect(toasts()).toContain('Banque remplacée');expect(byId('gen-status').textContent).toContain('Sauvegarde : questions.before-merge-1.json');
 expect(byId('gen-apply').disabled).toBe(true);expect(byId('bank-count').textContent).toBe('1');expect(byId('tab-questions').querySelector('.dot').hidden).toBe(true);
 await click('generate');generation={...generation,status:'done',started:1,finished:1,cost_usd:null,applied:null,batch:{questions:[{id:'x',question:'Seule ?',answer:'Oui'}],errors:['Le lot n’a pas été écrit'],warnings:[]}};
 await vi.advanceTimersByTimeAsync(1000);expect(byId('gen-checks').textContent).toBe('❌ Le lot n’a pas été écrit');expect(byId('gen-apply').disabled).toBe(true);expect(byId('gen-total').textContent).toBe('1 question');
 await click('generate');generation={...generation,status:'failed',error:'GENERATION_FAILED: Claude n’a pas terminé',batch:null};await vi.advanceTimersByTimeAsync(1000);
 expect(byId('gen-status').className).toContain('error');expect(toasts()).toContain('La génération a échoué');
 await click('generate');await click('generate-cancel');expect(byId('gen-status').textContent).toContain('annulée');expect(byId('generate').hidden).toBe(false);
 failures.push({path:'/api/generation',status:409,body:{error:'GENERATION_ACTIVE',message:'Une génération est déjà en cours'}});await click('generate');expect(byId('gen-error').textContent).toContain('Génération déjà en cours');
});
it('tunes correction criteria, tests answers and edits the JSON bank',async()=>{
 bank=[question,{id:'legacy',question:'Ancienne ?',answer:'Harry Potter',grading_mode:'person_name'}];
 URL.createObjectURL=vi.fn(()=>'blob:fake');URL.revokeObjectURL=vi.fn();const anchor=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 await load();
 expect(byId('bank-count').textContent).toBe('2');expect(byId('bank-list').textContent).toContain('✅ Harry Potter');expect(byId('criteria-true').value).toBe('Paris');
 byId('bank-list').querySelectorAll('button')[1].click();await settle();
 expect(byId('question').value).toBe('legacy');expect(byId('criteria-true').value).toBe('Harry Potter');expect(byId('criteria-false').value).toBe('');expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
 byId('criteria-false').value='Tout autre personnage';byId('aliases').value=' Potter \n\n';await click('save-correction');
 expect(bank[1]).toEqual({id:'legacy',question:'Ancienne ?',criteria:{true:'Harry Potter',false:'Tout autre personnage'},aliases:['Potter']});expect(toasts()).toContain('Critères enregistrés');
 byId('candidate').value='Paris';await click('check');expect(byId('verdict').className).toBe('verdict ok');expect(byId('verdict').textContent).toContain('Référence reconnue : « Paris »');
 accepted=false;byId('criteria-true').value='Macky Sall';await click('check');expect(lastBody('test-answer').question.criteria.true).toBe('Macky Sall');expect(byId('verdict').textContent).toMatch(/^❌ Réponse refusée/);
 byId('question').value='capital';byId('question').dispatchEvent(new Event('change'));expect(byId('verdict').hidden).toBe(true);expect(byId('criteria-true').value).toBe('Paris');
 byId('bank').value='{';await click('save');expect(byId('bank-error').textContent).toContain('JSON invalide');
 byId('bank').value='[]';await click('save');expect(toasts()).toContain('0 questions');expect(byId('empty-bank').hidden).toBe(false);
 await click('check');expect(byId('tester-error').textContent).toContain('Choisissez d’abord');
 const pick=files=>{Object.defineProperty(byId('import'),'files',{value:files,configurable:true});byId('import').dispatchEvent(new Event('change'));return settle();};
 await pick([{text:async()=>JSON.stringify([question])}]);expect(byId('bank').value).toContain(question.question);expect(toasts()).toContain('Fichier importé');
 await pick([{text:async()=>'{}'}]);expect(byId('bank-error').textContent).toContain('Fichier JSON invalide');
 await pick([]);await click('export');expect(anchor).toHaveBeenCalled();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');
});
it('tracks unsaved settings and offers validated games only when the transport is validated',async()=>{
 capabilities={native_ready:true};await load();
 expect(byId('save-bar').hidden).toBe(true);expect(byId('native-text').textContent).toContain('validé');expect(byId('settings-groups').querySelectorAll('.card')).toHaveLength(4);
 byId('setting-question_seconds').value='45';byId('config').dispatchEvent(new Event('input'));
 expect(byId('save-bar').hidden).toBe(false);expect(byId('tab-reglages').querySelector('.dot').hidden).toBe(false);expect(byId('start-summary').textContent).toContain('45 s par question · inscriptions');
 expect(byId('start-summary').textContent).toContain('non enregistrés');
 await click('reset-settings');expect(byId('setting-question_seconds').value).toBe(String(defaults.question_seconds));expect(byId('save-bar').hidden).toBe(true);
 byId('setting-ignore_accents').checked=false;byId('config').dispatchEvent(new Event('input'));await click('save-settings');
 expect(lastBody('settings').ignore_accents).toBe(false);expect(toasts()).toContain('Réglages enregistrés');expect(byId('save-bar').hidden).toBe(true);
 byId('modes').querySelector('[value="native"]').checked=true;await click('start');expect(lastBody('start')).toMatchObject({mode:'native',rehearsal:false});
});
it('falls back from validated games when the transport is not validated, and never overlaps polls',async()=>{
 await load();const native=byId('modes').querySelector('[value="native"]');native.disabled=false;native.checked=true;
 byId('config').dispatchEvent(new Event('input'));expect(byId('modes').querySelector('[value="rehearsal"]').checked).toBe(true);
 const original=fetch;let release;
 vi.stubGlobal('fetch',vi.fn((path,options)=>path==='/api/session'?new Promise(resolve=>{release=()=>resolve(response({}));}):original(path,options)));
 await vi.advanceTimersByTimeAsync(3000);expect(fetch.mock.calls.filter(([path])=>path==='/api/session')).toHaveLength(1);
 release();await settle();
});
