/** Labels and input boundaries for every local operational setting. */
export const fields = [
 ['whatsapp_group','Groupe WhatsApp','text',null,null,'wide'],
 ['nb_players_expected','Minimum de joueurs','number',1,1000],['max_players','Maximum de joueurs','number',1,1000],
 ['max_questions','Nombre de questions','number',1,1000],['registration_seconds','Inscriptions (secondes)','number',1,3600],
 ['question_seconds','Temps par question (secondes)','number',1,3600],['interval_seconds','Pause entre questions (secondes)','number',0,3600],
 ['max_points','Premier : points maximum','number',1,100000],['min_points','Dernier : points minimum','number',1,100000],
 ['ignore_accents','Accepter les réponses sans accents','checkbox'],
 ['join_command','Commande d’inscription','text',null,null,'advanced'],['answer_prefix','Préfixe des réponses','text',null,null,'advanced'],
 ['poll_seconds','Lecture des réponses (secondes)','number',0.1,30,'advanced'],
 ['message_chunk_size','Longueur maximale des messages','number',200,4000,'advanced'],
 ['max_history_pages','Limite de lecture du diagnostic','number',1,10000,'advanced'],
 ['port','Port du serveur local','number',1024,65535,'advanced'],
 ['whatsapp_database','Fichier local de WhatsApp','text',null,null,'advanced']
];
/** Create one typed input from its definition and current local value. */
function settingInput(key,type,min,max,value) {
 const input=document.createElement('input');input.id=`setting-${key}`;input.name=key;input.type=type;
 if(type==='checkbox')input.checked=value;else{input.value=value;input.required=true;}
 if(min!==undefined&&min!==null){input.min=min;input.max=max;input.step=key==='poll_seconds'?'any':'1';}
 return input;
}
/** Populate form inputs once; polling never overwrites an operator’s edits. */
export function renderSettings(settings) {
 for (const [key,title,type,min,max,section] of fields) {
  const box=document.createElement('div');box.className=`form-field ${key==='whatsapp_group'||key==='whatsapp_database'?'wide':''}`;
  const input=settingInput(key,type,min,max,settings[key]);
  const label=document.createElement('label');label.htmlFor=input.id;label.textContent=title;
  box.append(label,input);document.getElementById(section==='advanced'?'advanced-settings':'main-settings').append(box);
 }
}
/** Collect typed form values for backend validation and the immutable game snapshot. */
export function readSettings() {
 return Object.fromEntries(fields.map(([key,,type])=>{
  const input=document.getElementById(`setting-${key}`);
  const value=type==='checkbox'?input.checked:type==='number'?Number(input.value):input.value;
  return [key,value];
 }));
}
