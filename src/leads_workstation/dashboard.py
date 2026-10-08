DASHBOARD_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codestra Leads Workstation V2</title>
<link rel="stylesheet" href="/assets/dashboard.css">
</head>
<body>
<header>
  <div>
    <h1>Codestra Leads Workstation <span>V2</span></h1>
    <p>Campaign-aware lead operations, verification, compliance and delivery.</p>
  </div>
  <div id="connection" class="pill">Not authenticated</div>
</header>
<section id="authbar">
  <select id="authMode">
    <option value="dev">Development headers</option>
    <option value="bearer">Bearer token</option>
  </select>
  <input id="devUser" placeholder="Dev user" value="supervisor-dev">
  <input id="devRoles" placeholder="Roles" value="supervisor">
  <input id="devCampaigns" placeholder="Campaign IDs (comma-separated)">
  <input id="bearer" type="password" placeholder="Bearer token (memory only)">
  <button id="connectBtn">Connect</button>
</section>
<nav>
  <button data-view="overview" class="active">Overview</button>
  <button data-view="leads">All Leads</button>
  <button data-view="kanban">Kanban</button>
  <button data-view="campaigns">Campaigns</button>
  <button data-view="candidates">Candidates</button>
  <button data-view="outbox">Outbox</button>
  <button data-view="focus">Lead Focus</button>
</nav>
<main>
  <section id="filters">
    <input id="search" placeholder="Search business, contact, email, phone">
    <select id="country"><option value="">All countries</option></select>
    <select id="status"><option value="">All statuses</option></select>
    <select id="campaign"><option value="">All campaigns</option></select>
    <button id="applyFilters">Apply</button>
    <button id="clearFilters" class="secondary">Clear</button>
  </section>
  <div id="error" class="error hidden"></div>
  <section id="view"></section>
</main>
<script src="/assets/dashboard.js"></script>
</body>
</html>"""

DASHBOARD_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#161616;background:#f5f6f8}
*{box-sizing:border-box}body{margin:0}header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 24px;background:#fff;border-bottom:1px solid #ddd}
h1{margin:0;font-size:22px}h1 span{font-size:12px;border:1px solid #bbb;border-radius:999px;padding:2px 7px}header p{margin:4px 0 0;color:#666;font-size:13px}
#authbar,#filters,nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 24px;background:#fff;border-bottom:1px solid #e5e5e5}
input,select,button{font:inherit;border:1px solid #cfcfcf;border-radius:7px;padding:8px 10px;background:#fff}input{min-width:160px}#search{min-width:300px}
button{cursor:pointer}button.active,button.primary{background:#171717;color:#fff;border-color:#171717}.secondary{background:#f4f4f4}
main{padding:22px 24px}.pill,.badge{display:inline-block;border:1px solid #ccc;border-radius:999px;padding:4px 9px;font-size:12px}.pill.ok{border-color:#1b7f45;color:#1b7f45}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:18px}.card,.panel{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px}.metric{font-size:28px;font-weight:700}.muted{color:#6a6a6a}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden}th,td{padding:9px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;font-size:13px}th{background:#fafafa}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.column{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px}.lead{border:1px solid #e5e5e5;border-radius:8px;padding:9px;margin:7px 0;cursor:pointer}
.error{padding:12px;border:1px solid #b42318;background:#fff1f0;color:#8a1c13;border-radius:8px;margin:10px 0}.hidden{display:none}pre{white-space:pre-wrap;word-break:break-word;background:#111;color:#eee;padding:12px;border-radius:8px;max-height:460px;overflow:auto}
.actions{display:flex;gap:8px;flex-wrap:wrap}.linkbtn{border:0;background:transparent;text-decoration:underline;padding:0;color:#155eef}.status-DNC{font-weight:700}.right{text-align:right}
@media(max-width:720px){header{align-items:flex-start;flex-direction:column}#authbar input,#authbar select,#filters input,#filters select{width:100%;min-width:0}}
"""

DASHBOARD_JS = r"""
const state={view:'overview',auth:{mode:'dev'},stats:null,leads:[],campaigns:[],candidates:[],outbox:[],focus:null};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function headers(){
  const h={'Accept':'application/json'};
  if(state.auth.mode==='bearer'){if(state.auth.token)h.Authorization='Bearer '+state.auth.token}
  else{
    h['X-Dev-User']=state.auth.user||'';
    h['X-Dev-Roles']=state.auth.roles||'';
    h['X-Dev-Campaigns']=state.auth.campaigns||'';
  }
  return h;
}
async function api(path,options={}){
  const opts={...options,headers:{...headers(),...(options.headers||{})}};
  if(options.body&&typeof options.body!=='string'){opts.body=JSON.stringify(options.body);opts.headers['Content-Type']='application/json'}
  const r=await fetch(path,opts);
  let body=null;try{body=await r.json()}catch{body={error:'invalid_response'}}
  if(!r.ok){throw new Error((body&&body.detail)||body.error||('HTTP '+r.status))}
  return {body,headers:r.headers};
}
function showError(e){$('error').textContent=e.message||String(e);$('error').classList.remove('hidden')}
function clearError(){$('error').classList.add('hidden')}
function setConnection(ok,text){const el=$('connection');el.textContent=text;el.classList.toggle('ok',ok)}
function fillSelect(id,values,label=''){
  const el=$(id),cur=el.value;const first='<option value="">All '+(label||id)+'</option>';
  el.innerHTML=first+values.map(v=>'<option value="'+esc(v.value)+'">'+esc(v.label)+'</option>').join('');el.value=cur;
}
async function loadAll(){
  clearError();
  try{
    const me=await api('/api/v2/me');setConnection(true,me.body.subject+' · '+me.body.roles.join(', '));
    const tasks=[
      api('/api/v2/campaigns').catch(()=>({body:{items:[]}})),
      api('/api/v2/leads?limit=200').catch(()=>({body:{items:[]}})),
      api('/api/v2/candidates?limit=200').catch(()=>({body:{items:[]}})),
      api('/api/v2/outbox?limit=100').catch(()=>({body:{items:[]}})),
      api('/api/v2/stats').catch(()=>({body:null}))
    ];
    const [campaigns,leads,candidates,outbox,stats]=await Promise.all(tasks);
    state.campaigns=campaigns.body.items||[];state.leads=leads.body.items||[];state.candidates=candidates.body.items||[];state.outbox=outbox.body.items||[];state.stats=stats.body;
    fillSelect('campaign',state.campaigns.map(x=>({value:x.campaign_id,label:x.campaign_code+' — '+x.name})),'campaigns');
    fillSelect('country',[...new Set(state.leads.map(x=>x.country).filter(Boolean))].sort().map(x=>({value:x,label:x})),'countries');
    fillSelect('status',[...new Set(state.leads.map(x=>x.status).filter(Boolean))].sort().map(x=>({value:x,label:x})),'statuses');
    render();
  }catch(e){setConnection(false,'Authentication failed');showError(e)}
}
async function loadLeads(){
  const p=new URLSearchParams({limit:'200'});
  if($('search').value)p.set('q',$('search').value);
  if($('country').value)p.set('country',$('country').value);
  if($('status').value)p.set('status',$('status').value);
  if($('campaign').value)p.set('campaign_id',$('campaign').value);
  const r=await api('/api/v2/leads?'+p);state.leads=r.body.items||[];render();
}
function cards(){
  const s=state.stats||{};
  const vals=[
    ['Leads',s.total_leads??state.leads.length],
    ['With email',s.with_email??'—'],
    ['With phone',s.with_phone??'—'],
    ['Campaigns',s.campaign_count??state.campaigns.length],
    ['Suppressed',s.suppressed??'—'],
    ['DNC',s.do_not_contact??'—'],
    ['Pending outbox',s.pending_outbox??state.outbox.filter(x=>x.status==='pending').length],
    ['Candidates',state.candidates.length]
  ];
  return '<div class="cards">'+vals.map(v=>'<div class="card"><div class="metric">'+esc(v[1])+'</div><div class="muted">'+esc(v[0])+'</div></div>').join('')+'</div>';
}
function leadTable(items){
  if(!items.length)return '<div class="panel muted">No leads in this result.</div>';
  return '<table><thead><tr><th>Business / Contact</th><th>Country</th><th>Campaign</th><th>Status</th><th>Agent</th><th>Verification</th><th>Contact</th><th>v</th></tr></thead><tbody>'+
  items.map(x=>'<tr><td><button class="linkbtn focus" data-id="'+esc(x.lead_id)+'">'+esc(x.business_name)+'</button><br><span class="muted">'+esc(x.contact_name)+'</span></td><td>'+esc(x.country)+'</td><td>'+esc(x.campaign_id)+'</td><td class="status-'+esc(x.status)+'">'+esc(x.status)+'</td><td>'+esc(x.assigned_agent)+'</td><td>'+esc(x.verification_status)+'</td><td>'+esc(x.email)+'<br>'+esc(x.phone)+'</td><td>'+esc(x.version)+'</td></tr>').join('')+'</tbody></table>';
}
function grouped(key){const g={};for(const x of state.leads){const k=x[key]||'Unassigned';(g[k]??=[]).push(x)}return Object.entries(g).sort((a,b)=>b[1].length-a[1].length)}
function render(){
  const v=$('view');
  if(state.view==='overview'){
    const statuses=(state.stats&&state.stats.statuses)||[];
    v.innerHTML=cards()+'<div class="grid"><div class="panel"><h3>Lifecycle</h3>'+statuses.slice(0,15).map(x=>'<div>'+esc(x.status)+' <b>'+esc(x.count)+'</b></div>').join('')+'</div><div class="panel"><h3>Campaigns</h3>'+state.campaigns.slice(0,12).map(x=>'<div><b>'+esc(x.campaign_code)+'</b> '+esc(x.name)+' <span class="badge">'+esc(x.state)+'</span></div>').join('')+'</div></div>';
  }else if(state.view==='leads'){v.innerHTML='<h2>Leads</h2>'+leadTable(state.leads)}
  else if(state.view==='kanban'){v.innerHTML='<h2>Lifecycle Kanban</h2><div class="grid">'+grouped('status').map(([k,rows])=>'<div class="column"><h3>'+esc(k)+' ('+rows.length+')</h3>'+rows.slice(0,100).map(x=>'<div class="lead focus" data-id="'+esc(x.lead_id)+'"><b>'+esc(x.business_name)+'</b><br><span class="muted">'+esc(x.assigned_agent||'Unassigned')+'</span></div>').join('')+'</div>').join('')+'</div>'}
  else if(state.view==='campaigns'){v.innerHTML='<h2>Campaigns</h2><table><thead><tr><th>Code</th><th>Name</th><th>Type</th><th>State</th><th>Supervisor</th><th>Dates</th></tr></thead><tbody>'+state.campaigns.map(x=>'<tr><td>'+esc(x.campaign_code)+'</td><td>'+esc(x.name)+'</td><td>'+esc(x.campaign_type)+'</td><td>'+esc(x.state)+'</td><td>'+esc(x.primary_supervisor)+'</td><td>'+esc(x.start_at)+'<br>'+esc(x.end_at)+'</td></tr>').join('')+'</tbody></table>'}
  else if(state.view==='candidates'){v.innerHTML='<h2>Candidate Review</h2><table><thead><tr><th>Name</th><th>Country</th><th>Category</th><th>Disposition</th><th>Match</th><th>Reason</th></tr></thead><tbody>'+state.candidates.map(x=>'<tr><td>'+esc(x.business_name)+'</td><td>'+esc(x.country)+'</td><td>'+esc(x.business_category)+'</td><td>'+esc(x.disposition)+'</td><td>'+esc(x.match_lead_id)+'</td><td>'+esc(x.match_reason)+'</td></tr>').join('')+'</tbody></table>'}
  else if(state.view==='outbox'){v.innerHTML='<h2>Outbox</h2><table><thead><tr><th>Event</th><th>Aggregate</th><th>Status</th><th>Attempts</th><th>Created</th><th>Error</th></tr></thead><tbody>'+state.outbox.map(x=>'<tr><td>'+esc(x.event_type)+'</td><td>'+esc(x.aggregate_type)+'<br>'+esc(x.aggregate_id)+'</td><td>'+esc(x.status)+'</td><td>'+esc(x.attempt_count)+'</td><td>'+esc(x.created_at)+'</td><td>'+esc(x.last_error)+'</td></tr>').join('')+'</tbody></table>'}
  else if(state.view==='focus'){v.innerHTML=state.focus?focusHtml(state.focus):'<div class="panel">Select a lead from All Leads or Kanban.</div>'}
  bindFocus();
}
function focusHtml(x){
  return '<h2>Lead Focus</h2><div class="panel"><h3>'+esc(x.lead.business_name)+'</h3><div class="actions"><span class="badge">'+esc(x.lead.status)+'</span><span class="badge">'+esc(x.lead.country)+'</span><span class="badge">v'+esc(x.lead.version)+'</span></div><p>'+esc(x.lead.contact_name)+'</p><h4>Contact points</h4><pre>'+esc(JSON.stringify(x.contacts,null,2))+'</pre><h4>Assignments</h4><pre>'+esc(JSON.stringify(x.assignments,null,2))+'</pre><h4>Transitions</h4><pre>'+esc(JSON.stringify(x.transitions,null,2))+'</pre></div>';
}
function bindFocus(){document.querySelectorAll('.focus').forEach(el=>el.onclick=async()=>{try{const id=el.dataset.id;const [lead,contacts,assignments,transitions]=await Promise.all([api('/api/v2/leads/'+encodeURIComponent(id)),api('/api/v2/leads/'+encodeURIComponent(id)+'/contacts'),api('/api/v2/leads/'+encodeURIComponent(id)+'/assignments').catch(()=>({body:{items:[]}})),api('/api/v2/leads/'+encodeURIComponent(id)+'/transitions').catch(()=>({body:{items:[]}}))]);state.focus={lead:lead.body,contacts:contacts.body.items||[],assignments:assignments.body.items||[],transitions:transitions.body.items||[]};setView('focus')}catch(e){showError(e)}})}
function setView(name){state.view=name;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===name));render()}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('connectBtn').onclick=()=>{state.auth.mode=$('authMode').value;state.auth.user=$('devUser').value;state.auth.roles=$('devRoles').value;state.auth.campaigns=$('devCampaigns').value;state.auth.token=$('bearer').value;loadAll()};
$('applyFilters').onclick=()=>loadLeads().catch(showError);
$('clearFilters').onclick=()=>{for(const id of ['search','country','status','campaign'])$(id).value='';loadLeads().catch(showError)};
$('authMode').onchange=()=>{const bearer=$('authMode').value==='bearer';$('bearer').style.display=bearer?'block':'none';for(const id of ['devUser','devRoles','devCampaigns'])$(id).style.display=bearer?'none':'block'};
$('bearer').style.display='none';
"""
