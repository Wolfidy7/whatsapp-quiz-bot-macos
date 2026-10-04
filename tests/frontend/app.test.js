import {it,expect,vi,afterEach} from 'vitest';
import {readFileSync} from 'node:fs';
const question={id:'capital',question:'Capital?',answer:'Paris'};
let bank=[question],session={},failure=null,accepted=true;
const byId=id=>document.getElementById(id);
async function settle(){for(let i=0;i<15;i++)await Promise.resolve();}
async function click(id){byId(id).click();await settle();}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
it('handles editor, rehearsal, incidents, imports and exports through the DOM',async()=>{
 vi.useFakeTimers();document.documentElement.innerHTML=readFileSync('quiz_app/static/index.html','utf8');
 vi.stubGlobal('fetch',vi.fn(async(path,options)=>{
  const payload=options.body?JSON.parse(options.body):undefined;
  if(failure){const value=failure;failure=null;return {ok:false,json:async()=>value};}
  if(path==='/api/questions'&&options.method==='PUT')bank=payload;
  if(path==='/api/start')session={id:'fake',phase:'registration',players:[],rounds:[],deadline:Date.now()/1000+60};
  if(path==='/api/inject')session.players=[payload.author];
  if(path==='/api/cancel')session.phase='cancelled';
  if(path.startsWith('/api/recover'))session={id:'fake',phase:'paused',error:'RECOVERY_REQUIRED'};
  const value=path==='/api/questions'?bank:path==='/api/capabilities'?{native_ready:true}:path==='/api/settings'?{max_players:20}:path==='/api/test-answer'?{accepted,alias:accepted?'Paris':null}:session;
  return {ok:true,json:async()=>value};
 }));
 URL.createObjectURL=vi.fn(()=>'blob:fake');URL.revokeObjectURL=vi.fn();
 const anchorClick=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 await import('../../quiz_app/static/app.js');
 expect(byId('bank').value).toContain('Capital?');
 await click('save');byId('candidate').value='Paris';await click('check');expect(byId('verdict').textContent).toContain('Accepted');
 accepted=false;await click('check');expect(byId('verdict').textContent).toContain('Rejected');
 await click('start');expect(byId('phase').textContent).toBe('REGISTRATION');
 await click('native');await click('resume');
 await click('inject');expect(byId('players').textContent).toBe('1');
 session.outbox=[{status:'pending',text:'Reserved marker'},{status:'sent',text:'Done'}];
 session.rounds=[{question,results:[]}];await vi.advanceTimersByTimeAsync(1000);
 expect(byId('prompt').textContent).toBe('Capital?');
 expect(byId('pending').textContent).toBe('Reserved marker');
 await click('cancel');await click('recover');expect(byId('notice').textContent).toBe('RECOVERY_REQUIRED');
 await click('export');expect(anchorClick).toHaveBeenCalled();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');
 Object.defineProperty(byId('import'),'files',{value:[{text:async()=>JSON.stringify(bank)}],configurable:true});
 byId('import').dispatchEvent(new Event('change'));await settle();expect(byId('bank').value).toContain('Capital?');
 Object.defineProperty(byId('import'),'files',{value:[],configurable:true});byId('import').dispatchEvent(new Event('change'));await settle();
 for(const value of [{message:'storage failed'},{detail:'bad schema'},{error:'UNKNOWN'}]){failure=value;await click('save');expect(byId('notice').textContent.length).toBeGreaterThan(0);}
 byId('bank').value='{';await click('save');expect(byId('notice').textContent.length).toBeGreaterThan(0);
 anchorClick.mockRestore();
});
