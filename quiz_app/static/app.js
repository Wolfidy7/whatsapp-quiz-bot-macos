import {summary,remaining,parseBank,label,withCorrection} from './core.js';
import {renderSettings,readSettings} from './fields.js';
/** Locate a named dashboard element. */
const byId=id=>document.getElementById(id);
let latest={},starting=false,polling=false,ready=false;
const phases={registration:'INSCRIPTIONS',answering:'QUESTION EN COURS',interval:'ENTRE LES QUESTIONS',finished:'TERMINÉ',paused:'EN PAUSE',cancelled:'ARRÊTÉ'};
/** Execute one same-origin JSON request and expose classified server failures. */
async function api(path,method='GET',body) {
 const response=await fetch(`/api/${path}`,{method,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const value=await response.json();
 if(!response.ok)throw new Error(value.message||JSON.stringify(value.detail||value.error));
 return value;
}
/** Surface an action failure without clearing a persistent incident during background polling. */
async function action(work) {try{await work();}catch(error){byId('notice').textContent=error.message;}}
/** Build one safe question checkbox. */
function questionOption(question) {
 const row=document.createElement('label');row.className='question-option';
 const input=document.createElement('input');input.type='checkbox';input.value=question.id;input.checked=true;
 const text=document.createElement('span');text.textContent=question.question;row.append(input,text);return row;
}
/** Refresh bank controls after explicit edits, without touching game configuration. */
function renderBank(values) {
 const selected=byId('question').value;
 byId('bank').value=JSON.stringify(values,null,2);
 byId('question-list').replaceChildren(...values.map(questionOption));
 byId('question').replaceChildren(...values.map(question=>{const option=document.createElement('option');option.value=question.id;option.textContent=question.question;return option;}));
 if(values.some(question=>question.id===selected))byId('question').value=selected;
 renderCorrection();
}
/** Read the selected question from the JSON draft, refusing stale selections. */
function selectedQuestion() {
 const question=parseBank(byId('bank').value).find(item=>item.id===byId('question').value);
 if(!question)throw new Error('Sélectionnez une question présente dans le brouillon JSON.');
 return question;
}
/** Show unit controls only for numerical correction. */
function showUnits(){byId('numeric-options').hidden=byId('grading-mode').value!=='number';}
/** Load correction fields for the selected draft without saving or altering a running game. */
function renderCorrection() {
 const question=selectedQuestion();byId('grading-mode').value=question.grading_mode||'exact';
 byId('units').value=(question.units||[]).join('\n');byId('require-unit').checked=Boolean(question.require_unit);showUnits();
}
/** Build the current tester question from unsaved JSON and correction controls. */
function correctionDraft(){return withCorrection(selectedQuestion(),byId('grading-mode').value,byId('units').value,byId('require-unit').checked);}
/** Render names using text nodes so participant-controlled labels cannot inject HTML. */
function renderParticipants(session) {
 const names=(session.players||[]).map(key=>label(session,key));
 const rows=names.map(name=>{const item=document.createElement('li');item.textContent=name;return item;});
 byId('participants').replaceChildren(...rows);
 if(!rows.length){const item=document.createElement('li');item.className='muted';item.textContent='En attente des inscriptions.';byId('participants').append(item);}
}
/** Create a safe score row with response status and accumulated points. */
function rankingRow(row) {
 const item=document.createElement('div');item.className='ranking-row';
 const rank=document.createElement('span');rank.textContent=({1:'🥇',2:'🥈',3:'🥉'})[row.rank]||`${row.rank}.`;
 const player=document.createElement('div');const name=document.createElement('div');name.className='player-name';name.textContent=row.name;
 const status=document.createElement('div');status.className='response';status.textContent=row.answered?`Réponse reçue · ${row.round_points} pts sur cette question`:'En attente d’une réponse';player.append(name,status);
 const points=document.createElement('span');points.className='points';points.textContent=`${row.points} pts`;
 item.append(rank,player,points);return item;
}
/** Display provisional ranks without presenting an open collection as final. */
function renderRanking(session) {
 const live=session.live||{ranking:[],provisional:false};
 byId('ranking-status').textContent=live.provisional?'PROVISOIRE':session.id?'CONFIRMÉ':'EN ATTENTE';
 byId('ranking-help').textContent=live.provisional?'Les points de la question en cours restent provisoires jusqu’à STOP et à la vérification complète des réponses.':'Les points confirmés se cumulent à chaque question.';
 byId('ranking').replaceChildren(...live.ranking.map(rankingRow));
 if(!live.ranking.length)byId('ranking').textContent='Le classement apparaîtra après les premières inscriptions.';
}
/** Keep Stop reachable during slow native startup and prevent duplicate Start requests. */
function controls() {
 const active=starting||(latest.id&&!['finished','cancelled'].includes(latest.phase));
 byId('start').disabled=!ready||Boolean(active);byId('cancel').disabled=!active;byId('stop-now').disabled=!active;
 byId('config-fields').disabled=Boolean(active);byId('mode').disabled=Boolean(active);
 byId('simulation-tools').hidden=latest.mode!=='simulation';
}
/** Render a fresh snapshot while retaining unsaved form values and editor contents. */
function renderSession(session) {
 if(session.stop_requested&&!session.phase){byId('notice').textContent='Arrêt demandé. La partie s’arrête dès la fin de l’action en cours.';return;}
 latest=session;byId('phase').textContent=phases[session.phase]||(starting?'DÉMARRAGE':'PRÊT');
 byId('players').textContent=session.players?.length||0;byId('round').textContent=session.rounds?.length||'—';
 byId('remaining').textContent=remaining(session);byId('results').textContent=summary(session);
 byId('pending').textContent=(session.outbox||[]).filter(item=>item.status==='pending').map(item=>item.text).join('\n\n')||'Aucun.';
 byId('prompt').textContent=session.rounds?.at(-1)?.question.question||'Les joueurs s’inscrivent avec la commande configurée.';
 if(session.error)byId('notice').textContent=session.error;
 renderParticipants(session);renderRanking(session);controls();
}
/** Start one selected real rehearsal, validated native game or no-send simulation. */
async function start() {
 if(!byId('config').reportValidity())return;
 const mode=byId('mode').value;const ids=[...byId('question-list').querySelectorAll('input:checked')].map(input=>input.value);
 if(!ids.length)throw new Error('Sélectionnez au moins une question.');
 starting=true;controls();byId('notice').textContent='Démarrage de la partie…';
 try{renderSession(await api('start','POST',{mode:mode==='simulation'?'simulation':'native',rehearsal:mode==='rehearsal',settings:readSettings(),question_ids:ids}));byId('notice').textContent=latest.error||(latest.phase==='cancelled'?'Partie arrêtée.':'Partie démarrée.');}
 finally{starting=false;controls();}
}
/** Bind one local action to a guarded button. */
function bind(id,work){byId(id).addEventListener('click',()=>action(work));}
bind('start',start);
/** Request immediate cooperative cancellation from either visible Stop control. */
async function stop(){byId('notice').textContent='Arrêt demandé…';renderSession(await api('cancel','POST'));}
bind('cancel',stop);bind('stop-now',stop);
bind('save-settings',async()=>{if(!byId('config').reportValidity())return;await api('settings','PUT',readSettings());byId('settings-status').textContent='Paramètres enregistrés.';});
bind('save',async()=>renderBank(await api('questions','PUT',parseBank(byId('bank').value))));
bind('apply-correction',async()=>{const question=correctionDraft();byId('bank').value=JSON.stringify(parseBank(byId('bank').value).map(item=>item.id===question.id?question:item),null,2);byId('verdict').textContent='Mode appliqué au brouillon. Enregistrez les questions pour les prochaines parties.';});
bind('check',async()=>{const result=await api('test-answer','POST',{question:correctionDraft(),answer:byId('candidate').value,ignore_accents:byId('setting-ignore_accents').checked});byId('verdict').textContent=(result.accepted?`Acceptée · référence « ${result.alias} ». `:'Refusée · ')+result.reason;});
byId('question').addEventListener('change',()=>action(async()=>renderCorrection()));
byId('bank').addEventListener('change',()=>action(async()=>renderCorrection()));
byId('grading-mode').addEventListener('change',showUnits);
bind('resume',async()=>renderSession(await api('resume','POST')));
bind('inject',async()=>renderSession(await api('inject','POST',{author:byId('author').value,body:byId('reply').value})));
bind('recover',async()=>renderSession(await api(`recover/${encodeURIComponent(byId('archive').value)}`,'POST')));
bind('export',async()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(await api('questions'),null,2)],{type:'application/json'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='questions.json';anchor.click();URL.revokeObjectURL(url);});
byId('import').addEventListener('change',()=>action(async()=>{const file=byId('import').files[0];if(file)byId('bank').value=JSON.stringify(parseBank(await file.text()),null,2);}));
byId('mode').addEventListener('change',()=>{byId('mode-help').textContent=byId('mode').value==='simulation'?'Simulation locale : aucun message n’est envoyé dans WhatsApp.':'Les annonces seront envoyées dans le groupe WhatsApp configuré.';});
await action(async()=>{renderSettings(await api('settings'));renderBank(await api('questions'));ready=true;renderSession(await api('session'));byId('notice').textContent=latest.error||'';});
/** Poll snapshots without overlapping requests or erasing user edits. */
async function refresh(){if(polling)return;polling=true;try{await action(async()=>renderSession(await api('session')));}finally{polling=false;}}
setInterval(refresh,1000);
