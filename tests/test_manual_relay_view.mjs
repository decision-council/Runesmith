// Exercise the actual relay renderer without a browser, server or model call.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../runesmith/app/static/js/views/inference.js',import.meta.url),'utf8');
function h(tag,attrs,...children) {
  if (!attrs || typeof attrs!=='object' || Array.isArray(attrs) || attrs.tag) {children.unshift(attrs);attrs={};}
  return {tag,attrs,children:children.flat(Infinity),value:attrs.value||'',events:{},
    append(...rows){this.children.push(...rows.flat(Infinity));},
    addEventListener(name,handler){this.events[name]=handler;}};
}
function text(node) {return node==null?'':typeof node==='string'?node:(node.children||[]).map(text).join('\n');}
function nodes(node) {return [node,...(node.children||[]).filter(n=>n&&typeof n==='object').flatMap(nodes)];}
function button(panel,label) {return nodes(panel).find(n=>n.tag.startsWith('button')&&text(n).trim()===label);}
async function click(node) {assert(node);return (node.events.click||node.attrs.onclick)({currentTarget:node});}
const posts=[],copies=[],confirms=[];let reloaded=0,confirm=true,result={written:null,problems:['answer.files[0]: missing required content or edits']};
const context=vm.createContext({h,icon:()=>'',toast:()=>{},clear:n=>{n.children=[];return n;},
  copyText:async t=>copies.push(t),withBusy:async(_,fn)=>fn(),
  post:async(path,data)=>{posts.push({path,data});return data.force?{written:'answer.md',problems:result.problems}:result;},
  confirmDialog:async data=>{confirms.push(data);return confirm;}});
vm.runInContext('const relayReplies = new Map();\n'+source.slice(source.indexOf('function relayPanel(')),context);
const request={id:'test-request',approx_tokens:42,text:'Original request and schema'};
const panel=context.relayPanel([request],()=>reloaded++);
assert(text(panel).includes('Keep Studio running'));
assert(text(panel).includes('does not approve the code'));
await click(button(panel,'Copy'));assert.deepEqual(copies,['Original request and schema']);
const answer=nodes(panel).find(n=>n.tag.startsWith('textarea'));
const model=nodes(panel).find(n=>n.tag==='input.input');
answer.value='malformed reply';model.value='self-reported';
await click(button(panel,'Send the answer'));
assert.equal(posts.length,1);assert.equal(confirms.length,0);assert.equal(reloaded,0);
assert.equal(answer.value,'malformed reply');
assert(text(panel).includes('Not submitted'));
await click(button(panel,'Copy correction request'));
assert(copies.at(-1).includes('complete corrected reply'));
assert(copies.at(-1).includes('answer.files[0]'));
assert(copies.at(-1).includes('not a test result'));
assert.equal(posts.length,1); // Copying feedback does not submit or force an answer.
confirm=false;await click(button(panel,'Send unchanged anyway'));
assert.equal(posts.length,1);
assert(confirms.at(-1).text.includes('application permissions still apply'));
confirm=true;await click(button(panel,'Send unchanged anyway'));
assert.equal(posts.length,2);assert.equal(posts.at(-1).data.force,true);assert.equal(reloaded,1);
const second=context.relayPanel([request],()=>reloaded++);
const a2=nodes(second).find(n=>n.tag.startsWith('textarea'));a2.value='old';
await click(button(second,'Send the answer'));
const staleForce=button(second,'Send unchanged anyway');
a2.value='edited';a2.events.input();
assert(!button(second,'Copy correction request'));
const before=posts.length;await click(staleForce);assert.equal(posts.length,before);
result={written:'answer.md',problems:[]};
await click(button(second,'Send the answer'));
assert.equal(posts.at(-1).data.text,'edited');assert(!posts.at(-1).data.force);assert.equal(reloaded,2);
const empty=context.relayPanel([],()=>{});
assert(text(empty).includes('When a model set up'));assert(!button(empty,'Send the answer'));
assert(source.includes('There are no unanswered chat requests in this workspace.'));
const pending=context.relayPanel([request],()=>{});
const pendingAnswer=nodes(pending).find(n=>n.tag.startsWith('textarea'));
const pendingModel=nodes(pending).find(n=>n.tag==='input.input');
pendingAnswer.value='unsent draft';pendingAnswer.events.input();
pendingModel.value='label';pendingModel.events.input();
const restored=context.relayPanel([request],()=>{});
assert.equal(nodes(restored).find(n=>n.tag.startsWith('textarea')).value,'unsent draft');
assert.equal(nodes(restored).find(n=>n.tag==='input.input').value,'label');
const changed=context.relayPanel([{...request,text:'Different packet with reused ID'}],()=>{});
assert.equal(nodes(changed).find(n=>n.tag.startsWith('textarea')).value,'');
const originalAgain=context.relayPanel([request],()=>{});
assert.equal(nodes(originalAgain).find(n=>n.tag.startsWith('textarea')).value,'');
const prunable=nodes(originalAgain).find(n=>n.tag.startsWith('textarea'));
prunable.value='no longer pending';prunable.events.input();context.relayPanel([],()=>{});
assert.equal(nodes(context.relayPanel([request],()=>{})).find(n=>n.tag.startsWith('textarea')).value,'');
console.log('Actual chat-relay renderer: correction/copy/force/stale-reply/submit/empty/cache-identity/pruning cases passed; no inference.');
