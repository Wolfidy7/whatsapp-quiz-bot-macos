import {generationStatus} from './core.js';
import {byId,el} from './ui.js';
let shown='';
/** Render one generated question and its expected answer as safe text. */
function generatedItem(question){const row=el('li');row.append(el('span','q',question.question),el('span','a',`✅ ${question.answer}`));return row;}
/** Render a list of checker findings, or nothing. */
function checkList(kind,lines,prefix){const list=el('ul',`check-list ${kind}`);list.append(...lines.map(line=>el('li','',`${prefix} ${line}`)));return lines.length?[list]:[];}
/** Render progress and, once finished, the checked batch with its replace action. */
export function renderGeneration(state) {
 const running=state.status==='running';
 byId('generate').hidden=running;byId('generate-cancel').hidden=!running;byId('gen-form-fields').disabled=running;byId('gen-progress').hidden=!running;
 const status=byId('gen-status');status.textContent=generationStatus(state);status.className=`status${state.status==='failed'?' error':''}`;
 const events=state.events||[];byId('gen-log').hidden=!events.length;byId('gen-events').textContent=events.slice(-20).join('\n');
 const review=state.batch;byId('gen-review').hidden=!review;
 if(!review)return;
 const key=`${state.started}:${review.questions.length}`;
 if(key!==shown){shown=key;byId('gen-questions').replaceChildren(...review.questions.map(generatedItem));}
 byId('gen-total').textContent=`${review.questions.length} question${review.questions.length>1?'s':''}`;
 byId('gen-checks').replaceChildren(...checkList('error',review.errors,'❌'),...checkList('warning',review.warnings,'⚠️'));
 byId('gen-report').textContent=state.report;
 byId('gen-apply').disabled=Boolean(review.errors.length||state.applied);
}
/** Read the typed generation request; the server validates bounds again. */
export function readGeneration(){return {themes:byId('gen-themes').value.trim(),count:Number(byId('gen-count').value),difficulty:byId('gen-difficulty').value};}
