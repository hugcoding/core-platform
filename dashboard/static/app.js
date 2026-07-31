const $=id=>document.getElementById(id), nf=new Intl.NumberFormat('nl-NL');
const dt=v=>v?new Date(v).toLocaleString('nl-NL',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'—';
const bytes=v=>{if(v==null)return'—';let i=0,n=Number(v);for(;n>=1024&&i<4;i++)n/=1024;return`${n.toFixed(i?1:0)} ${['B','KB','MB','GB','TB'][i]}`};
function metric(id,v){$(id).textContent=v==null?'—':nf.format(v)}
function serviceCard(s){return `<article class="service ${s.state}"><i></i><div><strong>${s.name.replace('_',' ')}</strong><small>${s.detail}</small></div><span>${s.state}</span></article>`}
async function refresh(){try{const r=await fetch('/api/v1/overview',{cache:'no-store'});if(!r.ok)throw Error(r.status);const d=await r.json();
 document.body.dataset.state=d.overall;$('overall').textContent={healthy:'All systems nominal',attention:'Attention required',degraded:'Platform degraded'}[d.overall];
 $('summary').textContent=d.errors.length?d.errors.join(' · '):'CORE verwerkt en bewaakt je gegevens.';$('updated').textContent=dt(d.generated_at);
 $('services').innerHTML=d.services.map(serviceCard).join('');metric('activeFiles',d.metrics.active_files);metric('contentGroups',d.metrics.content_groups);metric('duplicates',d.metrics.duplicate_groups);metric('events',d.metrics.active_events);
 const c=d.classifier;$('progress').style.width=`${c.percent||0}%`;$('progressPct').textContent=`${c.percent||0}%`;$('progressCount').textContent=`${nf.format(c.processed||0)} / ${nf.format(c.total||0)}`;$('classifierState').textContent=c.active?'actief':'gereed / inactief';
 const h=d.host, storagePct=h.storage_total?Math.round(h.storage_used*100/h.storage_total):0, memPct=h.memory_total?Math.round(h.memory_used*100/h.memory_total):0;
 $('host').innerHTML=`<div><span>Opslag</span><b>${storagePct}%</b><small>${bytes(h.storage_free)} vrij</small></div><div><span>Geheugen</span><b>${memPct}%</b><small>${bytes(h.memory_used)} gebruikt</small></div><div><span>Load</span><b>${h.load_1m??'—'}</b><small>1 minuut</small></div>`;
 $('scans').innerHTML=d.recent_scans.map(s=>`<tr><td><span class="tag">${s.type}</span></td><td>${s.status}</td><td>${dt(s.started_at)}</td><td>${nf.format(s.files_discovered)}</td><td>${nf.format(s.jobs_enqueued)} / ${nf.format(s.jobs_processed)}</td></tr>`).join('')||'<tr><td colspan="5">Geen scans beschikbaar</td></tr>';
 $('queues').innerHTML=[['Polling',d.metrics.polling_queue],['Realtime',d.metrics.realtime_queue],['DLQ',d.metrics.dlq],['Dirty roots',d.metrics.dirty_roots],['Lege bestanden',d.metrics.empty_files],['Gewijzigd 24u',d.metrics.changed_24h]].map(([k,v])=>`<div><span>${k}</span><b>${nf.format(v??0)}</b></div>`).join('');
 }catch(e){document.body.dataset.state='degraded';$('overall').textContent='Dashboard offline';$('summary').textContent='Live API niet bereikbaar.'}}
setInterval(()=>{$('clock').textContent=new Date().toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit',second:'2-digit'})},1000);refresh();setInterval(refresh,10000);
