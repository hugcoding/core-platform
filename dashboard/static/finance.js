(() => {
'use strict';
const $=id=>document.getElementById(id), money=v=>new Intl.NumberFormat('nl-NL',{style:'currency',currency:'EUR'}).format(Number(v));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const key=()=>crypto.randomUUID?crypto.randomUUID():'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=crypto.getRandomValues(new Uint8Array(1))[0]&15;return(c==='x'?r:(r&3|8)).toString(16)});
const labels={received:'Ontvangen',validated:'Gevalideerd',imported:'Geïmporteerd',partial:'Te beoordelen',rejected:'Afgewezen',rolled_back:'Teruggedraaid',pending:'Wachtend',running:'Bezig',done:'Gereed',failed:'Mislukt'};
const reasons={waiting_for_local_llm:'Wacht op je lokale LLM; hervat automatisch zodra die weer beschikbaar is',recurring_snapshot_changed:'De betalingen of beoordelingen zijn gewijzigd. Vernieuw deze instellingen voordat je akkoord geeft.',recurring_scan_limit:'Dit patroon overschrijdt de bestaande scangrens. Er is niets gewijzigd.',invalid_recurring_status:'Kies een geldige weergave.',invalid_recurring_link:'Kies een los patroon en een ander hoofdpatroon op dezelfde rekening. Een bestaande groep kan niet onder een ander patroon worden gehangen.',manual_review_protected:'Een geselecteerde betaling is handmatig beoordeeld. Geef expliciet toestemming om deze te wijzigen.',capacity_unavailable:'Wacht op een actuele centrale capaciteitsmeting',waiting_for_stable_capacity:'Wacht op stabiele NAS-capaciteit',finance_job_busy:'Er loopt al een andere verwerking. Wacht tot deze gereed is en probeer opnieuw.',bank_reference_differs:'De ASN-nummers verschillen; deze betalingen kunnen niet als dezelfde worden gekoppeld.',bank_reference_reconciled:'ASN-transactienummers gecontroleerd',waiting_for_cpu:'Wacht op CPU-capaciteit',waiting_for_memory:'Wacht op geheugen',postgres_busy:'Database heeft voorrang',controlled_execution_priority:'Gecontroleerde uitvoering heeft voorrang',core_pipeline_priority:'CORE-verwerking heeft voorrang',retry_wait:'Tijdelijke storing; nieuwe poging volgt',no_xml_files:'Geen XML-bestanden gevonden',unsupported_namespace:'XML-versie wordt nog niet ondersteund',balance_mismatch:'Saldo-controle wijkt af',service_unavailable:'Dienst tijdelijk niet beschikbaar'};
let activePeriod={},detailEpoch=0,duplicateEpoch=0;
let managementState=null,managementEpoch=0,managementBusy=false,managementAttempt=null,managementHistoryEpoch=0;
let suggestionsState=null,suggestionsEpoch=0,suggestionSeed=null;
let state=null,page=0,timer=null,lockTimer=null,sessionEpoch=0,refreshId=0,sort='booking_date',direction='desc',editingAccount=null,nameSaveAttempt=null,accountNameEpoch=0,refreshController=null;
Object.assign(reasons,{llm_disabled:'CORE afgerond. LLM staat uit; overige betalingen wachten.',finance_invalid_llm_setting:'Kies LLM aan of uit.',cancelled:'Gestopt door jou',finance_local_endpoint_required:'Configureer een lokaal IP-adres voor de LLM.'});
function armLock(){clearTimeout(lockTimer);lockTimer=setTimeout(()=>{locked();message('Sessie verlopen. Ontgrendel Finance opnieuw.')},3600000)}
function message(value,error=false){$('message').textContent=value;$('message').classList.toggle('error',error)}
function locked(){clearRecurring();$('recurringDialog').close();$('categorizationStatus').textContent='';$('stopCategorize').hidden=true;refreshController?.abort();$('filterStatus').textContent='';sessionEpoch++;duplicateEpoch++;clearManagement();$('accountManagementDialog').close();$('wealthGroup').innerHTML='<option value="">Alle groepen (beheerd overzicht)</option><option value="unassigned">Nog indelen</option>';$('groupScope').textContent='';detailEpoch++;suggestionsEpoch++;suggestionsState=null;suggestionSeed=null;$('suggestionsDialog').close();$('suggestionsBody').replaceChildren();$('suggestionsStatus').textContent='';activePeriod={};$('dateFrom').value='';$('dateTo').value='';$('dateTo').min='';$('dateTo').setCustomValidity('');$('periodRange').hidden=true;$('periodStatus').textContent='';clearAccountName();$('accountNameDialog').close();$('editAccountName').disabled=true;state=null;clearTimeout(timer);clearTimeout(lockTimer);$('workspace').hidden=true;$('lock').hidden=true;$('loginPanel').hidden=false;$('transactions').replaceChildren();$('detailBody').replaceChildren();$('duplicateBody').replaceChildren();$('detail').close();$('duplicates').close();for(const id of ['credits','debits','net','total','uncategorized','imports','income','expenses','transferOut','unknownType','bankBalances','bankBalanceStatus'])$(id).replaceChildren();$('account').innerHTML='<option value="">Alle rekeningen</option>';$('month').innerHTML='<option value="">Alle perioden</option>'}
async function api(path,body,method,signal){const options={signal,credentials:'same-origin',headers:{'Content-Type':'application/json'}};if(body!==undefined){options.method=method||'POST';options.body=JSON.stringify(body)}else if(method)options.method=method;const response=await fetch('/api/v1/finance'+path,options);if(!response.ok){if(response.status===401)locked();let code='finance_unavailable';try{code=(await response.json()).detail}catch{}throw new Error(reasons[code]||({invalid_group_name:'Gebruik een groepsnaam van 1 tot 80 tekens zonder stuurtekens.',invalid_relationship:'Kies een groep en een relatie, of zet de rekening terug op Nog indelen.',group_not_found:'Deze groep is niet beschikbaar. Vernieuw het beheer.',group_changed:'De groepsnaam is ondertussen gewijzigd. Vernieuw het beheer en probeer opnieuw.',account_management_changed:'De rekening is ondertussen gewijzigd. Vernieuw het beheer voordat je opnieuw opslaat.',invalid_category:'Kies een actieve hoofdcategorie en een bijbehorende subcategorie.',invalid_classification:'Kies een geldig transactietype.',invalid_merchant:'Gebruik een merchantnaam van maximaal 120 tekens zonder stuurtekens.',suggestion_example_changed:'Het oorspronkelijke handmatige oordeel is gewijzigd of niet meer beschikbaar. Sla voor deze betaling zelf een oordeel op om een nieuw voorbeeld te gebruiken.',suggestion_needs_manual_example:'Kies een betaling waarvoor je zelf een categorie hebt opgeslagen.',suggestion_scan_limit:'Te veel boekingen voor een directe lokale vergelijking. Er is niets gewijzigd.',suggestion_changed:'Het voorstel of eerdere oordeel is gewijzigd. Vernieuw de voorstellen.',invalid_period:'Kies een geldig jaar of een volledig datumbereik; de einddatum mag niet voor de begindatum liggen.',invalid_account_name:'Gebruik maximaal 80 tekens zonder regelafbrekingen of onzichtbare stuurtekens.',account_name_changed:'De rekeningnaam is ondertussen gewijzigd. Sluit dit venster, vernieuw en probeer opnieuw.',idempotency_conflict:'Dit verzoek is eerder met andere gegevens gebruikt. Sluit en open het naamvenster opnieuw.',account_not_found:'Deze rekening is niet meer beschikbaar.',invalid_code:'Onjuiste toegangscode',finance_locked:'Ontgrendel Finance om verder te gaan',finance_disabled:'Finance is nog niet geactiveerd',review_changed:'Het oordeel is gewijzigd; vernieuw en probeer opnieuw',try_later:'Te veel pogingen. Probeer het over vijf minuten.'}[code])||'De actie is niet uitgevoerd. Vernieuw en probeer opnieuw.')}return response.json()}
function renderBankBalances(value,busy=false){
 const data=value||{accounts:[],pending:0,total:null};
 $('bankBalanceStatus').textContent=data.pending?`${data.pending} eerdere imports wachten op saldoverwerking. ${busy?'Verwerking aangevraagd; volg de voortgang bij Bronnen & imports.':'Kies Saldi uit bestaande imports ophalen.'}`:data.total!==null?`Totaal banksaldo op ${data.as_of}: ${money(data.total)}`:'Geen gezamenlijk saldo beschikbaar op dezelfde peildatum.';
 const row=a=>{const ok=a.status==='reported';return `<tr><td><button class="balance-link" data-balance-account="${esc(a.account_id)}" data-balance-group="${esc(a.group_id||'unassigned')}">${esc(a.label)}</button></td><td>${ok?money(a.opening)+'<br><small>'+esc(a.opening_date||'Datum ontbreekt')+'</small>':'&mdash;'}</td><td>${ok?money(a.closing)+'<br><small>'+esc(a.closing_date)+'</small>':'&mdash;'}</td><td>${ok?`<a href="/api/v1/finance/sources/${esc(a.source_id)}" download>Bankafschrift</a> &middot; ${esc(a.locator)}${data.requested_end&&a.closing_date<data.requested_end?'<br>Geen banksaldo op gekozen einddatum; laatste bekende saldo getoond.':''}`:a.status==='conflict'?'Tegenstrijdige banksaldi op '+esc(a.closing_date)+'; controleer de bronnen.':'Geen banksaldo met bruikbare peildatum beschikbaar.'}</td></tr>`};
 const groups=data.groups||[{id:null,name:'Nog indelen',accounts:data.accounts,total:null}];
 $('bankBalances').innerHTML=groups.map(g=>`<tr class="balance-group"><th scope="rowgroup"><button class="balance-link" data-balance-group="${esc(g.id||'unassigned')}">${esc(g.name)}</button></th><td></td><td>${g.total!==null?money(g.total)+'<br><small>'+esc(g.as_of)+'</small>':'Geen eenduidig groepstotaal'}</td><td>${g.accounts.length} rekeningen</td></tr>`+g.accounts.map(row).join('')).join('');
}
$('bankBalances').onclick=e=>{const button=e.target.closest('[data-balance-group]');if(!button)return;chooseScope(button.dataset.balanceGroup,button.dataset.balanceAccount||'');document.querySelector('.finance-filters').scrollIntoView({behavior:'smooth',block:'start'})};
function scopeAccounts(){const group=$('wealthGroup').value;return (state?.all_accounts||state?.accounts||[]).filter(a=>!group||(group==='unassigned'?!a.group_id:a.group_id===group))}
function syncScope(){
 const accounts=scopeAccounts();select('account',accounts.map(a=>[a.id,a.label]),'<option value="">Alle rekeningen</option>');
 $('editAccountName').disabled=!accounts.some(a=>a.id===$('account').value);
 if(state?.periods_by_account){state.months=[...new Set(accounts.filter(a=>!$('account').value||a.id===$('account').value).flatMap(a=>state.periods_by_account[a.id]||[]))].sort().reverse();state.years=[...new Set(state.months.map(m=>m.slice(0,4)))];periodOptions()}
 $('groupScope').textContent=($('wealthGroup').value==='unassigned'?'Nog indelen':state?.groups?.find(g=>g.id===$('wealthGroup').value)?.name||'Alle groepen: beheerd overzicht, niet alleen eigen vermogen')+' | Actuele rekeningindeling voor alle perioden. Geen berekend vermogen of eigendomsaandeel.';
}
function chooseScope(group,account=''){$('wealthGroup').value=group;syncScope();$('account').value=scopeAccounts().some(a=>a.id===account)?account:'';syncScope();page=0;refresh()}
$('wealthGroup').onchange=()=>{syncScope();page=0;refresh()};
$('account').onchange=()=>{syncScope();page=0;refresh()};
function importDates(b){const stamp=value=>value?new Date(value).toLocaleString('nl-NL',{timeZone:'Europe/Amsterdam'}):'Onbekend';return `<small>${b.imported_at?'Ge\u00efmporteerd: '+esc(stamp(b.imported_at)):'Ontvangen: '+esc(stamp(b.created_at))}${b.rolled_back_at?' | Teruggedraaid: '+esc(stamp(b.rolled_back_at)):''}</small><small>Bijgewerkt t/m: ${esc(b.last_transaction_date||'Geen gekoppelde transacties')}${b.status==='rolled_back'?' (historie; teruggedraaid)':''}${b.unresolved?' (gekoppelde transacties; open regels niet meegerekend)':''}</small>`}
$('refreshBalances').onclick=async()=>{const button=$('refreshBalances');button.disabled=true;try{await action(()=>api('/balances/refresh',{}),'Saldoverwerking aangevraagd. De voortgang staat bij Bronnen & imports.')}finally{button.disabled=!!state?.jobs?.some(j=>['pending','running'].includes(j.status))}};
function select(id,items,first){const old=$(id).value;$(id).innerHTML=first+items.map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('');$(id).value=old;if(!$(id).value)$(id).value=''}
function periodOptions(){const previous=$('month').value,years=state.years||[...new Set(state.months.map(m=>m.slice(0,4)))];$('month').innerHTML='<option value="">Alle perioden</option><option value="custom">Aangepast datumbereik</option><optgroup label="Jaren">'+years.map(y=>`<option value="year:${esc(y)}">${esc(y)}</option>`).join('')+'</optgroup><optgroup label="Maanden">'+state.months.map(m=>`<option value="${esc(m)}">${esc(m)}</option>`).join('')+'</optgroup>';if(previous&&!['','custom',...years.map(y=>'year:'+y),...state.months].includes(previous))$('month').innerHTML+=`<option value="${esc(previous)}">${esc(previous.replace('year:',''))} (huidige selectie)</option>`;$('month').value=previous}
function periodChanged(){const value=$('month').value;$('periodRange').hidden=value!=='custom';if(value==='custom'){$('periodStatus').textContent='De huidige selectie blijft actief totdat je Toepassen kiest. Beide grensdatums tellen mee.';$('dateFrom').focus();return}activePeriod=value.startsWith('year:')?{year:value.slice(5)}:value?{month:value}:{};page=0;refresh()}
$('month').onchange=periodChanged;
$('dateFrom').oninput=()=>{$('dateTo').min=$('dateFrom').value;$('dateTo').setCustomValidity('')};
$('dateTo').oninput=()=>{$('dateTo').setCustomValidity('')};
$('periodRange').onsubmit=e=>{e.preventDefault();const start=$('dateFrom').value,end=$('dateTo').value;$('dateTo').setCustomValidity(start&&end&&start>end?'De einddatum mag niet voor de begindatum liggen.':'');if(!$('periodRange').reportValidity())return;activePeriod={date_from:start,date_to:end};$('periodStatus').textContent=`Gekozen bereik: ${start} tot en met ${end}.`;page=0;refresh()};
function sortHeaders(){document.querySelectorAll('th[aria-sort]').forEach(th=>th.setAttribute('aria-sort','none'));document.querySelectorAll('[data-sort]').forEach(b=>{const active=b.dataset.sort===sort;const next=active&&direction==='asc'?'aflopend':'oplopend';b.classList.toggle('active',active);b.querySelector('span').textContent=active?(direction==='asc'?'\u2191':'\u2193'):'\u2195';b.title='Sorteer '+next;b.setAttribute('aria-label',b.childNodes[0].textContent.trim()+': sorteer '+next);if(active)b.closest('th').setAttribute('aria-sort',direction==='asc'?'ascending':'descending')})}
document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{direction=sort===b.dataset.sort?(direction==='asc'?'desc':'asc'):'asc';sort=b.dataset.sort;page=0;refresh()});
async function refresh(){const epoch=sessionEpoch,request=++refreshId;clearTimeout(timer);refreshController?.abort();const controller=new AbortController();refreshController=controller;$('filterStatus').textContent='Overzicht bijwerken...';$('transactions').setAttribute('aria-busy','true');try{const query=new URLSearchParams({account:$('account').value,group:$('wealthGroup').value,...activePeriod,category:$('category').value,transaction_type:$('transactionType').value,subcategory:$('subcategory').value,page,sort,direction});const loaded=await api('/data?'+query,undefined,undefined,controller.signal);if(epoch!==sessionEpoch||request!==refreshId)return;state=loaded;if($('account').value&&!state.accounts.some(a=>a.id===$('account').value)){$('account').value='';page=0;return refresh()}sortHeaders();$('workspace').hidden=false;$('loginPanel').hidden=true;$('lock').hidden=false;
 select('wealthGroup',(state.groups||[]).map(g=>[g.id,g.name]),'<option value="">Alle groepen (beheerd overzicht)</option><option value="unassigned">Nog indelen</option>');$('groupScope').textContent=($('wealthGroup').value==='unassigned'?'Nog indelen':state.groups?.find(g=>g.id===$('wealthGroup').value)?.name||'Alle groepen: beheerd overzicht, niet alleen eigen vermogen')+' | Actuele rekeningindeling voor alle perioden. Geen berekend vermogen of eigendomsaandeel.';
 syncScope();select('category',state.categories.filter(c=>!c.parent_id).map(c=>[c.code,c.name||c.label]),'<option value="">Alle categorieën</option><option value="uncategorized">Nog te categoriseren</option>');
 select('transactionType',(state.transaction_types||[]).map(t=>[t.code,t.name]),'<option value="">Alle typen</option>');filterSubcategories();
 for(const name of ['income','expenses'])$(name).textContent=money(state.totals[name]||0);$('transferOut').textContent=money(state.totals.transfer_out||0);$('unknownType').textContent=state.totals.unknown_type||0;
 renderBankBalances(state.bank_balances,state.jobs.some(j=>['pending','running'].includes(j.status)));
 for(const name of ['credits','debits','net'])$(name).textContent=money(state.totals[name]);$('total').textContent=state.totals.total;$('uncategorized').textContent=state.totals.uncategorized+' zonder categorie';
 $('attention').hidden=!state.unresolved;$('attentionText').textContent=state.unresolved+' importregels wachten op herkenning of controle. De bestaande betalingen kunnen al meetellen.';
 $('coverage').textContent=state.unresolved?'Onvolledig zolang mogelijke duplicaten openstaan · EUR':'Geïmporteerde boekingen · EUR · Inclusief eigen overboekingen';
 $('transactions').innerHTML=state.transactions.map((t,i)=>`<tr><td>${esc(t.booking_date)}</td><td><button data-detail="${i}">${esc(t.merchant||t.counterparty||'Onbekende tegenpartij')}<small>${esc(t.description||'Geen omschrijving')}</small></button></td><td>${esc(classificationLabel(t))}<small>${esc(typeLabel(t.transaction_type))}${!t.confirmed&&t.classification_source?' | Automatisch: '+esc(t.classification_source==='AI'?'lokale LLM':t.classification_source==='RULE'?'bankinformatie':'soortgelijke betaling'):''}</small></td><td class="money ${Number(t.amount)>=0?'positive':'negative'}">${money(t.amount)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">Nog geen boekingen voor deze selectie. Lees de XML-map in of pas je filters aan.</td></tr>';
 document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>detail(state.transactions[Number(b.dataset.detail)]));$('pageLabel').textContent=`Pagina ${page+1}`;$('previous').disabled=page===0;$('next').disabled=(page+1)*100>=Number(state.totals.total);
 $('imports').innerHTML=state.imports.map(b=>`<div class="import-row"><span class="badge ${esc(b.status)}">${esc(labels[b.status])}</span><div class="grow"><strong>Import ${esc(b.id.slice(0,8))}</strong>${importDates(b)}<small>${esc(b.records)} regels · ${esc(b.unresolved)} open · ${esc(reasons[b.reason_code]||b.reason_code||'')}</small></div><button data-source="${esc(b.source_id)}">Originele XML</button>${['partial','imported'].includes(b.status)?`<button data-rollback="${esc(b.id)}">Terugdraaien</button>`:''}</div>`).join('')||'<p class="empty">Je imports verschijnen hier, inclusief eventuele afwijzingen.</p>';
 document.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>window.open('/api/v1/finance/sources/'+b.dataset.source,'_blank','noopener'));
 document.querySelectorAll('[data-rollback]').forEach(b=>b.onclick=async()=>{if(confirm('Bijdrage van deze import terugdraaien? Bronnen en historie blijven bewaard.'))await action(()=>api('/imports/'+b.dataset.rollback+'/rollback',{confirm:true}),'Import teruggedraaid')});
 renderCategorization();
 const job=state.jobs[0];$('jobStatus').textContent=job?`${job.job_kind==='recurring'?'Terugkerend herkennen: ':job.job_kind==='categorize'?'Lokale indeling: ':job.job_kind==='references'?'ASN-herkenning: ':job.job_kind==='balances'?'Saldoverwerking: ':''}${labels[job.status]||job.status}${job.waiting_reason&&job.status!=='failed'?' · '+(reasons[job.waiting_reason]||job.waiting_reason):''}${job.error_code?' · '+(reasons[job.error_code]||job.error_code):''}`:'Geen import aangevraagd';$('import').disabled=job&&['pending','running'].includes(job.status);$('refreshBalances').disabled=!!$('import').disabled;$('reconcileDuplicates').disabled=!!$('import').disabled;clearTimeout(timer);if($('import').disabled)timer=setTimeout(refresh,10000);
 }catch(e){if(e.name!=='AbortError'&&epoch===sessionEpoch&&request===refreshId)message(e.message,true)}finally{if(epoch===sessionEpoch&&request===refreshId){$('filterStatus').textContent='';$('transactions').setAttribute('aria-busy','false')}}}
function renderCategorization(){if(!$('llmEnabled').disabled)$('llmEnabled').checked=state.llm_enabled!==false;const job=state.jobs.find(j=>j.job_kind==='categorize'),busy=state.jobs.some(j=>['pending','running'].includes(j.status));$('categorize').disabled=busy;$('stopCategorize').hidden=!job||!['pending','running'].includes(job.status);$('stopCategorize').dataset.job=job?.id||'';$('categorizationStatus').textContent=job?`${labels[job.status]||job.status} | ${job.categorization_phase==='core'?'CORE-herkenning':state.llm_enabled===false?'LLM uit':'Lokale LLM'}: ${job.processed} van ${job.target_count} verwerkt; ${job.classified} ingedeeld. ${job.waiting_reason&&job.status!=='failed'?reasons[job.waiting_reason]||job.waiting_reason:''} ${job.error_code?reasons[job.error_code]||job.error_code:''}`:'Nog geen lokale indeling gestart.'}
$('llmEnabled').onchange=async()=>{const box=$('llmEnabled'),value=box.checked,epoch=sessionEpoch;box.disabled=true;try{await action(()=>api('/classification-settings',{llm_enabled:value}),value?'Lokale LLM aan. Een wachtende job hervat automatisch.':'Lokale LLM uit. CORE blijft werken; overige betalingen wachten.')}finally{box.disabled=false;if(epoch===sessionEpoch&&state)renderCategorization()}};
$('categorize').onclick=async()=>{const button=$('categorize');button.disabled=true;try{await action(()=>api('/categorization',{}),'Lokale indeling gestart. Je eerdere beoordelingen blijven behouden.')}finally{button.disabled=!!state?.jobs?.some(j=>['pending','running'].includes(j.status))}};
$('stopCategorize').onclick=()=>action(()=>api('/categorization/'+$('stopCategorize').dataset.job+'/stop',{}),'Indeling gestopt. Al opgeslagen categorieen blijven behouden.');
async function action(fn,success){try{await fn();message(success);await refresh()}catch(e){message(e.message,true)}}
function typeLabel(code){return state?.transaction_types?.find(t=>t.code===code)?.name||'Nog niet bepaald'}
function classificationLabel(t){const main=state?.categories.find(c=>c.code===t.category_code),sub=state?.categories.find(c=>c.code===t.subcategory_code);return main?`${main.name||main.label}${sub?' / '+(sub.name||sub.label):''}`:'Nog te categoriseren'}
function filterSubcategories(){const parent=state?.categories.find(c=>c.code===$('category').value);select('subcategory',(state?.categories||[]).filter(c=>parent&&c.parent_id===parent.id).map(c=>[c.code,c.name||c.label]),'<option value="">Alle subcategorieen</option>');$('subcategory').disabled=!parent}
$('category').onchange=()=>{filterSubcategories();page=0;refresh()};
$('detail').addEventListener('close',()=>{detailEpoch++});
async function detail(t,onSaved=null){
 const epoch=sessionEpoch,request=++detailEpoch;
 $('detailBody').innerHTML=`<p class="eyebrow">TRANSACTIEDETAIL</p><h2>${esc(t.merchant||t.counterparty||'Boeking')}</h2><h2 class="${Number(t.amount)>=0?'positive':'negative'}">${money(t.amount)}</h2>
 <dl><dt>Boekdatum / valutadatum</dt><dd>${esc(t.booking_date)} / ${esc(t.value_date||'')}</dd><dt>Banktegenpartij</dt><dd>${esc(t.counterparty)}</dd><dt>Tegenrekening</dt><dd>${esc(t.counteraccount||'Niet aangeleverd')}</dd><dt>Originele bankomschrijving</dt><dd><p>${esc(t.description)}</p></dd></dl>
 <div class="classification-fields"><label>Transactietype<select id="detailType">${(state.transaction_types||[]).map(k=>`<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('')}</select></label>
 <label>Categorie<select id="detailCategory"><option value="">Nog te categoriseren</option>${state.categories.filter(c=>!c.parent_id&&(c.active||c.code===t.category_code)).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}${c.active?'':' (inactief)'}</option>`).join('')}</select></label>
 <label>Subcategorie<select id="detailSubcategory"></select></label>
 <label>Merchant (genormaliseerde naam)<input id="detailMerchant" maxlength="120" autocomplete="off" placeholder="Bijvoorbeeld: Shell"></label></div>
 <p id="typeHint" class="muted"></p><button id="applyTypeHint" type="button">Aanbevolen type overnemen</button>
 <p class="muted">De bankomschrijving blijft intact. Een herkende merchantnaam is een voorstel totdat je het oordeel opslaat.</p>
 <p id="classificationError" role="alert"></p><button id="saveCategory" class="primary">Oordeel opslaan</button>
 <p class="muted">Bron: ${esc(t.classification_source||'Nog geen oordeel')} | Bevestigd: ${t.confirmed?'ja':'nee'} | Confidence: ${esc(t.confidence??'niet bepaald')}</p>
 <p><button id="findSuggestions" ${t.category_code&&t.confirmed&&t.classification_source==='MANUAL'?'':'disabled'}>Soortgelijke betalingen voorstellen</button></p>
 <h3>Classificatiehistorie</h3><div id="classificationHistory">Laden...</div><h3>Bronbewijs</h3><div id="sources">Laden...</div>`;
 $('detailCategory').value=t.category_code||'';$('detailType').value=t.transaction_type||'UNKNOWN';$('detailMerchant').value=t.merchant||t.merchant_suggestion||'';
 function hint(){const c=state.categories.find(c=>c.code===($('detailSubcategory').value||$('detailCategory').value));$('typeHint').textContent=c?`Aanbevolen type bij deze categorie: ${typeLabel(c.transaction_type)}. Je kunt een ander type kiezen.`:'';$('applyTypeHint').disabled=!c;return c?.transaction_type}
 function subs(){const parent=state.categories.find(c=>c.code===$('detailCategory').value);$('detailSubcategory').innerHTML='<option value="">Geen subcategorie</option>'+state.categories.filter(c=>parent&&c.parent_id===parent.id&&(c.active||c.code===t.subcategory_code)).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}${c.active?'':' (inactief)'}</option>`).join('');$('detailSubcategory').disabled=!parent;hint()}
 subs();$('detailSubcategory').value=t.subcategory_code||'';hint();$('detailCategory').onchange=subs;$('detailSubcategory').onchange=hint;$('applyTypeHint').onclick=()=>{$('detailType').value=hint()||'UNKNOWN'};
 $('detail').showModal();$('findSuggestions').onclick=()=>{$('detail').close();showSuggestions(t.id)};
 let attempt=null;
 $('saveCategory').onclick=async()=>{
  const body={transaction_type:$('detailType').value,category:$('detailCategory').value,subcategory:$('detailSubcategory').value,merchant:$('detailMerchant').value,previous:t.review_id};
  const signature=JSON.stringify(body);if(!attempt||attempt.signature!==signature)attempt={signature,key:key()};
  $('saveCategory').disabled=true;$('classificationError').textContent='';
  try{await api('/transactions/'+t.id+'/classification',{...body,key:attempt.key});if(epoch!==sessionEpoch||request!==detailEpoch)return;$('detail').close();message('Classificatie opgeslagen');if(onSaved)await onSaved();else await refresh()}
  catch(e){if(epoch===sessionEpoch&&request===detailEpoch)$('classificationError').textContent=e.message}
  finally{if(epoch===sessionEpoch&&request===detailEpoch)$('saveCategory').disabled=false}
 };
 await Promise.all([
  (async()=>{try{const d=await api('/transactions/'+t.id+'/sources');if(epoch!==sessionEpoch||request!==detailEpoch)return;$('sources').innerHTML=d.sources.map(s=>`<div class="source-row">CORE document #${esc(s.file_id)} | ${esc(s.locator)}<br><a href="/api/v1/finance/sources/${esc(s.source_id)}" target="_blank" rel="noopener">Originele XML openen</a><small> | Import ${esc(s.batch_id.slice(0,8))} | ${esc(labels[s.status])}</small></div>`).join('')}catch(e){if(epoch===sessionEpoch&&request===detailEpoch)$('sources').textContent=e.message}})(),
  (async()=>{try{const d=await api('/transactions/'+t.id+'/classifications');if(epoch!==sessionEpoch||request!==detailEpoch)return;$('classificationHistory').innerHTML=d.events.map(e=>`<div class="source-row"><strong>${esc(typeLabel(e.transaction_type))} | ${esc(classificationLabel(e))}</strong><p>${esc(e.merchant||'')} | ${esc(e.classification_source)} | ${e.confirmed?'Jouw oordeel':e.actor==='finance-local'?'Automatisch ingedeeld':'Voorstel'} | Confidence: ${esc(e.confidence??'niet bepaald')}</p><small>${esc(e.created_at)}${e.suggestion_method?' | Regel: '+esc(e.suggestion_method):''}</small></div>`).join('')||'<p>Nog geen classificatie opgeslagen.</p>'}catch(e){if(epoch===sessionEpoch&&request===detailEpoch)$('classificationHistory').textContent=e.message}})()
 ]);
}
async function showSuggestions(seed){
 const epoch=sessionEpoch,request=++suggestionsEpoch;suggestionSeed=seed;suggestionsState=null;$('selectionActions').hidden=true;$('suggestionsBody').replaceChildren();$('suggestionsStatus').textContent='Lokaal vergelijken...';$('suggestionsProgress').hidden=false;$('refreshSuggestions').disabled=true;if(!$('suggestionsDialog').open)$('suggestionsDialog').showModal();
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
 try{const result=await api('/transactions/'+seed+'/suggestions',undefined,undefined,controller.signal);if(epoch!==sessionEpoch||request!==suggestionsEpoch)return;suggestionsState=result;
 const category=classificationLabel(result.classification||{category_code:result.category_code});const meaning=result.classification?`${typeLabel(result.classification.transaction_type)}${result.classification.merchant?' | '+result.classification.merchant:''}`:'';
 const reason={ovpay:'OVpay herkend in de omschrijving.',merchant_marker:'Dezelfde expliciete merchant-marker.',transfer_group_required:'Voor interne transfers moeten de bronrekening en tegenrekening bij dezelfde ingedeelde groep horen. Er wordt niets voorgesteld.',counterparty_account:'Dezelfde tegenpartij en tegenrekening.',unsupported_pattern:'Geen voldoende specifiek herkenningspatroon. Er wordt niets voorgesteld.',conflicting_examples:'Je eerdere categorieen voor dit patroon verschillen. Er wordt niets voorgesteld.'}[result.reason]||'';
 $('suggestionsStatus').textContent=`${result.from_original_example?'Gebaseerd op het oorspronkelijke handmatige oordeel. ':''}${reason} ${result.total?`${result.total} ${result.total===1?'voorstel':'voorstellen'} voor ${category}. Maximaal 50 tegelijk zichtbaar.`:'Geen voorstellen.'}`;
 $('suggestionsBody').innerHTML=result.transactions.map((t,i)=>`<article class="duplicate-card"><b>${esc(t.booking_date)} \u00b7 ${money(t.amount)} \u00b7 ${esc(t.merchant||t.counterparty||'Onbekende tegenpartij')}</b><p>${esc(t.description)}</p><small>${esc(state.accounts.find(a=>a.id===t.account_id)?.label||'Eigen rekening')}</small><p>Voorstel: <strong>${esc(category)}</strong><br>${esc(meaning)}</p><label><input type="checkbox" data-select-suggestion="${i}"> Dit voorstel selecteren</label></article>`).join('');
 document.querySelectorAll('[data-select-suggestion]').forEach(b=>b.onchange=updateSuggestionSelection);$('selectionActions').hidden=!result.transactions.length;updateSuggestionSelection();
 }catch(e){if(epoch===sessionEpoch&&request===suggestionsEpoch)$('suggestionsStatus').textContent=e.name==='AbortError'?'Het zoeken duurt te lang. Probeer Voorstellen vernieuwen. Er is niets gewijzigd.':e.message}
 finally{clearTimeout(timeout);if(epoch===sessionEpoch&&request===suggestionsEpoch){$('suggestionsProgress').hidden=true;$('refreshSuggestions').disabled=false}}
}
function updateSelectionControls(boxes,all,approve,busy=false){
 const eligible=boxes.filter(b=>!b.disabled),count=eligible.filter(b=>b.checked).length;
 all.checked=eligible.length>0&&count===eligible.length;all.indeterminate=count>0&&count<eligible.length;
 all.disabled=!eligible.length||busy;approve.disabled=!count||busy;approve.textContent=`Selectie accorderen (${count})`;
}
function updateSuggestionSelection(){
 updateSelectionControls([...document.querySelectorAll('[data-select-suggestion]')],$('selectVisibleSuggestions'),$('approveSelection'),!!suggestionsState?.busy);
}
$('selectVisibleSuggestions').onchange=()=>{document.querySelectorAll('[data-select-suggestion]').forEach(b=>b.checked=$('selectVisibleSuggestions').checked);updateSuggestionSelection()};
$('approveSelection').onclick=async()=>{
 const proposal=suggestionsState;if(!proposal||proposal.busy)return;
 const items=[...document.querySelectorAll('[data-select-suggestion]:checked')].map(b=>{const t=proposal.transactions[Number(b.dataset.selectSuggestion)];return {id:t.id,previous:t.review_id}});
 if(!items.length)return;
 const signature=JSON.stringify(items);if(proposal.selectionSignature!==signature){proposal.selectionSignature=signature;proposal.selectionKey=key()}
 const epoch=sessionEpoch,request=suggestionsEpoch;proposal.busy=true;
 const controls=[...document.querySelectorAll('#selectionActions input,#selectionActions button,[data-select-suggestion]'),$('refreshSuggestions')];controls.forEach(c=>c.disabled=true);
 try{await api('/suggestions/approve',{seed_transaction_id:proposal.seed_transaction_id,seed_review_id:proposal.seed_review_id,items,key:proposal.selectionKey});if(epoch!==sessionEpoch||request!==suggestionsEpoch)return;message(`${items.length} voorstellen geaccordeerd en auditeerbaar opgeslagen`);await refresh();if(epoch===sessionEpoch&&request===suggestionsEpoch)await showSuggestions(proposal.seed_transaction_id)}
 catch(e){if(epoch===sessionEpoch&&request===suggestionsEpoch)$('suggestionsStatus').textContent=e.message}
 finally{proposal.busy=false;if(epoch===sessionEpoch&&request===suggestionsEpoch){controls.forEach(c=>c.disabled=false);updateSuggestionSelection()}$('refreshSuggestions').disabled=false}
};
$('refreshSuggestions').onclick=()=>{if(suggestionSeed)showSuggestions(suggestionSeed)};
$('suggestionsDialog').addEventListener('close',()=>{suggestionsEpoch++;suggestionsState=null;suggestionSeed=null;$('suggestionsBody').replaceChildren();$('suggestionsStatus').textContent=''});
function duplicateComparison(r){
 const payment=p=>`<b>${esc(p.booking_date)} &middot; ${money(p.amount)}</b><p>${esc(p.counterparty||'Onbekende tegenpartij')}</p><p>${esc(p.description)}</p><small>ASN-nummer: ${esc(p.entry_reference||'Niet beschikbaar')}<br>Tegenrekening: ${esc(p.counteraccount||'Niet beschikbaar')}</small>`;
 return `<article class="duplicate-card"><div class="duplicate-comparison"><section><h3>Binnengekomen importregel</h3>${payment(r)}<p>${esc(r.locator)}</p></section><section><h3>Bestaande betalingen</h3>${r.candidates.map(c=>`<div class="duplicate-existing">${payment(c)}<p><button data-existing="${esc(c.id)}">Details en bron</button> <button data-same="${esc(c.id)}" data-record="${esc(r.id)}" ${c.can_link===false?'disabled':''}>Dit is dezelfde betaling</button></p>${c.can_link===false?'<p>Referentie of betalingsgegevens verschillen. Niet automatisch samenvoegen.</p>':''}</div>`).join('')||'<p>Geen eenduidige bestaande betaling gevonden.</p>'}</section></div><button data-distinct="${esc(r.id)}">Dit is een afzonderlijke betaling</button></article>`;
}
async function duplicates(){
 const epoch=sessionEpoch,request=++duplicateEpoch;
 $('duplicateBody').textContent='Bestaande betalingen en referenties laden...';
 if(!$('duplicates').open)$('duplicates').showModal();
 try{const d=await api('/unresolved');if(epoch!==sessionEpoch||request!==duplicateEpoch||!$('duplicates').open)return;
 $('duplicateBody').innerHTML=d.records.map(duplicateComparison).join('')||'<p>Geen openstaande gevallen.</p>';
 document.querySelectorAll('[data-same]').forEach(b=>b.onclick=()=>resolveDuplicate(b.dataset.record,'same',b.dataset.same));
 document.querySelectorAll('[data-distinct]').forEach(b=>b.onclick=()=>resolveDuplicate(b.dataset.distinct,'distinct'));
 document.querySelectorAll('[data-existing]').forEach(b=>b.onclick=()=>{const candidate=d.records.flatMap(r=>r.candidates).find(c=>c.id===b.dataset.existing);if(candidate)detail(candidate)});
 }catch(e){if(epoch===sessionEpoch&&request===duplicateEpoch&&$('duplicates').open)$('duplicateBody').textContent=e.message}
}
$('duplicates').addEventListener('close',()=>{duplicateEpoch++;$('duplicateBody').replaceChildren()});
async function resolveDuplicate(id,decision,transaction_id){
 if(!confirm('Dit duplicate-oordeel vastleggen?'))return;const epoch=sessionEpoch;
 try{await api('/unresolved/'+id,{decision,transaction_id,key:key()});if(epoch!==sessionEpoch)return;await refresh();if($('duplicates').open)await duplicates()}catch(e){if(epoch===sessionEpoch)message(e.message,true)}
}
$('reconcileDuplicates').onclick=async()=>{const button=$('reconcileDuplicates');button.disabled=true;try{await action(()=>api('/duplicates/reconcile',{}),'ASN-herkenning aangevraagd. Geen nieuwe import nodig; volg de voortgang bij Bronnen & imports.')}finally{button.disabled=!!state?.jobs?.some(j=>['pending','running'].includes(j.status))}};
function clearManagement(){managementEpoch++;managementHistoryEpoch++;managementState=null;managementAttempt=null;managementBusy=false;$('managementBody').hidden=true;$('managementStatus').textContent='';$('managementHistory').replaceChildren();for(const id of ['managedAccount','managedGroup','managedRelationship','renameGroup'])$(id).replaceChildren();for(const id of ['managedName','newGroupName','renameGroupName'])$(id).value=''}
function managementControls(busy){managementBusy=busy;document.querySelectorAll('#managementBody input,#managementBody select,#managementBody button').forEach(e=>e.disabled=busy);$('refreshManagement').disabled=busy;if(!busy){$('managedRelationship').disabled=!$('managedGroup').value;$('saveManagement').disabled=!managementState?.accounts.length;$('saveGroupName').disabled=!managementState?.groups.length}}
function groupOptions(){return '<option value="">Nog indelen</option>'+managementState.groups.map(g=>`<option value="${esc(g.id)}">${esc(g.name)}</option>`).join('')}
async function renderManagementAccount(){
 const a=managementState?.accounts.find(a=>a.id===$('managedAccount').value);managementAttempt=null;const epoch=sessionEpoch,request=managementEpoch,history=++managementHistoryEpoch;
 $('managementHistory').replaceChildren();if(!a)return;$('managedName').value=a.display_name||'';$('managedGroup').value=a.group_id||'';$('managedRelationship').value=a.relationship;$('managedRelationship').disabled=!a.group_id;
 try{const d=await api('/accounts/'+a.id+'/management-history');if(epoch!==sessionEpoch||request!==managementEpoch||history!==managementHistoryEpoch)return;$('managementHistory').innerHTML=d.events.map(e=>`<div class="source-row"><strong>${esc(e.group_id?managementState.groups.find(g=>g.id===e.group_id)?.name||'Groep':'Nog indelen')}</strong><p>${esc(managementState.relationships[e.relationship])} | ${esc(e.display_name||a.default_label)}</p><small>${esc(e.created_at)} | ${esc(e.actor)}</small></div>`).join('')||'<p>Nog geen indelingswijzigingen.</p>'}catch(e){if(epoch===sessionEpoch&&request===managementEpoch&&history===managementHistoryEpoch)$('managementHistory').textContent=e.message}
}
function renderRenameGroup(){const g=managementState?.groups.find(g=>g.id===$('renameGroup').value);$('renameGroupName').value=g?.name||'';managementAttempt=null}
async function loadManagement(preferredAccount){
 const epoch=sessionEpoch,request=++managementEpoch;managementControls(true);$('managementBody').hidden=true;$('managementStatus').textContent='Rekeningen laden...';
 try{const d=await api('/account-management');if(epoch!==sessionEpoch||request!==managementEpoch)return;managementState=d;managementAttempt=null;$('managedAccount').innerHTML=d.accounts.map(a=>`<option value="${esc(a.id)}">${esc(a.label)}</option>`).join('');if(d.accounts.some(a=>a.id===preferredAccount))$('managedAccount').value=preferredAccount;
 $('managedGroup').innerHTML=groupOptions();$('managedRelationship').innerHTML=Object.entries(d.relationships).map(([k,v])=>`<option value="${esc(k)}">${esc(v)}</option>`).join('');$('renameGroup').innerHTML=d.groups.map(g=>`<option value="${esc(g.id)}">${esc(g.name)}</option>`).join('');renderRenameGroup();$('managementBody').hidden=false;$('managementStatus').textContent=d.accounts.length?'':'Nog geen rekeningen geimporteerd.';await renderManagementAccount();
 }catch(e){if(epoch===sessionEpoch&&request===managementEpoch)$('managementStatus').textContent=e.message}
 finally{if(epoch===sessionEpoch&&request===managementEpoch)managementControls(false)}
}
async function saveManagementRequest(path,body,success){
 if(managementBusy)return;const epoch=sessionEpoch,request=managementEpoch,account=$('managedAccount').value;
 const signature=JSON.stringify([path,body]);if(managementAttempt?.signature!==signature)managementAttempt={signature,key:key()};managementControls(true);$('managementStatus').textContent='Opslaan...';
 try{await api(path,{...body,key:managementAttempt.key});if(epoch!==sessionEpoch||request!==managementEpoch)return;await refresh();if(epoch!==sessionEpoch||request!==managementEpoch)return;$('newGroupName').value='';await loadManagement(account);if(epoch===sessionEpoch&&$('accountManagementDialog').open)$('managementStatus').textContent=success}
 catch(e){if(epoch===sessionEpoch&&request===managementEpoch)$('managementStatus').textContent=e.message}
 finally{if(epoch===sessionEpoch&&request===managementEpoch)managementControls(false)}
}
$('manageAccounts').onclick=()=>{clearManagement();$('accountManagementDialog').showModal();loadManagement($('account').value)};
$('accountManagementDialog').addEventListener('close',clearManagement);
$('refreshManagement').onclick=()=>loadManagement($('managedAccount').value);
$('managedAccount').onchange=renderManagementAccount;
$('managedGroup').onchange=()=>{if(!$('managedGroup').value)$('managedRelationship').value='UNASSIGNED';$('managedRelationship').disabled=!$('managedGroup').value};
$('renameGroup').onchange=renderRenameGroup;
$('accountManagementForm').onsubmit=e=>{e.preventDefault();const a=managementState?.accounts.find(a=>a.id===$('managedAccount').value);if(a)saveManagementRequest('/accounts/'+a.id+'/management',{name:$('managedName').value,group_id:$('managedGroup').value||null,relationship:$('managedRelationship').value,previous:a.group_event_id,previous_name:a.name_event_id},'Rekening opgeslagen. Eerdere classificaties zijn behouden.')};
$('createGroupForm').onsubmit=e=>{e.preventDefault();saveManagementRequest('/wealth-groups',{name:$('newGroupName').value},'Groep toegevoegd. Je kunt nu rekeningen indelen.')};
$('renameGroupForm').onsubmit=e=>{e.preventDefault();const g=managementState?.groups.find(g=>g.id===$('renameGroup').value);if(g)saveManagementRequest('/wealth-groups/'+g.id+'/name',{name:$('renameGroupName').value,previous:g.event_id},'Groepsnaam opgeslagen.')};
function clearAccountName(){accountNameEpoch++;editingAccount=null;nameSaveAttempt=null;$('accountDisplayName').value='';$('accountNameIdentity').textContent='';$('accountNameError').textContent=''}
function editAccountName(){const account=state?.accounts.find(a=>a.id===$('account').value);if(!account)return;clearAccountName();editingAccount=account;$('accountNameIdentity').textContent=account.default_label||account.label;$('accountDisplayName').value=account.display_name||'';$('accountDisplayName').disabled=false;$('saveAccountName').disabled=false;$('resetAccountName').disabled=false;$('accountNameDialog').showModal();$('accountDisplayName').focus()}
async function saveAccountName(reset=false){
 if(!editingAccount)return;const epoch=sessionEpoch,editEpoch=accountNameEpoch,account=editingAccount,value=reset?'':$('accountDisplayName').value;
 if(!nameSaveAttempt||nameSaveAttempt.name!==value)nameSaveAttempt={name:value,previous:account.name_event_id||null,key:key()};
 $('accountNameError').textContent='';$('accountDisplayName').disabled=true;$('saveAccountName').disabled=true;$('resetAccountName').disabled=true;
 try{await api('/accounts/'+account.id+'/name',nameSaveAttempt);if(epoch!==sessionEpoch)return;if(editEpoch!==accountNameEpoch){await refresh();return}$('accountNameDialog').close();clearAccountName();message(reset||!value.trim()?'Standaardnaam hersteld':'Rekeningnaam opgeslagen');await refresh()}
 catch(e){if(epoch===sessionEpoch&&editEpoch===accountNameEpoch)$('accountNameError').textContent=e.message}
 finally{if(epoch===sessionEpoch&&editEpoch===accountNameEpoch){$('accountDisplayName').disabled=false;$('saveAccountName').disabled=false;$('resetAccountName').disabled=false}}
}
$('editAccountName').onclick=editAccountName;
$('accountNameDialog').addEventListener('close',clearAccountName);
$('accountNameForm').onsubmit=e=>{e.preventDefault();saveAccountName()};
$('resetAccountName').onclick=()=>saveAccountName(true);
// Recurring view reuses the owner session, API errors and transaction detail editor.
const recurringKindEdits=new Map();
let recurringFocus=null;
let recurringEpoch=0,recurringPage=0,recurringTimer=null,recurringAttempt=null;
const recurringLabels={monthly:'Maandelijks',quarterly:'Per kwartaal',yearly:'Jaarlijks',proposed:'Voorgesteld',confirmed:'Bevestigd',rejected:'Afgewezen',inactive:'Inactief',subscription:'Abonnement',fixed_cost:'Vaste last',periodic_transfer:'Periodieke overboeking',other_recurring:'Overig terugkerend'};
function clearRecurring(){recurringFocus=null;$('recurringReviewStatus').value='proposed';recurringKindEdits.clear();recurringEpoch++;clearTimeout(recurringTimer);recurringAttempt=null;$('recurringBody').replaceChildren();$('recurringStatus').textContent='';$('recurringAccount').replaceChildren();$('recurringProgress').hidden=true}
function recurringControls(busy){for(const id of ['recurringRefresh','recurringDetect','recurringAccount','recurringReviewStatus','recurringPrevious','recurringNext'])$(id).disabled=busy;$('recurringProgress').hidden=!busy}
async function loadRecurring(context=null){
 const epoch=sessionEpoch,request=++recurringEpoch;clearTimeout(recurringTimer);recurringControls(true);$('recurringBody').replaceChildren();$('recurringStatus').textContent='Patronen laden...';
 try{
  const data=await api('/recurring?account='+encodeURIComponent($('recurringAccount').value)+'&status='+encodeURIComponent($('recurringReviewStatus').value||'proposed')+'&page='+recurringPage+(recurringFocus?'&focus='+encodeURIComponent(recurringFocus):''));
  if(epoch!==sessionEpoch||request!==recurringEpoch)return;
  $('recurringStatus').textContent=data.patterns.length?'Bekijk de onderliggende betalingen voordat je akkoord geeft.':$('recurringReviewStatus').value==='proposed'?'Geen patronen te beoordelen. Eerder geaccordeerde patronen staan bij Bevestigd.':'Geen patronen in deze weergave.';
  $('recurringBody').innerHTML=data.patterns.map((p,i)=>{
   const account=state?.accounts.find(a=>a.id===p.account_id),kind=recurringKindEdits.get(p.id)||p.reviewed_type||p.proposed_type||p.recurring_type;
   return `<section class="panel" data-recurring-card="${esc(p.id)}"><h3>${esc(p.merchant||'Onbekende tegenpartij')}</h3><p>${esc(account?.label||'Rekening')} &middot; ${esc(recurringLabels[p.cadence]||'Niet meer herkend')} &middot; ${esc(recurringLabels[p.status])}</p>
    <p>${esc(p.typical_amount??'?')} ${esc(p.currency)} per betaling (bereik ${esc(p.amount_min??'?')} &middot; ${esc(p.amount_max??'?')}). ${esc(p.observation_count)} betalingen; herkenningsscore ${Math.round((p.confidence||0)*100)}%.</p>
    <p>Laatste betaling: ${esc(p.last_observed||'onbekend')}. Verwachte datum: ${esc(p.next_expected||'onbekend')} (schatting).</p>
    <p>Laatste waargenomen bedragwijziging: ${esc(p.price_change_percent??'onbekend')}% (${esc(p.previous_amount??'?')} naar ${esc(p.latest_amount??'?')} ${esc(p.currency)}). Dit is geen bevestigde contractwijziging.</p>
    ${(p.components||[]).length>1?'<p>Handmatig samengevoegd. Perioden kunnen overlappen of gaten bevatten; er wordt geen doorlopend ritme of forecast afgeleid.</p>':''}
    ${(p.components||[]).map(c=>`<p>${esc(c.merchant)}: ${esc(c.first_observed||'start niet bekend')} t/m ${esc(c.last_observed||'onbekend')} (${esc(c.observation_count)} betalingen) ${c.id!==p.id?`<button data-recurring-unlink="${i}" data-component="${esc(c.id)}">Losmaken</button>`:''}</p>`).join('')}
    ${p.stale?'<p>Bronnen of indelingen zijn gewijzigd. Kies Opnieuw herkennen voor actuele patronen.</p>':''}${p.new_evidence?'<p>Nieuwe detectie sinds je laatste beoordeling; je oordeel is behouden.</p>':''}
    <p>Classificatie: ${(p.classifications||[]).map(c=>`${esc(classificationLabel(c))}: ${c.count} betalingen, ${c.confirmed_count} handmatig bevestigd`).join('; ')||'Geen actieve classificaties'}</p>
    ${p.type_evidence==='confirmed_subscription_category_and_monthly_pattern'?'<p>Soortvoorstel: bevestigd als abonnement gecategoriseerde uitgaven ondersteunen het maandelijkse patroon. Bevestig het patroon afzonderlijk.</p>':''}
    <label>Soort <select data-recurring-kind="${i}">${['subscription','fixed_cost','periodic_transfer','other_recurring'].map(k=>`<option value="${k}" ${k===kind?'selected':''}>${recurringLabels[k]}</option>`).join('')}</select></label>
    ${['rejected','inactive','proposed'].map(k=>`<button data-recurring-review="${i}" data-status="${k}">${k==='confirmed'?'Bevestigen':k==='rejected'?'Afwijzen':k==='inactive'?'Inactief maken':'Heropenen'}</button>`).join('')}
    <button data-recurring-merge="${i}" ${(p.components||[]).length>1?'disabled':''}>Samenvoegen onder andere naam</button><button data-recurring-members="${i}">Instellingen en betalingen bekijken</button><div data-recurring-details="${i}"></div></section>`;
  }).join('');
  document.querySelectorAll('[data-recurring-kind]').forEach(select=>select.onchange=()=>recurringKindEdits.set(data.patterns[Number(select.dataset.recurringKind)].id,select.value));
  document.querySelectorAll('[data-recurring-review]').forEach(b=>b.onclick=()=>saveRecurring(data.patterns[Number(b.dataset.recurringReview)],b.dataset.status,document.querySelector(`[data-recurring-kind="${b.dataset.recurringReview}"]`).value));
  document.querySelectorAll('[data-recurring-merge]').forEach(b=>b.onclick=()=>loadRecurringCandidates(data.patterns[Number(b.dataset.recurringMerge)],b.dataset.recurringMerge,0,request));
  document.querySelectorAll('[data-recurring-unlink]').forEach(b=>b.onclick=()=>{const p=data.patterns[Number(b.dataset.recurringUnlink)].components.find(c=>c.id===b.dataset.component);saveRecurringLink(p,null,request)});
  document.querySelectorAll('[data-recurring-members]').forEach(b=>b.onclick=()=>loadRecurringMembers(data.patterns[Number(b.dataset.recurringMembers)],b.dataset.recurringMembers,0,request));
  recurringControls(false);$('recurringPrevious').disabled=recurringPage===0;$('recurringNext').disabled=!data.has_more;
  if(context?.id){const index=data.patterns.findIndex(p=>p.id===context.id);if(index>=0){await loadRecurringMembers(data.patterns[index],String(index),context.memberPage||0,request);if(epoch===sessionEpoch&&request===recurringEpoch){const card=document.querySelector(`[data-recurring-card="${context.id}"]`);card?.scrollIntoView({block:'nearest'});card?.querySelector('[data-recurring-kind]')?.focus({preventScroll:true})}}else $('recurringStatus').textContent='Dit patroon is niet meer beschikbaar in dit overzicht. Vernieuw de detectie.'}

 }catch(e){if(epoch===sessionEpoch&&request===recurringEpoch){recurringControls(false);$('recurringPrevious').disabled=true;$('recurringNext').disabled=true;$('recurringStatus').textContent=e.message}}
}
async function saveRecurring(pattern,status,kind){
 const epoch=sessionEpoch,request=recurringEpoch,body={detection_id:pattern.detection_id,previous:pattern.review_id,status,recurring_type:kind},signature=JSON.stringify([pattern.id,body]);
 if(recurringAttempt?.signature!==signature)recurringAttempt={signature,key:key()};
 recurringControls(true);document.querySelectorAll('[data-recurring-review]').forEach(b=>b.disabled=true);$('recurringStatus').textContent='Beoordeling opslaan...';
 try{await api('/recurring/'+pattern.id+'/review',{...body,key:recurringAttempt.key});recurringKindEdits.delete(pattern.id);if(epoch!==sessionEpoch||request!==recurringEpoch)return;recurringAttempt=null;await loadRecurring()}
 catch(e){if(epoch===sessionEpoch&&request===recurringEpoch){recurringControls(false);document.querySelectorAll('[data-recurring-review]').forEach(b=>b.disabled=false);$('recurringStatus').textContent=e.message}}
}
async function loadRecurringMembers(pattern,index,memberPage,request){
 const epoch=sessionEpoch,target=document.querySelector(`[data-recurring-details="${index}"]`);if(!target)return;const memberRequest=key();target.dataset.request=memberRequest;target.textContent='Betalingen laden...';
 try{const data=await api('/recurring/'+pattern.id+'/transactions?preview=true');if(epoch!==sessionEpoch||request!==recurringEpoch||target.dataset.request!==memberRequest)return;
  if(data.detection_id!==pattern.detection_id){target.textContent='Het patroon is bijgewerkt. Vernieuw het overzicht.';return}
  target.innerHTML=`<p>${data.total} betalingen over ${esc(data.date_from||'?')} t/m ${esc(data.date_to||'?')}. Preview: ${data.transactions.length}, verspreid over de periode. ${data.protected_count} handmatig beoordeeld.</p>
   <label>Categorie toepassen op <select data-scope><option value="none">Categorieen behouden; alleen soort bevestigen</option><option value="selected">Geselecteerde previewbetalingen</option><option value="all">Alle ${data.total} betalingen van dit patroon</option></select></label><p data-scope-summary role="status"></p>
   <div class="classification-fields"><label>Categorie<select data-category><option value="">Kies categorie</option>${state.categories.filter(c=>!c.parent_id&&c.active).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}</option>`).join('')}</select></label><label>Subcategorie<select data-subcategory><option value="">Geen subcategorie</option></select></label><label>Transactietype<select data-type>${state.transaction_types.map(t=>`<option value="${esc(t.code)}">${esc(t.name)}</option>`).join('')}</select></label></div>
   <p><label><input type="checkbox" data-overwrite> Ik wil ook geselecteerde handmatig beoordeelde betalingen wijzigen</label></p>
   <label><input type="checkbox" data-all> Alle zichtbare toegestane betalingen</label><button data-apply class="primary">Alles opslaan en akkoord</button><p data-feedback role="status"></p>`+
   (data.transactions.map((t,i)=>`<p><input type="checkbox" data-pick="${i}" aria-label="Betaling ${esc(t.booking_date)} selecteren" ${t.confirmed?'disabled':''}> <button data-member="${i}">${esc(t.booking_date)} &middot; ${esc(t.amount)} ${esc(t.currency)} &middot; ${esc(classificationLabel(t))}</button> ${t.confirmed?'Handmatig bevestigd':'Niet handmatig bevestigd'}</p>`).join('')||'<p>Geen actieve bronbetalingen.</p>');
  target.querySelectorAll('[data-member]').forEach(b=>b.onclick=()=>detail(data.transactions[Number(b.dataset.member)],()=>epoch===sessionEpoch&&request===recurringEpoch?loadRecurring({id:pattern.id,memberPage}):undefined));
  bindRecurringClassification(target,pattern,data,()=>epoch===sessionEpoch&&request===recurringEpoch&&target.dataset.request===memberRequest,async()=>{recurringKindEdits.delete(pattern.id);await loadRecurring();$('recurringStatus').textContent='Alles opgeslagen en akkoord. Het patroon staat bij Bevestigd.'});
 }catch(e){if(epoch===sessionEpoch&&request===recurringEpoch&&target.dataset.request===memberRequest)target.textContent=e.message}
}
function bindRecurringClassification(target,pattern,data,current,reload){
 const transactions=data.transactions,q=s=>target.querySelector(s),boxes=[...target.querySelectorAll('[data-pick]')];let busy=false,attempt=null;
 const update=()=>{
  const scope=q('[data-scope]').value,overwrite=q('[data-overwrite]').checked;
  boxes.forEach(b=>{b.disabled=scope!=='selected'||(transactions[Number(b.dataset.pick)].confirmed&&!overwrite);if(b.disabled)b.checked=false});
  updateSelectionControls(boxes,q('[data-all]'),q('[data-apply]'),busy);
  const count=boxes.filter(b=>b.checked&&!b.disabled).length;
  q('[data-category]').disabled=busy||scope==='none';q('[data-subcategory]').disabled=busy||scope==='none';q('[data-type]').disabled=busy||scope==='none';q('[data-overwrite]').disabled=busy||scope==='none';
  q('[data-apply]').textContent='Alles opslaan en akkoord';q('[data-apply]').disabled=busy||(scope!=='none'&&!q('[data-category]').value)||(scope==='selected'&&!count);
  q('[data-scope-summary]').textContent=scope==='none'?'Categorieen blijven behouden. Je bevestigt de gekozen soort.':scope==='all'?`Categorie toepassen op ${overwrite?data.total:data.total-data.protected_count} van ${data.total} betalingen, ook buiten de preview. ${overwrite?'Geselecteerde toestemming geldt ook voor handmatige oordelen.':data.protected_count+' handmatige beoordelingen blijven behouden.'}`:`Categorie toepassen op ${count} aangevinkte previewbetalingen. Andere betalingen blijven behouden.`;
 };
 q('[data-category]').onchange=()=>{const parent=state.categories.find(c=>c.code===q('[data-category]').value);q('[data-subcategory]').innerHTML='<option value="">Geen subcategorie</option>'+state.categories.filter(c=>parent&&c.active&&c.parent_id===parent.id).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}</option>`).join('');if(parent)q('[data-type]').value=parent.transaction_type;update()};
 q('[data-subcategory]').onchange=()=>{const child=state.categories.find(c=>c.code===q('[data-subcategory]').value);if(child)q('[data-type]').value=child.transaction_type};
 q('[data-overwrite]').onchange=update;q('[data-scope]').onchange=update;
 boxes.forEach(b=>b.onchange=update);q('[data-all]').onchange=()=>{boxes.filter(b=>!b.disabled).forEach(b=>b.checked=q('[data-all]').checked);update()};
 if(data.classification?.category_code&&state.categories.some(c=>c.active&&c.code===data.classification.category_code)){
  q('[data-category]').value=data.classification.category_code;q('[data-category]').onchange();q('[data-subcategory]').value=data.classification.subcategory_code||'';q('[data-type]').value=data.classification.transaction_type;
 }
 q('[data-apply]').onclick=async()=>{
  if(busy||q('[data-apply]').disabled)return;
  const scope=q('[data-scope]').value,items=boxes.filter(b=>b.checked&&!b.disabled).map(b=>{const t=transactions[Number(b.dataset.pick)];return {id:t.id,previous:t.review_id}});
  const classification=scope==='none'?null:{scope,category:q('[data-category]').value,subcategory:q('[data-subcategory]').value,transaction_type:q('[data-type]').value,overwrite:q('[data-overwrite]').checked,...(scope==='selected'?{items}:{})};
  const kind=target.closest('[data-recurring-card]').querySelector('[data-recurring-kind]').value;
  const body={detection_id:pattern.detection_id,previous:pattern.review_id,recurring_type:kind,snapshot:data.snapshot,classification},signature=JSON.stringify(body);
  if(attempt?.signature!==signature)attempt={signature,key:key()};busy=true;
  const controls=[...target.closest('[data-recurring-card]').querySelectorAll('input,select,button')],disabled=controls.map(c=>c.disabled);controls.forEach(c=>c.disabled=true);q('[data-feedback]').textContent='Alle instellingen opslaan...';
  try{await api('/recurring/'+pattern.id+'/approve',{...body,key:attempt.key});if(!current())return;attempt=null;await reload()}
  catch(e){if(current())q('[data-feedback]').textContent=e.message}
  finally{busy=false;if(current()){controls.forEach((c,i)=>c.disabled=disabled[i]);update()}}
 };
 update();
}
async function saveRecurringLink(pattern,parent,request){
 const epoch=sessionEpoch,body={parent_id:parent,previous:pattern.link_id},signature=JSON.stringify([pattern.id,body]);
 if(recurringAttempt?.signature!==signature)recurringAttempt={signature,key:key()};recurringControls(true);$('recurringStatus').textContent='Koppeling opslaan...';
 try{await api('/recurring/'+pattern.id+'/link',{...body,key:recurringAttempt.key});if(epoch!==sessionEpoch||request!==recurringEpoch)return;recurringAttempt=null;recurringPage=0;recurringFocus=parent||pattern.id;$('recurringReviewStatus').value='all';await loadRecurring({id:recurringFocus})}
 catch(e){if(epoch===sessionEpoch&&request===recurringEpoch){recurringControls(false);$('recurringStatus').textContent=e.message}}
}
async function loadRecurringCandidates(pattern,index,candidatePage,request){
 const epoch=sessionEpoch,target=document.querySelector(`[data-recurring-details="${index}"]`);if(!target)return;
 const memberRequest=key();target.dataset.request=memberRequest;target.textContent='Patronen op deze rekening laden...';
 try{const data=await api('/recurring?account='+pattern.account_id+'&status=all&page='+candidatePage);if(epoch!==sessionEpoch||request!==recurringEpoch||target.dataset.request!==memberRequest)return;
  const candidates=data.patterns.filter(p=>p.id!==pattern.id&&p.direction===pattern.direction&&p.currency===pattern.currency);
  target.innerHTML='<p>Kies onder welke naam je deze betalingen wilt groeperen. Controleer omschrijving, ritme en perioden. Dit wijzigt geen bronbetalingen of categorieen.</p>'+candidates.map((p,i)=>`<p><button data-join="${i}">Samenvoegen onder ${esc(p.merchant)}</button> ${esc(recurringLabels[p.cadence]||'Meerdere ritmes')} &middot; laatste betaling ${esc(p.last_observed||'?')} &middot; ${esc(p.typical_amount)} ${esc(p.currency)}</p>`).join('');
  target.querySelectorAll('[data-join]').forEach(b=>b.onclick=()=>saveRecurringLink(pattern,candidates[Number(b.dataset.join)].id,request));
  for(const [label,destination] of [['Vorige patronen',candidatePage-1],['Volgende patronen',data.has_more?candidatePage+1:-1]])if(destination>=0){const b=document.createElement('button');b.textContent=label;b.onclick=()=>loadRecurringCandidates(pattern,index,destination,request);target.append(b)}
 }catch(e){if(epoch===sessionEpoch&&request===recurringEpoch&&target.dataset.request===memberRequest)target.textContent=e.message}
}
$('showRecurring').onclick=()=>{clearRecurring();recurringPage=0;$('recurringAccount').innerHTML='<option value="">Alle rekeningen</option>'+state.accounts.map(a=>`<option value="${esc(a.id)}">${esc(a.label)}</option>`).join('');$('recurringAccount').value=$('account').value;$('recurringDialog').showModal();loadRecurring()};
$('recurringDialog').addEventListener('close',clearRecurring);
$('recurringRefresh').onclick=()=>loadRecurring();for(const id of ['recurringAccount','recurringReviewStatus'])$(id).onchange=()=>{recurringPage=0;recurringFocus=null;loadRecurring()};
$('recurringPrevious').onclick=()=>{recurringPage--;loadRecurring()};$('recurringNext').onclick=()=>{recurringPage++;loadRecurring()};
$('recurringDetect').onclick=async()=>{const epoch=sessionEpoch,request=recurringEpoch;recurringControls(true);$('recurringStatus').textContent='Herkenning aanvragen...';try{await api('/recurring/detect',{});if(epoch!==sessionEpoch||request!==recurringEpoch)return;$('recurringStatus').textContent='Herkenning aangevraagd voor alle rekeningen. Verwerking wacht zo nodig op NAS-capaciteit. Vernieuw na voltooiing; de voortgang staat bij Imports en in CORE Pulse.';await refresh()}catch(e){if(epoch===sessionEpoch&&request===recurringEpoch)$('recurringStatus').textContent=e.message}finally{if(epoch===sessionEpoch&&request===recurringEpoch)recurringControls(false)}};
// End recurring view.
 $('login').onsubmit=async e=>{e.preventDefault();const code=$('accessCode').value;$('accessCode').value='';await action(()=>api('/session',{code}),'Finance ontgrendeld');if(state)armLock()};$('lock').onclick=async()=>{try{await api('/session',{},'DELETE')}finally{locked();message('Finance vergrendeld')}};$('refresh').onclick=refresh;$('import').onclick=()=>action(()=>api('/import',{}),'Import aangevraagd. Verwerking wacht zo nodig op NAS-capaciteit.');$('reviewDuplicates').onclick=duplicates;for(const id of ['transactionType','subcategory'])$(id).onchange=()=>{page=0;refresh()};$('previous').onclick=()=>{page--;refresh()};$('next').onclick=()=>{page++;refresh()};armLock();refresh();
})();
