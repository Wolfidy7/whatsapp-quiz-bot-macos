import {generationStatus} from './core.js';
/** Locate a named dashboard element. */
const byId=id=>document.getElementById(id);
let shown='';
/** Render one generated question and its expected answer as safe text. */
function generatedItem(question){const row=document.createElement('li');row.textContent=`${question.question} → ${question.answer}`;return row;}
/** Render progress and, once finished, the checked batch with its replace action. */
export function renderGeneration(state) {
 const running=state.status==='running';
 byId('generate').disabled=running;byId('generate-cancel').disabled=!running;byId('gen-form-fields').disabled=running;
 byId('gen-status').textContent=generationStatus(state);
 const events=state.events||[];byId('gen-events').hidden=!events.length;byId('gen-events').textContent=events.slice(-15).join('\n');
 const review=state.batch;byId('gen-review').hidden=!review;
 if(!review)return;
 const key=`${state.started}:${review.questions.length}`;
 if(key!==shown){shown=key;byId('gen-questions').replaceChildren(...review.questions.map(generatedItem));}
 const checks=[...review.errors.map(error=>`❌ ${error}`),...review.warnings.map(warning=>`⚠️ ${warning}`)];
 byId('gen-checks').hidden=!checks.length;byId('gen-checks').textContent=checks.join('\n');
 byId('gen-report').textContent=state.report;
 byId('gen-apply').disabled=Boolean(review.errors.length||state.applied);
}
/** Read the typed generation request; the server validates bounds again. */
export function readGeneration(){return {themes:byId('gen-themes').value.trim(),count:Number(byId('gen-count').value),difficulty:byId('gen-difficulty').value};}
