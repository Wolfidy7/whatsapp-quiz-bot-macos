/** Settings grouped by purpose: [key, label, type, min, max, hint]; the last group is the advanced one. */
export const groups = [
 {title:'👥 Joueurs', fields:[
  ['whatsapp_group','Groupe WhatsApp','text',null,null,'Nom exact de la conversation.'],
  ['nb_players_expected','Minimum de joueurs','number',1,1000,'En dessous, la partie est annulée.'],
  ['max_players','Maximum de joueurs','number',1,1000,'Les inscriptions suivantes sont ignorées.']]},
 {title:'⏱️ Rythme', fields:[
  ['registration_seconds','Durée des inscriptions','number',1,3600,'En secondes.'],
  ['question_seconds','Temps par question','number',1,3600,'En secondes, avant le STOP.'],
  ['interval_seconds','Pause entre les questions','number',0,3600,'En secondes, après les résultats.']]},
 {title:'🏆 Points', fields:[
  ['max_points','Points du plus rapide','number',1,100000,'Pour la première bonne réponse.'],
  ['min_points','Points du plus lent','number',1,100000,'Pour la dernière bonne réponse.']]},
 {title:'🧠 Correction', fields:[
  ['jev_threshold','Seuil de confiance jev','number',0,1,'Entre 0 et 1 : au-dessus, la réponse est acceptée.'],
  ['ignore_accents','Accepter les réponses sans accents','checkbox']]},
 {title:'🔧 Avancé', advanced:true, fields:[
  ['join_command','Commande d’inscription','text',null,null,'Par exemple !join.'],
  ['answer_prefix','Préfixe des réponses','text',null,null,'Par exemple !r.'],
  ['poll_seconds','Lecture des messages','number',0.1,30,'Intervalle en secondes.'],
  ['message_chunk_size','Longueur maximale d’un message','number',200,4000,'En caractères.'],
  ['max_history_pages','Limite du diagnostic','number',1,10000,'Pages lues par l’ancien lecteur.'],
  ['port','Port du serveur','number',1024,65535,'Pris en compte au redémarrage.'],
  ['jev_model','Modèle jev','text',null,null,''],
  ['whatsapp_database','Base de messages WhatsApp','text',null,null,'Fichier local, lu sans modification.']]},
];
const fields=groups.flatMap(group=>group.fields);
/** Create one labeled, typed field from its definition and current value. */
function settingField([key,title,type,min,max,hint],value) {
 const box=document.createElement('div');box.className=`field${type==='checkbox'?' check':''}${['whatsapp_group','whatsapp_database'].includes(key)?' wide':''}`;
 const input=document.createElement('input');input.id=`setting-${key}`;input.name=key;input.type=type;
 if(type==='checkbox')input.checked=value;else{input.value=value;input.required=true;}
 if(min!==undefined&&min!==null){input.min=min;input.max=max;input.step=['poll_seconds','jev_threshold'].includes(key)?'any':'1';input.inputMode='decimal';}
 const label=document.createElement('label');label.htmlFor=input.id;label.textContent=title;
 box.append(...(type==='checkbox'?[input,label]:[label,input]));
 if(hint){const small=document.createElement('small');small.textContent=hint;box.append(small);}
 return box;
}
/** Build every settings card once; polling never overwrites an operator’s edits. */
export function renderSettings(settings) {
 const cards=byGroup=>byGroup.map(group=>{
  const card=document.createElement('div');card.className='card';
  const title=document.createElement('h2');const [emoji,...words]=group.title.split(' ');const badge=document.createElement('span');badge.className='emoji';badge.textContent=emoji;title.append(badge,words.join(' '));
  const grid=document.createElement('div');grid.className='form-grid';grid.append(...group.fields.map(field=>settingField(field,settings[field[0]])));
  card.append(title,grid);return card;
 });
 document.getElementById('settings-groups').replaceChildren(...cards(groups.filter(group=>!group.advanced)));
 const advanced=groups.find(group=>group.advanced);
 document.getElementById('advanced-settings').replaceChildren(...advanced.fields.map(field=>settingField(field,settings[field[0]])));
}
/** Collect typed form values for backend validation and the immutable game snapshot. */
export function readSettings() {
 return Object.fromEntries(fields.map(([key,,type])=>{
  const input=document.getElementById(`setting-${key}`);
  const value=type==='checkbox'?input.checked:type==='number'?Number(input.value):input.value;
  return [key,value];
 }));
}
/** Tell whether the form differs from the saved settings. */
export function settingsChanged(saved) {
 const current=readSettings();
 return fields.some(([key])=>current[key]!==saved[key]);
}
