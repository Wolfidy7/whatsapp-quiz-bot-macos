import {explainError} from './core.js';
/** Locate a named dashboard element. */
export const byId=id=>document.getElementById(id);
/** Create an element with a class and safe text content. */
export function el(tag,className,text) {
 const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;
}
const ICONS={success:'🎉',info:'💡',warning:'⚠️',error:'🚨'};
/** Show a notification; errors stay until closed, other kinds fade after a few seconds. */
export function toast(kind,title,text='',detail='') {
 const box=el('div',`toast ${kind}`);box.setAttribute('role',kind==='error'?'alert':'status');
 const body=el('div');body.append(el('strong','',title));if(text)body.append(el('p','',text));if(detail)body.append(el('small','',detail));
 const close=el('button','','✕');close.setAttribute('aria-label','Fermer');close.addEventListener('click',()=>box.remove());
 box.append(el('span','icon',ICONS[kind]),body,close);
 const stack=byId('toasts');stack.prepend(box);
 while(stack.children.length>4)stack.lastElementChild.remove();
 if(kind!=='error')setTimeout(()=>box.remove(),4500);
 return box;
}
/** Explain an error in a toast and, when given, inline next to the action that failed. */
export function showError(error,inline) {
 const {title,hint,detail}=explainError(error);
 toast('error',title,hint,detail);
 if(inline){inline.replaceChildren(alertBox('error',`🚨 ${title}`,hint,detail));inline.hidden=false;}
}
/** Build an inline alert block with a title, an explanation and an optional raw detail. */
export function alertBox(kind,title,text,detail) {
 const box=el('div',`alert ${kind}`);box.append(el('strong','',title));
 if(text)box.append(el('p','',text));if(detail)box.append(el('small','',`Détail : ${detail}`));
 return box;
}
/** Switch tabs from the nav and the URL hash; the selected tab survives reloads. */
export function setupTabs() {
 const tabs=[...document.querySelectorAll('[data-tab]')];
 const select=name=>{
  const chosen=tabs.some(tab=>tab.dataset.tab===name)?name:'jouer';
  for(const tab of tabs){const on=tab.dataset.tab===chosen;tab.setAttribute('aria-selected',String(on));byId(`panel-${tab.dataset.tab}`).hidden=!on;}
  history.replaceState(null,'',`#${chosen}`);
 };
 for(const tab of tabs)tab.addEventListener('click',()=>{select(tab.dataset.tab);window.scrollTo(0,0);});
 select(location.hash.slice(1));
 return select;
}
/** Flag a tab that needs attention. */
export function markTab(name,on){byId(`tab-${name}`).querySelector('.dot').hidden=!on;}
/** Celebrate a finished game with a short burst of confetti. */
export function confetti() {
 const colors=['#6c3bff','#ff4fa3','#ffc93c','#12b5a0','#ff7a45'];
 for(let index=0;index<40;index++){
  const piece=el('i','confetti');piece.style.left=`${(index*37)%100}vw`;piece.style.background=colors[index%colors.length];
  piece.style.animationDelay=`${(index%10)*0.08}s`;document.body.append(piece);setTimeout(()=>piece.remove(),3200);
 }
}
