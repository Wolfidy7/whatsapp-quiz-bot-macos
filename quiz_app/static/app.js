import {label,isActive,countdown,phaseInfo,modeLabel,historyRows,parseBank,withCorrection,startSummary,apiError,explainError} from './core.js';
import {renderSettings,readSettings,settingsChanged} from './fields.js';
import {renderGeneration,readGeneration} from './generation.js';
import {byId,el,toast,showError,alertBox,setupTabs,markTab,confetti} from './ui.js';
const app={session:{},generation:{},bank:[],saved:{},unchecked:new Set(),nativeReady:false,ready:false,starting:false,polling:false,setup:false,dirty:false};
let selectTab;
/** Execute one same-origin JSON request; failures carry the server's error code. */
async function api(path,method='GET',body) {
 const response=await fetch(`/api/${path}`,{method,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const value=await response.json().catch(()=>({}));
 if(!response.ok)throw apiError(response.status,value);
 return value;
}
/** Build a form error that tells the operator what to fix. */
const missing=message=>Object.assign(new Error(message),{code:'INPUT'});
/** Run one user action, explaining a failure in a toast and next to the control that triggered it. */
async function act(work,inline) {try{if(inline)inline.hidden=true;await work();}catch(error){showError(error,inline);}}
/** Bind a button to a guarded action with an optional inline error area. */
function bind(id,work,inline){byId(id).addEventListener('click',()=>act(work,inline&&byId(inline)));}

/** Ids of the questions ticked for the next game, in bank order. */
const selectedIds=()=>app.bank.filter(question=>!app.unchecked.has(question.id)).map(question=>question.id);
/** Expected answer of a question, including a legacy answer field. */
const answerOf=question=>question.criteria?.true??question.answer??'';
/** Build one selectable question row for the next game. */
function pickRow(question) {
 const row=el('label','pick');const input=el('input');input.type='checkbox';input.value=question.id;input.checked=!app.unchecked.has(question.id);
 input.addEventListener('change',()=>{if(input.checked)app.unchecked.delete(question.id);else app.unchecked.add(question.id);updateSetup();});
 const text=el('span','',question.question);text.append(el('small','',`✅ ${answerOf(question)}`));row.append(input,text);return row;
}
/** Build one bank row with a shortcut to its correction settings. */
function bankRow(question) {
 const row=el('li');const tune=el('button','btn ghost small','🎯');tune.title='Régler la correction';tune.setAttribute('aria-label',`Régler la correction : ${question.question}`);
 tune.addEventListener('click',()=>{byId('question').value=question.id;renderCorrection();byId('tester').scrollIntoView({behavior:'smooth'});});
 row.append(el('span','q',question.question),el('span','a',`✅ ${answerOf(question)}`),tune);return row;
}
/** Refresh every view of the bank after a save, an import or a generated replacement. */
function renderBank(values) {
 app.bank=values;
 byId('bank').value=JSON.stringify(values,null,2);byId('bank-count').textContent=values.length;
 byId('bank-list').replaceChildren(...values.map(bankRow));byId('question-list').replaceChildren(...values.map(pickRow));
 byId('empty-bank').hidden=values.length>0;
 const selected=byId('question').value;
 byId('question').replaceChildren(...values.map(question=>{const option=el('option','',question.question);option.value=question.id;return option;}));
 if(values.some(question=>question.id===selected))byId('question').value=selected;
 renderCorrection();updateSetup();
}
/** The saved question chosen in the correction panel. */
function selectedQuestion() {
 const question=app.bank.find(item=>item.id===byId('question').value);
 if(!question)throw missing('Choisissez d’abord une question de la banque.');
 return question;
}
/** Load the selected question's criteria and aliases into the correction panel. */
function renderCorrection() {
 const question=app.bank.find(item=>item.id===byId('question').value)||{};
 byId('criteria-true').value=answerOf(question);byId('criteria-false').value=question.criteria?.false??'';byId('aliases').value=(question.aliases||[]).join('\n');
 byId('verdict').hidden=true;
}
/** The selected question with the criteria currently typed in the panel, saved or not. */
const correctionDraft=()=>withCorrection(selectedQuestion(),byId('criteria-true').value,byId('criteria-false').value,byId('aliases').value);

/** Update the game setup card: mode availability, selection count and what Start will use. */
function updateSetup() {
 if(!app.ready)return;
 const settings=readSettings();const count=selectedIds().length;
 for(const name of document.querySelectorAll('.group-name'))name.textContent=`« ${settings.whatsapp_group} »`;
 const native=document.querySelector('input[name="mode"][value="native"]');native.disabled=!app.nativeReady;
 if(native.disabled&&native.checked)document.querySelector('input[name="mode"][value="rehearsal"]').checked=true;
 byId('native-text').textContent=app.nativeReady?'Publie dans le groupe : le transport contrôlé est validé.':'Indisponible tant que le test de transport contrôlé n’a pas été réussi.';
 byId('selection-count').textContent=`${count} sur ${app.bank.length} question${app.bank.length>1?'s':''} sélectionnée${count>1?'s':''}`;
 byId('start-summary').textContent=startSummary(count,settings,app.dirty);
 byId('start').disabled=!count||app.starting||isActive(app.session);
 byId('start').textContent=app.starting?'⏳ Démarrage…':'🚀 Lancer la partie';
}
/** Track unsaved settings and show the save bar. */
function updateDirty() {
 app.dirty=settingsChanged(app.saved);byId('save-bar').hidden=!app.dirty;markTab('reglages',app.dirty);updateSetup();
}

/** Render the participant chips with text nodes so player names cannot inject HTML. */
function renderParticipants(session) {
 const rows=(session.players||[]).map(key=>el('li','',label(session,key)));
 byId('participants').replaceChildren(...(rows.length?rows:[el('li','muted','En attente des inscriptions…')]));
}
/** Build one ranking row with a medal, the answer status and the accumulated points. */
function rankingRow(row) {
 const item=el('div',`rank-row rank-${row.rank}`);
 const player=el('div');player.append(el('div','name',row.name),el('div','state',row.answered?`Réponse reçue · ${row.round_points} pts sur cette question`:'En attente d’une réponse'));
 item.append(el('span','medal',({1:'🥇',2:'🥈',3:'🥉'})[row.rank]||String(row.rank)),player,el('span','points',`${row.points} pts`));
 return item;
}
/** Render the ranking, flagged as provisional while answers are still being collected. */
function renderRanking(session) {
 const live=session.live||{ranking:[],provisional:false};const started=(session.rounds||[]).length>0;
 const tag=byId('ranking-status');tag.hidden=!started;tag.textContent=live.provisional?'Provisoire':'Confirmé';tag.className=`tag${live.provisional?' provisional':''}`;
 byId('ranking').replaceChildren(...(started?live.ranking.map(rankingRow):[el('p','hint','Le classement apparaîtra après la première question.')]));
}
/** Explain a session incident and, when the game is paused, offer to verify and resume. */
function renderIncident(session) {
 const box=byId('incident');box.hidden=!session.error;
 if(!session.error)return;
 const {title,hint,detail}=explainError(session.error);
 const alert=alertBox('error',`🚨 ${title}`,hint,detail);
 const pending=(session.outbox||[]).filter(item=>item.status==='pending').map(item=>item.text);
 if(pending.length)alert.append(el('p','','Messages dont l’envoi n’est pas confirmé :'),el('pre','',pending.join('\n\n')));
 if(session.phase==='paused'){
  const resume=el('button','btn primary small','🔎 Vérifier et reprendre');
  resume.addEventListener('click',()=>act(async()=>{renderSession(await api('resume','POST'));toast('success','Partie reprise','Tous les envois ont été retrouvés dans le groupe.');}));
  alert.append(resume);
 }
 box.replaceChildren(alert);
}
/** Render the live game card: phase banner, countdown, current question, players and ranking. */
function renderLive(session) {
 const info=phaseInfo(session.phase);const total=(session.questions||[]).length;const round=(session.rounds||[]).length;
 byId('live-banner').className=`banner tone-${info.tone}`;byId('live-emoji').textContent=info.emoji;byId('live-title').textContent=info.label;
 byId('live-subtitle').textContent=info.text;
 const timer=countdown(session);byId('countdown').hidden=!timer;
 if(timer){byId('countdown').style.setProperty('--ratio',timer.ratio);byId('remaining').textContent=`${timer.seconds}s`;}
 renderIncident(session);
 byId('players').textContent=`${(session.players||[]).length} / ${session.settings?.max_players??'—'}`;
 byId('round').textContent=`${round||'—'} / ${total}`;byId('live-mode').textContent=modeLabel(session);
 const current=(session.rounds||[])[round-1];const asking=['answering','interval'].includes(session.phase)&&current;
 byId('prompt').hidden=!asking;if(asking)byId('prompt').textContent=`❓ ${current.question.question}`;
 renderParticipants(session);renderRanking(session);
 byId('simulation-tools').hidden=session.mode!=='simulation'||!isActive(session);
 byId('new-game').hidden=isActive(session);
}
/** Render the history tab from the last loaded game. */
function renderHistory(session) {
 const box=byId('history');
 if(!session.id){box.replaceChildren(el('p','hint','Aucune partie pour le moment.'));return;}
 const info=phaseInfo(session.phase);
 const head=el('p','',`${info.emoji} ${info.label} · ${modeLabel(session)} · identifiant `);head.append(el('code','',session.id));
 const rounds=historyRows(session).map(row=>{
  const card=el('div','history-round');const list=el('ul');list.append(...row.answers.map(answer=>el('li','',answer)));
  card.append(el('h4','',row.title),row.answers.length?list:el('p','hint','Aucune réponse.'));return card;
 });
 box.replaceChildren(head,...(rounds.length?rounds:[el('p','hint','Aucune question jouée.')]));
}
/** Render the header, the play tab and the history from the current snapshot. */
function render() {
 const session=app.session;const active=isActive(session);
 const info=phaseInfo(session.id?session.phase:'');
 byId('phase').textContent=app.starting&&!active?'Démarrage…':info.label;byId('phase').className=`pill tone-${info.tone}`;
 byId('stop-now').hidden=!active&&!app.starting;markTab('jouer',active);
 const live=active||(Boolean(session.id)&&!app.setup);
 byId('setup').hidden=live;byId('live').hidden=!live;
 if(live)renderLive(session);
 updateSetup();renderHistory(session);
}
/** Announce game transitions observed between two snapshots of the same game. */
function announce(before,after) {
 if(before.id!==after.id||before.phase===after.phase)return;
 if(after.phase==='answering'&&before.phase==='registration')toast('info','Inscriptions closes',`${(after.players||[]).length} joueur(s) inscrit(s). Première question envoyée !`);
 if(after.phase==='finished'){const winner=after.live?.ranking?.[0];confetti();toast('success','Partie terminée 🏁',winner?`Bravo à ${winner.name}, ${winner.points} pts !`:'Merci à tous les joueurs.');}
 if(after.phase==='cancelled')toast('warning','Partie arrêtée','Aucune autre question ne sera envoyée.');
 if(after.phase==='paused'&&after.error)showError(after.error);
}
/** Store a fresh snapshot, announce what changed and re-render. */
function renderSession(session) {
 if(session.stop_requested&&!session.phase){toast('info','Arrêt demandé','La partie s’arrête dès la fin de l’action en cours sur le Mac.');return;}
 const before=app.session;app.session=session;announce(before,session);render();
}
/** Start a simulation, a WhatsApp rehearsal or a validated game with the selected questions. */
async function start() {
 if(!byId('config').checkValidity())throw missing('Certains réglages sont invalides : corrigez-les dans l’onglet Réglages.');
 const ids=selectedIds();
 const mode=document.querySelector('input[name="mode"]:checked').value;
 app.starting=true;render();
 if(mode!=='simulation')toast('info','Ouverture de WhatsApp…','Le Mac recherche le groupe puis publie les inscriptions.');
 try{
  const session=await api('start','POST',{mode:mode==='simulation'?'simulation':'native',rehearsal:mode==='rehearsal',settings:readSettings(),question_ids:ids});
  app.setup=false;renderSession(session);
  if(session.phase==='registration'&&!session.error)toast('success','C’est parti ! 🚀','Les inscriptions sont ouvertes.');
 }finally{app.starting=false;render();}
}
/** Store the generation state, flag the Questions tab and announce its outcome. */
function setGeneration(state) {
 const before=app.generation.status;app.generation=state;renderGeneration(state);
 markTab('questions',state.status==='running'||(state.status==='done'&&!state.applied));
 if(before!=='running')return;
 if(state.status==='done')toast('success','Lot prêt ! 🎉','Vérifiez les questions, puis remplacez la banque.');
 if(state.status==='failed')showError({code:'GENERATION_FAILED',message:state.error});
}

bind('start',start,'start-error');
bind('stop-now',async()=>renderSession(await api('cancel','POST')));
bind('new-game',async()=>{app.setup=true;render();window.scrollTo(0,0);});
bind('select-all',async()=>{app.unchecked.clear();renderBank(app.bank);});
bind('select-none',async()=>{for(const question of app.bank)app.unchecked.add(question.id);renderBank(app.bank);});
bind('inject',async()=>renderSession(await api('inject','POST',{author:byId('author').value,body:byId('reply').value})));
bind('generate',async()=>{
 if(!byId('gen-form').checkValidity())throw missing('Indiquez des thèmes et un nombre de questions entre 1 et 200.');
 const request=readGeneration();setGeneration(await api('generation','POST',request));
 toast('info','Claude est au travail ✨',`${request.count} questions · ${request.themes}. Comptez quelques minutes.`);
},'gen-error');
bind('generate-cancel',async()=>setGeneration(await api('generation/cancel','POST')),'gen-error');
bind('gen-apply',async()=>{
 const total=app.generation.batch.questions.length;
 if(!confirm(`Remplacer les ${app.bank.length} questions de la banque par ces ${total} nouvelles questions ? L’ancienne banque sera sauvegardée.`))return;
 setGeneration(await api('generation/apply','POST'));renderBank(await api('questions'));
 toast('success','Banque remplacée 🔁',`${total} questions prêtes à jouer. Sauvegarde : ${app.generation.applied}.`);
},'gen-error');
bind('save-correction',async()=>{
 const question=correctionDraft();
 renderBank(await api('questions','PUT',app.bank.map(item=>item.id===question.id?question:item)));
 toast('success','Critères enregistrés 💾','Ils s’appliquent aux prochaines parties.');
},'tester-error');
bind('check',async()=>{
 const {ignore_accents,jev_threshold,jev_model}=readSettings();const verdict=byId('verdict');
 verdict.hidden=false;verdict.className='verdict';verdict.replaceChildren(el('span','','⏳ jev évalue la réponse…'));
 const result=await api('test-answer','POST',{question:correctionDraft(),answer:byId('candidate').value,ignore_accents,jev_threshold,jev_model});
 const reference=result.alias?`Référence reconnue : « ${result.alias} ». `:'';
 verdict.className=`verdict ${result.accepted?'ok':'ko'}`;
 verdict.replaceChildren(el('strong','',result.accepted?'✅ Réponse acceptée':'❌ Réponse refusée'),el('span','',`${reference}${result.reason}`));
},'tester-error');
bind('save',async()=>{
 let values;try{values=parseBank(byId('bank').value);}catch(error){throw missing(`JSON invalide : ${error.message}`);}
 renderBank(await api('questions','PUT',values));toast('success','Banque enregistrée 📚',`${values.length} questions.`);
},'bank-error');
bind('export',async()=>{
 const url=URL.createObjectURL(new Blob([JSON.stringify(await api('questions'),null,2)],{type:'application/json'}));
 const anchor=document.createElement('a');anchor.href=url;anchor.download='questions.json';anchor.click();URL.revokeObjectURL(url);
},'bank-error');
byId('import').addEventListener('change',()=>act(async()=>{
 const file=byId('import').files[0];if(!file)return;
 let values;try{values=parseBank(await file.text());}catch(error){throw missing(`Fichier JSON invalide : ${error.message}`);}
 byId('bank').value=JSON.stringify(values,null,2);toast('info','Fichier importé',`${values.length} questions dans l’éditeur. Cliquez sur Enregistrer pour les appliquer.`);
},byId('bank-error')));
bind('save-settings',async()=>{
 if(!byId('config').checkValidity())throw missing('Certains champs sont vides ou hors limites.');
 app.saved=await api('settings','PUT',readSettings());updateDirty();toast('success','Réglages enregistrés ✅','Ils s’appliquent à la prochaine partie.');
},'settings-error');
bind('reset-settings',async()=>{renderSettings(app.saved);updateDirty();});
bind('recover',async()=>{
 const id=byId('archive').value.trim();if(!id)throw missing('Collez l’identifiant de la partie à rouvrir.');
 app.setup=false;renderSession(await api(`recover/${encodeURIComponent(id)}`,'POST'));selectTab('jouer');
 toast('info','Archive ouverte','La partie est en pause : vérifiez-la, puis reprenez-la ou arrêtez-la.');
},'archive-error');
byId('question').addEventListener('change',renderCorrection);
byId('config').addEventListener('input',updateDirty);

/** Poll the game, and the generation while it runs, without overlapping requests. */
async function refresh() {
 if(app.polling)return;app.polling=true;
 try{await act(async()=>{renderSession(await api('session'));if(app.generation.status==='running')setGeneration(await api('generation'));});}
 finally{app.polling=false;}
}
/** Load settings, bank, game and generation, then start polling. */
async function init() {
 selectTab=setupTabs();
 const [settings,bank,session,capabilities,generation]=await Promise.all(['settings','questions','session','capabilities','generation'].map(path=>api(path)));
 app.saved=settings;renderSettings(settings);app.nativeReady=capabilities.native_ready;app.ready=true;
 renderBank(bank);app.session=session;render();setGeneration(generation);
 setInterval(refresh,1000);
}
init().catch(error=>showError(error)).finally(()=>{window.quizReady=true;});
