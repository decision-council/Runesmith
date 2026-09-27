// Work policies and local outcome evidence, separate from authority and model usage.
import {h, icon, get, post, toast, clear, drawer, withBusy, bus, debounce} from '../core.js';
import {measurementReadiness} from '../measurement-readiness.js';
import {supportReportsCard} from '../support-reports.js';

const EXECUTORS = [['map_plan','Map & Plan'],['build','Build'],['troubleshoot','Troubleshoot'],['optimize','Optimize'],['operations','Operations']];

function measurementEditor(item, revision, reload) {
  drawer({title: item?.id ? 'Edit measurement' : 'Add measurement', sub: 'Define the evidence before interpreting a result', render(body, close) {
    const fields = {};
    const input = (key, label, hint='', value='') => {
      const node = h('input.input', {value: item?.[key] ?? value, placeholder: hint, 'aria-label': label});
      fields[key] = node; return h('label.col.mt-8', h('b.small', label), node);
    };
    const select = (key, label, options, fallback) => {
      const node = h('select.select', {'aria-label': label}, options.map(([v,l]) => h('option', {value:v, selected:(item?.[key]||fallback)===v}, l)));
      fields[key] = node; return h('label.col.mt-8', h('b.small', label), node);
    };
    const enabled = h('input', {type:'checkbox', checked:item?.enabled ?? true, 'aria-label':'Measurement enabled'});
    body.append(h('p.small.muted', 'Local CSV/JSON and pasted structured reports work here. GA4 and email entries are configuration placeholders, not live connections. No raw report rows are sent to models.'),
      h('label.row', enabled, 'Enabled'), input('name','Name','e.g. Successful checkouts'), input('goal','Objective / goal reference'),
      select('source_kind','Receive data from', [['csv','CSV dropped at a project path'],['json','JSON dropped at a project path'],
        ['paste_csv','Pasted CSV report'],['paste_json','Pasted JSON report'],['ga4','Live GA4 — unavailable'],['email','Filtered email — unavailable']], 'csv'),
      input('path','Relative report path','reports/metrics.csv'), input('source_label','Source / data description','e.g. GA4 export, not a live connection'),
      select('aggregation','Calculate', [['count','Count selected rows'],['sum','Sum'],['mean','Mean'],['latest','Latest timestamped value']], 'count'),
      input('field','Numeric field / column','Required except for count'), input('unit','Unit','events, ms, orders…'),
      input('filter_field','Filter field (optional)'), input('filter_equals','Must equal'),
      input('time_field','Timestamp field (required for latest/window/age)'), input('start','Window start, inclusive','2026-09-01T00:00:00Z'),
      input('end','Window end, exclusive','2026-10-01T00:00:00Z'),
      input('max_age_hours','Maximum data age (hours, optional)','Blank: no recency rule'),
      h('p.small.muted','Requires a timestamp field. The age rule uses the newest included data timestamp, never the file or measurement time. It does not prove that all rows are recent or complete. Expired evidence blocks Optimize; Operations can still import a replacement.'),
      input('email_sender','Future email sender filter','No mailbox access is performed'), input('email_subject','Future email subject filter'));
    const op = h('select.select', {'aria-label':'Threshold comparison'}, [['','No threshold'],['gte','At least'],['lte','At most']].map(([v,l])=>h('option',{value:v,selected:(item?.threshold?.op||'')===v},l)));
    const threshold = h('input.input', {type:'number',step:'any',value:item?.threshold?.value ?? '', 'aria-label':'Threshold value'});
    const instructions = h('textarea.textarea', {rows:5,value:item?.instructions||'', 'aria-label':'Interpretation instructions',placeholder:'How to interpret this measure, its limitations, expected data period and what a useful change would mean.'});
    body.append(h('label.col.mt-8', h('b.small','Optional target (not automatic acceptance)'), op, threshold),
      h('label.col.mt-8',h('b.small','Interpretation instructions'),instructions),
      h('p.tiny.muted','Use timezone-qualified ISO timestamps. Empty windows are unknown, never zero. JSON must be an array of row objects. No formulas or executable expressions. Limits: 256 KB and 5,000 rows.'),
      h('button.btn.primary.mt-16',{onclick:e=>withBusy(e.currentTarget,async()=>{
        const definition=Object.fromEntries(Object.entries(fields).map(([k,n])=>[k,n.value]));
        definition.id=item?.id;definition.enabled=enabled.checked;definition.instructions=instructions.value;
        const age=fields.max_age_hours.value.trim();
        if(age&&(!Number.isFinite(Number(age))||Number(age)<=0||Number(age)>87600)){toast('Enter a positive data-age limit in hours (at most 87600), or leave it blank.','warn');return;}
        if(age&&!fields.time_field.value.trim()){toast('A data-age rule needs a timestamp field.','warn');return;}
        definition.max_age_hours=age?Number(age):null;
        if(op.value && !threshold.value.trim()){toast('Enter a threshold value.','warn');return;}
        definition.threshold=op.value?{op:op.value,value:Number(threshold.value)}:null;
        await post('/api/measurements',{revision,definition});close();reload();toast('Definition saved. No report read or model call.','good');
      })},icon('check'),'Save definition'));
  }});
}

function pasteReport(item, reload) {
  drawer({title:`Report for ${item.name}`,sub:'Structured report data, not instructions to execute',render(body,close){
    const text=h('textarea.textarea.mono',{rows:16,'aria-label':'Report text',placeholder:item.source_kind==='paste_csv'?'time,value\n2026-09-26T12:00:00Z,42':'[{"time":"2026-09-26T12:00:00Z","value":42}]'});
    body.append(h('p.small.muted','The payload is kept in this workspace home with its digest. Include only the data you intend Runesmith to read.'),text,
      h('button.btn.primary.mt-8',{onclick:e=>withBusy(e.currentTarget,async()=>{
        await post(`/api/measurements/${encodeURIComponent(item.id)}/report`,{text:text.value});close();reload();toast('Report received. Use Measure now to evaluate it.','good');
      })},icon('check'),'Save report'));
  }});
}

export default async function render(root, ctx) {
  root.classList.add('mission-page');
  let dirty=false,closed=false,loadSerial=0; const runButtons=[];
  const reports=supportReportsCard();
  const heading=h('div.page-head',h('div',h('h2','Modes & measurements'),h('p','Choose what Runesmith works on and how results are observed. Every mode can be on together.')));
  const refreshStatus=h('span.tiny.muted',{'aria-live':'polite'},'Saved receipts only; refresh does not remeasure.');
  const body=h('div');root.append(heading,body);
  const load=async()=>{
    if(dirty||closed)return false;
    const serial=++loadSerial,data=await get('/api/mission');
    if(dirty||closed||serial!==loadSerial)return false;
    clear(body);runButtons.length=0;
    const modes=data.modes.map(({id,name,executor,enabled,instructions,measurement_ids})=>({id,name,executor,enabled,instructions,measurement_ids:[...measurement_ids]}));
    const modesCard=h('div.card');const rows=h('div.col.gap-16.mt-16');const dirtyLabel=h('p.tiny.faint','Saved configuration');
    const mark=()=>{dirty=true;dirtyLabel.textContent='Unsaved changes — save modes before running them.';runButtons.forEach(b=>b.disabled=true);};
    const infer=h('input',{type:'checkbox',checked:data.infer_purpose,'aria-label':'Infer purpose without explicit direction',onchange:mark});
    const drawMode=(mode)=>{
      const existing=data.modes.find(r=>r.id===mode.id);
      const checkbox=h('input',{type:'checkbox',checked:mode.enabled,'aria-label':`${mode.name} enabled`,onchange:e=>{mode.enabled=e.target.checked;mark();}});
      const guidance=h('textarea.textarea',{rows:3,value:mode.instructions,'aria-label':`${mode.name} instructions`,placeholder:'Instructions specific to this activity; no extra permissions.'});
      guidance.addEventListener('input',()=>{mode.instructions=guidance.value;mark();});
      const selected=new Set(mode.measurement_ids);
      const metrics=h('div.col.gap-6',...data.measurements.items.map(m=>h('label.row.small',
        h('input',{type:'checkbox',checked:selected.has(m.id),onchange:e=>{e.target.checked?selected.add(m.id):selected.delete(m.id);mode.measurement_ids=[...selected];mark();}}),m.name)));
      const run=h('button.btn.sm',{disabled:dirty||!mode.enabled||Boolean(existing?.blockers.length),onclick:e=>withBusy(e.currentTarget,async()=>{
        if(dirty){toast('Save mode changes first.','warn');return;}
        await post('/api/worker/run',{job:'mode',params:{mode:mode.id}});toast('Queued through the normal serial worker.','good');
      })},icon('play'),'Run now');runButtons.push(run);
      rows.append(h('div.card.flat',h('div.row.mission-mode-head',h('h3',mode.name),h('span.badge',mode.executor),h('span.spacer'),h('label.switch',checkbox,h('span')),run),
        h('p.small.muted',existing?.description||`Custom guidance over the ${mode.executor} executor; no new tools or authority.`),
        h('details.mt-8',h('summary.small',`${mode.name}: instructions & evidence`),guidance,
          ['operations','optimize'].includes(mode.executor)?h('div.mt-8',h('p.small','Measurements for this mode'),metrics):null),
        existing?.blockers.length?h('p.small.warn',existing.blockers.join(' ')):null,
        existing?.last?h('p.tiny.muted',`${existing.last.utc}: ${existing.last.result.summary}`):null));
    };
    modes.forEach(drawMode);
    const reason=h('input.input',{placeholder:'Why change these modes?', 'aria-label':'Mode change reason'});
    const customName=h('input.input',{placeholder:'Custom mode name','aria-label':'Custom mode name'});
    const executor=h('select.select',{'aria-label':'Custom mode executor'},EXECUTORS.map(([id,label])=>h('option',{value:id},label)));
    modesCard.append(h('h3',icon('sliders'),'Activity modes'),
      h('p.small.muted',`${data.configured?'Explicit mode routing':'Legacy routing retained until you save modes'}. Scheduling is ${data.scheduling.auto_work?'on':'off'}; self-improvement is ${data.scheduling.kaizen?'on':'off'}. Saving modes changes neither.`),
      h('p.small',data.scheduling.policy),
      h('div.mission-controls',h('label.col',h('span.small','Reason for change'),reason),dirtyLabel,
        h('button.btn.primary',{onclick:e=>withBusy(e.currentTarget,async()=>{
          await post('/api/mission/modes',{revision:data.revision,modes,infer_purpose:infer.checked,reason:reason.value});dirty=false;await load();ctx.refreshState();toast('Modes saved; permissions and scheduling unchanged.','good');
        })},icon('check'),'Save modes')),
      ...(data.legacy_upgrade?[h('p.callout.warn','Older mode settings: Map & Plan and purpose inference start off. Saving upgrades the settings explicitly; no automatic new activity.')]:[]),
      h('div.card.flat.mt-16',h('label.row',infer,h('b','Infer purpose without explicit direction')),
        h('p.small.muted','When on, the planner may propose a purpose from the environment and label its assumptions. When off, planning needs an owner brief, goal or selected blueprint. Restrictions are always read. An existing plan can drive Build with Map & Plan off.'),
        h('p.tiny.muted','Read-only map refresh remains available. Existing inferred plans keep their provenance; this switch does not adopt them or grant production authority.')),rows,
      h('div.row.mt-16',customName,executor,h('button.btn',{onclick:()=>{
        if(!customName.value.trim())return;
        const id='custom-'+Date.now().toString(36)+'-'+modes.length;
        const row={id,name:customName.value.trim(),executor:executor.value,enabled:false,instructions:'',measurement_ids:[]};modes.push(row);mark();drawMode(row);customName.value='';
      }},icon('plus'),'Add custom mode')),
      h('p.tiny.muted','Current execution is serial. Production adapters and speed/concurrency controls remain open additions. Self-improvement and scheduling remain in Settings.'));
    const intent=data.intent;
    const intentCard=h('div.card',h('h3',icon('map'),'Instructions & purpose'),h('span.badge',intent.purpose.basis),
      h('p',intent.purpose.text),h('p.small.muted',intent.purpose.uncertainty),h('p.tiny.muted',intent.discovery_scope),
      ...intent.blockers.map(t=>h('p.callout.warn',t)),
      ...intent.instructions.map(i=>h('details.mt-8',h('summary.small',`${i.path} · scope ${i.scope} · ${i.kind}`),h('p.tiny.mono',i.sha256),h('pre.code',i.text))),
      h('p.tiny.muted',intent.rule));
    const metricCard=h('div.card',h('div.card-head',h('h3',icon('target'),'Objective measurements'),h('button.btn.sm',{onclick:()=>measurementEditor(null,data.measurements.revision,load)},icon('plus'),'Add measurement')),
      h('p.small.muted',data.measurements.scope));
    for(const item of data.measurements.items){
      const last=item.last;const live=['ga4','email'].includes(item.source_kind);
      const label=last?.status==='measured'?`${last.value} ${last.unit??''}`:last?.status||'not measured';
      metricCard.append(h('div.card.flat.mt-8',h('div.row',h('b',item.name),h('span.badge',item.enabled?'enabled':'off'),h('span.badge',item.adapter)),
        h('p',label),last?h('p.tiny.muted',`Observed ${last.measured_at}; data timestamp ${last.latest_data_at||'not supplied'}. Receipt ${last.id}`):null,
        last?.detail?h('p.small',last.detail):null,last?.current_definition===false?h('p.callout.warn','Definition changed; this historical value is not a current measurement.'):null,
        last?.rows?h('p.tiny.muted',`${last.rows.included}/${last.rows.total} rows included; ${last.rows.filter_excluded} filtered and ${last.rows.window_excluded} outside the window.`):null,
        last?.threshold_met!==null&&last?.threshold_met!==undefined?h('p.small',`Recorded threshold ${last.threshold_met?'met':'not met'}; historical report, not automatic goal acceptance.`):null,
        last?measurementReadiness(last.assessment):null,
        h('div.row.wrap',h('button.btn.sm',{onclick:()=>measurementEditor(item,data.measurements.revision,load)},icon('pencil'),'Edit'),
          item.source_kind.startsWith('paste_')?h('button.btn.sm',{onclick:()=>pasteReport(item,load)},icon('note'),'Paste report'):null,
          h('button.btn.sm',{disabled:!item.enabled||live,onclick:e=>withBusy(e.currentTarget,async()=>{await post('/api/worker/run',{job:'measure',params:{measurement:item.id}});toast('Measurement queued; no model call.','good');})},icon('play'),'Measure now'))));
    }
    if(!data.measurements.items.length)metricCard.append(h('p.small','Examples: website event counts, store order/revenue totals, tool latency, support resolution times. A build-only goal can instead use its existing acceptance checks.'));
    const proposals=h('div.card',h('h3',icon('spark'),'Optimization hypotheses'),h('p.small.muted','Proposals only: no code implementation, goal adoption or measured gain is implied.'));
    for(const p of data.proposals)proposals.append(h('details.mt-8',h('summary.small',`${p.state} · ${p.author||'author not recorded'} · ${p.created_at}`),
      p.detail?h('p.small.warn',p.detail):null,
      ...(p.answer?Object.entries(p.answer).map(([k,v])=>h('p.small',h('b',k+': '),v)):p.detail?[]:[h('p.small','Pending or interrupted; inspect the receipt before retrying.')]))) ;
    reports.update(data.support_reports);
    body.append(h('p.callout',data.limits),h('div.grid.two',h('div.col.gap-16',modesCard,intentCard),h('div.col.gap-16',reports.node,metricCard,proposals)));
    return true;
  };
  heading.append(h('div.col.gap-6',h('button.btn',{onclick:e=>withBusy(e.currentTarget,async()=>{
    if(dirty){toast('Save mode changes before refreshing evidence.','warn');return;}
    const loaded=await load();
    if(!closed)refreshStatus.textContent=loaded?'Saved evidence refreshed; no report read or model call.':'View changed during refresh; your edits were preserved.';
  })},icon('refresh'),'Refresh evidence'),refreshStatus));
  await load();const update=debounce(load,350);const offs=['mission','job','brief','goals','map','settings'].map(kind=>bus.on(kind,update));
  return()=>{closed=true;reports.dispose();offs.forEach(off=>off());root.classList.remove('mission-page');};
}
