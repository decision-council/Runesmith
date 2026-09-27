// Local report custody and deliberate model sharing; never dispatches a job.
import {h, icon, get, post, toast, clear, drawer, withBusy, confirmDialog, bus, debounce} from './core.js';

const LABELS={not_selected:'Local only · not selected',selected_for_next_packet:'Selected for next matching repair packet',
  budget_omitted:'Selected but omitted by packet budget',target_unavailable:'Selected but target is unavailable or changed'};

export function supportReportsCard() {
  const node=h('section.card.support-reports',{'aria-label':'Support reports'});
  let current=null,closed=false,serial=0;
  const active=()=>{if(closed)throw new Error('This report view was closed. Reopen it before saving.');};
  const refresh=async()=>{
    const request=++serial, data=await get('/api/support-reports');
    if(!closed&&request===serial)update(data);
  };
  const paste=()=>{
    const snapshot=current;
    drawer({title:'Paste support report',sub:'Minimized incident evidence, not owner instructions',render(body,close){
      let pending=false;
      const title=h('input.input',{'aria-label':'Report title',maxlength:120});
      const source=h('input.input',{'aria-label':'Report source',maxlength:240,placeholder:'e.g. redacted support incident, reviewed by me'});
      const target=h('select.select',{'aria-label':'Affected component'},h('option',{value:''},'Choose a mapped component'),
        snapshot.targets.map(t=>h('option',{value:t.name},`${t.name} · ${t.path}`)));
      const reported=h('input.input',{'aria-label':'Reported time',placeholder:'Optional: 2026-09-27T06:00:00Z'});
      const text=h('textarea.textarea.mono',{rows:12,maxlength:snapshot.max_excerpt_chars,'aria-label':'Support excerpt',
        placeholder:'Keep only the symptom, reproduction steps and necessary diagnostic lines. Remove keys and customer identifiers.'});
      const count=h('span.tiny.muted',`0 / ${snapshot.max_excerpt_chars} characters`);
      text.addEventListener('input',()=>{count.textContent=`${text.value.length} / ${snapshot.max_excerpt_chars} characters`;});
      const status=h('p.small',{'aria-live':'polite'});
      body.append(h('p.callout','Saving retains this excerpt locally, with sharing OFF. Review it, then explicitly select it for the configured repair model. No job is started by either action.'),
        h('p.small.muted','Reports are claims to investigate, not verified defects or instructions to execute. There is no automatic removal of secrets or personal information. Retained excerpts and sessions are included in home snapshot exports; review those archives before sharing.'),
        ...[[title,'Title'],[source,'Source / provenance label'],[target,'Affected component'],[reported,'Reported time (timezone required if supplied)'],[text,'Minimized excerpt']]
          .map(([control,label])=>h('label.col.mt-8',h('b.small',label),control)),count,status,
        h('button.btn.primary.mt-16',{onclick:e=>withBusy(e.currentTarget,async()=>{
          if(pending)return;active();
          if(!title.value.trim()||!source.value.trim()||!target.value||!text.value.trim()){
            status.textContent='Add a title, source, mapped component and excerpt.';return;
          }
          pending=true;status.textContent='Saving locally…';
          try{
            const result=await post('/api/support-reports',{revision:snapshot.revision,report:{title:title.value,source:source.value,
              target:target.value,text:text.value,reported_at:reported.value}});
            close();toast(result.reused?'Existing report retained; its selection is unchanged.':'Support report retained locally. Sharing is off.','good');await refresh();
          }catch(error){status.textContent=`Not confirmed: ${error.message}. Your text is retained here; no automatic retry. Refresh the inbox before making another submission.`;throw error;}
          finally{pending=false;}
        })},icon('check'),'Save locally'));
    }});
  };
  function update(data){
    if(closed)return;
    current=data;clear(node);
    node.append(h('div.card-head',h('h3',icon('note'),'Support reports · Troubleshoot'),
      h('button.btn.sm',{onclick:e=>withBusy(e.currentTarget,refresh)},icon('refresh'),'Refresh inbox')));
    if(!data?.available){node.append(h('p.callout.warn',data?.error||'Support-report view is unavailable; no assumption of an empty inbox.'));return;}
    node.append(h('p.small.muted','Retain a minimized incident excerpt locally, then choose whether the repair model may use it. Importing or selecting never starts work.'),
      h('div.row.wrap',h('button.btn.sm',{disabled:!data.targets.length,onclick:paste},icon('plus'),'Paste support report'),
        h('span.tiny.muted',`${data.items.length} / ${data.limit} retained`)),
      h('details.mt-8',h('summary.small','Sharing, retention & repair limits'),h('p.small.muted',data.scope),
        h('p.tiny.muted',`Preview as of this refresh. At most ${data.max_included} newest selected reports per component, within ${data.budget_bytes} UTF-8 bytes of report entries. Selection does not prove delivery or resolution and does not reopen an already-served failure.`)));
    if(!data.targets.length)node.append(h('p.small.warn','Refresh the Living map first. This intake currently targets mapped Python repositories; standalone report diagnosis and other repair adapters are not implemented.'));
    if(!data.items.length)node.append(h('p.small.muted','No support excerpts retained. Importing an excerpt will not start Troubleshoot.'));
    for(const row of data.items){
      const targetOK=row.delivery!=='target_unavailable'&&data.targets.some(t=>t.name===row.target.name&&t.path===row.target.path);
      let pending=false;
      const choose=h('button.btn.sm',{disabled:!row.selected&&!targetOK,onclick:e=>withBusy(e.currentTarget,async()=>{
        if(pending)return;pending=true;
        try{
          active();
          const selected=!row.selected;
          if(selected&&!await confirmDialog({title:'Share this support excerpt with the repair model?',
            text:`${row.title} → ${row.target.name} (${row.target.path}). The excerpt, source label and timestamps may be sent to the configured repair provider in a future matching step. Confirm you reviewed the retained text and removed unnecessary secrets or personal data. Sessions/proposals remain local review records, excluded from learning memory and Kaizen/trial reuse. This does not queue work.`,
            confirm:'Allow future repair context'}))return;
          active();
          await post(`/api/support-reports/${row.id}/selection`,{revision:data.revision,selected,confirm_model_sharing:selected});
          toast(selected?'Selected for future matching repair context; no job started.':'Excluded from future repair context. Already-sent requests retain their original input.','good');await refresh();
        }finally{pending=false;}
      })},row.selected?'Exclude from future repairs':'Select for repair context');
      node.append(h('article.card.flat.mt-8',h('h4',row.title),h('span.badge',LABELS[row.delivery]||'Delivery unknown'),
        h('p.small',`${row.target.name} · ${row.target.path}`),
        h('details.mt-8',h('summary.small','Review retained excerpt & provenance'),h('p.small',`Source: ${row.source}`),
          h('p.tiny.muted',`Reported: ${row.reported_at||'not supplied'} · Received: ${row.received_at}`),
          h('pre.code',row.text),h('p.tiny.mono',`Excerpt SHA-256: ${row.source_sha256}`),h('p.tiny.mono',`Receipt: ${row.id}`)),
        h('div.row.wrap.mt-8',choose)));
    }
  }
  const off=bus.on('support_reports',debounce(()=>{if(!closed)refresh().catch(e=>toast(e.message,'warn'));},250));
  return {node,update,dispose(){closed=true;serial++;off();}};
}
