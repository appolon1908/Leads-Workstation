DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codestra Leads Workstation V2</title>
<link rel="stylesheet" href="/assets/dashboard.css">
</head>
<body>
<div class="app-shell">
  <aside class="sidebar" aria-label="Primary">
    <div class="brand">
      <div class="brand-mark">C</div>
      <div>
        <strong>Leads Workstation</strong>
        <span>Codestra V2</span>
      </div>
    </div>
    <nav id="nav" class="side-nav">
      <button data-view="overview" class="active"><span>Overview</span></button>
      <button data-view="leads"><span>All Leads</span></button>
      <button data-view="kanban"><span>Kanban</span></button>
      <button data-view="campaigns"><span>Campaigns</span></button>
      <button data-view="candidates"><span>Candidates</span></button>
      <button data-view="integrations"><span>Integrations</span></button>
    </nav>
    <div class="sidebar-foot">
      <button id="sessionBtn" class="ghost wide">Session & access</button>
      <div id="connection" class="connection">Not authenticated</div>
    </div>
  </aside>

  <section class="workspace">
    <header class="topbar">
      <div>
        <div class="eyebrow" id="viewEyebrow">Lead operations</div>
        <h1 id="viewTitle">Overview</h1>
      </div>
      <div class="top-actions">
        <button id="refreshBtn" class="secondary">Refresh</button>
        <button id="newLeadBtn" class="primary hidden">+ New lead</button>
      </div>
    </header>

    <section id="authPanel" class="auth-panel">
      <div class="auth-copy">
        <strong>Connect to Leads Workstation</strong>
        <span>Development headers are loopback-only. Bearer mode keeps the token in browser memory only.</span>
      </div>
      <div class="auth-controls">
        <select id="authMode" aria-label="Authentication mode">
          <option value="dev">Development headers</option>
          <option value="bearer">Bearer token</option>
        </select>
        <input id="devUser" placeholder="Dev user" value="admin-dev" autocomplete="off">
        <input id="devRoles" placeholder="Roles" value="admin" autocomplete="off">
        <input id="devCampaigns" placeholder="Campaign IDs" autocomplete="off">
        <input id="bearer" type="password" placeholder="Bearer token" autocomplete="off">
        <button id="connectBtn" class="primary">Connect</button>
      </div>
    </section>

    <main>
      <section id="filterBar" class="filter-bar hidden">
        <div class="search-wrap">
          <input id="search" type="search" placeholder="Search business, contact, email or phone">
        </div>
        <select id="country"><option value="">All countries</option></select>
        <select id="status"><option value="">All statuses</option></select>
        <select id="campaign"><option value="">All campaigns</option></select>
        <button id="applyFilters" class="secondary">Apply</button>
        <button id="clearFilters" class="ghost">Clear</button>
      </section>

      <div id="notice" class="notice hidden" role="status"></div>
      <div id="error" class="error hidden" role="alert"></div>
      <section id="view" class="view-host"></section>
    </main>
  </section>
</div>

<div id="drawerBackdrop" class="backdrop hidden"></div>
<aside id="drawer" class="drawer" aria-label="Details" aria-hidden="true">
  <div class="drawer-head">
    <div>
      <div class="eyebrow" id="drawerEyebrow">Details</div>
      <h2 id="drawerTitle">Record</h2>
    </div>
    <button id="drawerClose" class="icon-btn" aria-label="Close details">×</button>
  </div>
  <div id="drawerBody" class="drawer-body"></div>
</aside>

<dialog id="modal">
  <form method="dialog" id="modalForm">
    <div class="modal-head">
      <div>
        <div class="eyebrow" id="modalEyebrow">Action</div>
        <h2 id="modalTitle">Action</h2>
      </div>
      <button type="button" id="modalClose" class="icon-btn" aria-label="Close">×</button>
    </div>
    <div id="modalBody" class="modal-body"></div>
    <div class="modal-actions">
      <button type="button" id="modalCancel" class="secondary">Cancel</button>
      <button type="submit" id="modalSubmit" class="primary">Save</button>
    </div>
  </form>
</dialog>

<script src="/assets/dashboard.js"></script>
</body>
</html>"""

DASHBOARD_CSS = """
:root{
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:#182230;background:#f5f7fa;font-synthesis:none;
  --ink:#182230;--muted:#667085;--line:#e4e7ec;--panel:#fff;--soft:#f8fafc;
  --brand:#101828;--brand2:#344054;--accent:#175cd3;--success:#067647;
  --warning:#b54708;--danger:#b42318;--radius:14px;--shadow:0 12px 36px rgba(16,24,40,.12)
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#f5f7fa}
button,input,select,textarea{font:inherit}
button{cursor:pointer}
button:disabled{cursor:not-allowed;opacity:.45}
input,select,textarea{
  width:100%;border:1px solid #d0d5dd;border-radius:9px;background:#fff;color:var(--ink);
  padding:9px 11px;outline:none;transition:border-color .15s,box-shadow .15s
}
input:focus,select:focus,textarea:focus{border-color:#84adff;box-shadow:0 0 0 3px rgba(23,92,211,.12)}
textarea{min-height:90px;resize:vertical}
.app-shell{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}
.sidebar{
  position:sticky;top:0;height:100vh;background:#0c111d;color:#fff;padding:22px 14px;
  display:flex;flex-direction:column;border-right:1px solid #1d2939
}
.brand{display:flex;gap:11px;align-items:center;padding:0 8px 24px}
.brand-mark{
  width:36px;height:36px;border-radius:10px;background:#fff;color:#101828;
  display:grid;place-items:center;font-weight:800
}
.brand strong{display:block;font-size:14px}.brand span{display:block;color:#98a2b3;font-size:12px;margin-top:2px}
.side-nav{display:flex;flex-direction:column;gap:4px}
.side-nav button{
  border:0;background:transparent;color:#d0d5dd;text-align:left;padding:10px 12px;border-radius:8px;
  font-weight:600
}
.side-nav button:hover{background:#1d2939;color:#fff}
.side-nav button.active{background:#344054;color:#fff}
.sidebar-foot{margin-top:auto;border-top:1px solid #1d2939;padding-top:14px}
.connection{font-size:11px;color:#98a2b3;padding:9px 3px 0;line-height:1.4}
.connection.ok{color:#75e0a7}
.workspace{min-width:0}
.topbar{
  height:82px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;
  justify-content:space-between;padding:0 28px;position:sticky;top:0;z-index:10
}
.eyebrow{text-transform:uppercase;letter-spacing:.08em;color:#667085;font-size:10px;font-weight:700}
h1,h2,h3,h4,p{margin-top:0}
h1{font-size:24px;margin:3px 0 0}h2{font-size:20px;margin:3px 0 0}h3{font-size:15px}
.top-actions,.actions,.inline-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
button.primary,button.secondary,button.ghost,button.danger{
  border-radius:8px;padding:8px 11px;font-weight:650;border:1px solid transparent
}
button.primary{background:#175cd3;color:#fff;border-color:#175cd3}
button.primary:hover{background:#1849a9}
button.secondary{background:#fff;border-color:#d0d5dd;color:#344054}
button.secondary:hover{background:#f9fafb}
button.ghost{background:transparent;color:#475467}
.sidebar button.ghost{color:#d0d5dd;border:1px solid #344054}
button.danger{background:#fff1f0;color:#b42318;border-color:#fecdca}
button.small{padding:5px 8px;font-size:12px}
button.wide{width:100%}
.icon-btn{width:34px;height:34px;border:0;border-radius:8px;background:#f2f4f7;font-size:22px;line-height:1}
.auth-panel{
  display:flex;gap:16px;align-items:center;justify-content:space-between;background:#fffaeb;
  border-bottom:1px solid #fedf89;padding:12px 28px
}
.auth-copy{min-width:220px}.auth-copy strong{display:block;font-size:13px}.auth-copy span{display:block;color:#7a2e0e;font-size:11px;margin-top:2px}
.auth-controls{display:flex;gap:7px;align-items:center;flex:1;justify-content:flex-end}
.auth-controls input,.auth-controls select{max-width:200px}
main{padding:22px 28px 44px}
.filter-bar{
  display:grid;grid-template-columns:minmax(240px,1fr) 160px 160px 200px auto auto;
  gap:8px;margin-bottom:16px
}
.notice,.error{padding:11px 13px;border-radius:9px;margin-bottom:14px;font-size:13px}
.notice{background:#ecfdf3;border:1px solid #abefc6;color:#05603a}
.error{background:#fff1f0;border:1px solid #fecdca;color:#912018}
.hidden{display:none!important}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:11px;margin-bottom:18px}
.metric-card{
  background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:15px;text-align:left;
  transition:transform .14s,border-color .14s,box-shadow .14s
}
button.metric-card{width:100%}
button.metric-card:hover{transform:translateY(-1px);border-color:#b2ccff;box-shadow:0 8px 22px rgba(16,24,40,.07)}
.metric{font-size:27px;font-weight:750;letter-spacing:-.02em}.metric-label{font-size:12px;color:#667085;margin-top:3px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.panel{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:16px}
.panel-head,.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
.panel-head h3,.section-head h2{margin:0}
.muted{color:var(--muted)}.tiny{font-size:11px}.small-text{font-size:12px}
.stat-list{display:flex;flex-direction:column;gap:9px}
.stat-row{display:flex;justify-content:space-between;gap:15px;font-size:13px}
.progress{height:6px;background:#eef2f6;border-radius:999px;overflow:hidden;margin-top:5px}
.progress span{display:block;height:100%;background:#528bff;border-radius:999px}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;background:#fff}
table{width:100%;border-collapse:collapse;min-width:850px}
th,td{padding:10px 12px;border-bottom:1px solid #eef2f6;text-align:left;vertical-align:middle;font-size:12px}
th{background:#f8fafc;color:#475467;font-weight:650;position:sticky;top:0}
tbody tr{transition:background .12s}tbody tr:hover{background:#f9fbff}
.click-row{cursor:pointer}
.linkbtn{border:0;background:transparent;color:#175cd3;padding:0;font-weight:650;text-align:left}
.badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:650;background:#f2f4f7;color:#475467}
.badge.success{background:#ecfdf3;color:#067647}.badge.warning{background:#fffaeb;color:#b54708}.badge.danger{background:#fff1f0;color:#b42318}.badge.info{background:#eff8ff;color:#175cd3}
.dot{width:6px;height:6px;border-radius:999px;background:currentColor}
.kanban{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(250px,300px);gap:12px;overflow-x:auto;padding-bottom:8px}
.kanban-col{background:#eef2f6;border-radius:12px;padding:10px;min-height:240px}
.kanban-head{display:flex;justify-content:space-between;align-items:center;padding:2px 3px 8px;font-size:12px;font-weight:700}
.lead-card{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:11px;margin-bottom:8px;cursor:pointer;box-shadow:0 1px 2px rgba(16,24,40,.03)}
.lead-card:hover{border-color:#84adff}
.lead-card strong{font-size:13px}.lead-card .meta{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}
.campaign-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px}
.campaign-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;cursor:pointer}
.campaign-card:hover{border-color:#84adff}.campaign-card h3{margin-bottom:6px}
.empty{background:#fff;border:1px dashed #cfd4dc;border-radius:12px;padding:30px;text-align:center;color:#667085}
.backdrop{position:fixed;inset:0;background:rgba(16,24,40,.34);z-index:40}
.drawer{
  position:fixed;right:0;top:0;width:min(620px,92vw);height:100vh;background:#fff;z-index:50;
  box-shadow:var(--shadow);transform:translateX(105%);transition:transform .2s ease;display:flex;flex-direction:column
}
.drawer.open{transform:translateX(0)}
.drawer-head{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-start}
.drawer-body{padding:18px 20px 36px;overflow:auto}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.detail-item{background:#f8fafc;border-radius:9px;padding:10px}
.detail-item span{display:block;color:#667085;font-size:10px;text-transform:uppercase;letter-spacing:.06em}
.detail-item strong{display:block;font-size:13px;margin-top:3px;overflow-wrap:anywhere}
.detail-section{margin-top:18px}.detail-section h3{margin-bottom:9px}
.timeline{display:flex;flex-direction:column;gap:9px}
.timeline-item{border-left:2px solid #d0d5dd;padding-left:10px;font-size:12px}
.contact-row,.member-row,.suppression-row{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid #eef2f6}
dialog{width:min(620px,94vw);border:0;border-radius:14px;padding:0;box-shadow:var(--shadow)}
dialog::backdrop{background:rgba(16,24,40,.45)}
#modalForm{margin:0}.modal-head{display:flex;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line)}
.modal-body{padding:18px 20px;max-height:70vh;overflow:auto}.modal-actions{display:flex;justify-content:flex-end;gap:8px;padding:13px 20px;border-top:1px solid var(--line)}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.field{display:flex;flex-direction:column;gap:5px}.field.full{grid-column:1/-1}.field label{font-size:11px;font-weight:650;color:#475467}
.checkbox{display:flex;gap:8px;align-items:center}.checkbox input{width:auto}
.split{display:grid;grid-template-columns:1fr 1fr;gap:14px}
pre.json{white-space:pre-wrap;word-break:break-word;background:#101828;color:#e4e7ec;border-radius:9px;padding:11px;font-size:11px;max-height:330px;overflow:auto}
@media(max-width:950px){
  .app-shell{grid-template-columns:74px minmax(0,1fr)}
  .brand>div:last-child,.side-nav button span,.sidebar-foot .connection{display:none}
  .brand{justify-content:center;padding-left:0;padding-right:0}.side-nav button{text-align:center}
  .filter-bar{grid-template-columns:1fr 1fr}.search-wrap{grid-column:1/-1}
  .auth-panel{align-items:flex-start;flex-direction:column}.auth-controls{justify-content:flex-start;flex-wrap:wrap}.auth-controls input,.auth-controls select{max-width:none;flex:1 1 180px}
}
@media(max-width:620px){
  .app-shell{display:block}.sidebar{position:static;height:auto;padding:10px 12px;display:block}.brand{display:none}
  .side-nav{flex-direction:row;overflow-x:auto;overflow-y:hidden;scrollbar-width:none}
  .side-nav::-webkit-scrollbar{display:none}
  .side-nav button{flex:0 0 auto;white-space:nowrap}.side-nav button span{display:block}.sidebar-foot{display:none}
  .topbar{height:auto;padding:14px 16px}.top-actions{gap:5px}main{padding:16px}
  .auth-panel{padding:12px 16px}.filter-bar{grid-template-columns:1fr}.search-wrap{grid-column:auto}
  .detail-grid,.form-grid,.split{grid-template-columns:1fr}.field.full{grid-column:auto}
}
"""

DASHBOARD_JS = r"""
const state={
  view:'overview',auth:{mode:'dev'},me:null,options:null,stats:null,
  leads:[],campaigns:[],candidates:[],candidateSummary:null,outbox:[],webhooks:[],
  focus:null,campaignFocus:null,filters:{suppressed:null},modalSubmit:null
};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const uid=()=>globalThis.crypto?.randomUUID?.()||('id-'+Date.now()+'-'+Math.random().toString(16).slice(2));
const val=(id)=>($(id)?.value||'').trim();
const checked=id=>Boolean($(id)?.checked);
const has=p=>Boolean(state.me&&(state.me.permissions||[]).includes('*')||(state.me?.permissions||[]).includes(p));

function headers(extra={}){
  const h={'Accept':'application/json','X-Request-ID':uid(),...extra};
  if(state.auth.mode==='bearer'){
    if(state.auth.token)h.Authorization='Bearer '+state.auth.token;
  }else{
    h['X-Dev-User']=state.auth.user||'';
    h['X-Dev-Roles']=state.auth.roles||'';
    h['X-Dev-Campaigns']=state.auth.campaigns||'';
  }
  return h;
}
async function api(path,options={}){
  const method=(options.method||'GET').toUpperCase();
  const extra={...(options.headers||{})};
  if(!['GET','HEAD'].includes(method)&&!extra['Idempotency-Key'])extra['Idempotency-Key']=uid();
  const opts={...options,method,headers:headers(extra)};
  if(options.body!==undefined&&typeof options.body!=='string'){
    opts.body=JSON.stringify(options.body);opts.headers['Content-Type']='application/json';
  }
  const r=await fetch(path,opts);
  let body=null;try{body=await r.json()}catch{body={error:'invalid_response'}}
  if(!r.ok){
    const detail=typeof body?.detail==='object'?JSON.stringify(body.detail):body?.detail;
    const error=new Error(detail||body?.error||('HTTP '+r.status));error.status=r.status;error.body=body;throw error;
  }
  return {body,headers:r.headers,status:r.status};
}
function showError(e){$('error').textContent=e?.message||String(e);$('error').classList.remove('hidden');window.scrollTo({top:0,behavior:'smooth'})}
function clearError(){$('error').classList.add('hidden')}
function toast(message){$('notice').textContent=message;$('notice').classList.remove('hidden');setTimeout(()=>$('notice').classList.add('hidden'),3200)}
function setConnection(ok,text){const el=$('connection');el.textContent=text;el.classList.toggle('ok',ok)}
function statusBadge(value){
  const raw=String(value||'Unknown'),lower=raw.toLowerCase();
  let cls='';if(['valid','active','converted','completed','published','promoted','opted_in'].some(x=>lower.includes(x)))cls='success';
  else if(['dnc','invalid','failed','dead','suppressed','opted_out'].some(x=>lower.includes(x)))cls='danger';
  else if(['pending','attempted','historical','risky','paused','review'].some(x=>lower.includes(x)))cls='warning';
  else cls='info';
  return '<span class="badge '+cls+'"><span class="dot"></span>'+esc(raw)+'</span>';
}
function setTitle(title,eyebrow='Lead operations'){$('viewTitle').textContent=title;$('viewEyebrow').textContent=eyebrow}
function fillSelect(id,items,firstLabel){
  const el=$(id),current=el.value;
  el.innerHTML='<option value="">'+esc(firstLabel)+'</option>'+items.map(x=>'<option value="'+esc(x.value)+'">'+esc(x.label)+'</option>').join('');
  if([...el.options].some(o=>o.value===current))el.value=current;
}
function setAuthControls(){
  const bearer=$('authMode').value==='bearer';
  $('bearer').classList.toggle('hidden',!bearer);
  for(const id of ['devUser','devRoles','devCampaigns'])$(id).classList.toggle('hidden',bearer);
}
function updateActionVisibility(){
  $('newLeadBtn').classList.toggle('hidden',!has('lead:create'));
  document.querySelector('[data-view="campaigns"]').classList.toggle('hidden',!has('campaign:read'));
  document.querySelector('[data-view="candidates"]').classList.toggle('hidden',!has('candidate:read'));
  document.querySelector('[data-view="integrations"]').classList.toggle('hidden',!(has('outbox:read')||has('webhook:manage')));
}
async function safe(path,fallback,permission){
  if(permission&&!has(permission))return fallback;
  try{return (await api(path)).body}catch{return fallback}
}
async function loadAll(){
  clearError();
  const me=await api('/api/v2/me');state.me=me.body;
  state.options=(await api('/api/v2/options')).body;
  setConnection(true,state.me.subject+' · '+state.me.roles.join(', '));
  $('authPanel').classList.add('hidden');updateActionVisibility();
  const [campaigns,leads,candidates,candidateSummary,outbox,webhooks,stats]=await Promise.all([
    safe('/api/v2/campaigns',{items:[]},'campaign:read'),
    safe('/api/v2/leads?limit=200',{items:[]},'lead:read'),
    safe('/api/v2/candidates?limit=200',{items:[]},'candidate:read'),
    safe('/api/v2/candidates/summary',{total:0,by_disposition:{}},'candidate:read'),
    safe('/api/v2/outbox?limit=100',{items:[]},'outbox:read'),
    safe('/api/v2/webhooks',{items:[]},'webhook:manage'),
    safe('/api/v2/stats',null,'audit:read')
  ]);
  state.campaigns=campaigns.items||[];state.leads=leads.items||[];state.candidates=candidates.items||[];
  state.candidateSummary=candidateSummary;state.outbox=outbox.items||[];state.webhooks=webhooks.items||[];state.stats=stats;
  hydrateFilters();render();
}
function hydrateFilters(){
  fillSelect('campaign',state.campaigns.map(x=>({value:x.campaign_id,label:x.campaign_code+' — '+x.name})),'All campaigns');
  fillSelect('country',[...new Set(state.leads.map(x=>x.country).filter(Boolean))].sort().map(x=>({value:x,label:x})),'All countries');
  const statuses=new Set(state.leads.map(x=>x.status).filter(Boolean));Object.keys(state.options?.lifecycle_transitions||{}).forEach(x=>statuses.add(x));
  fillSelect('status',[...statuses].sort().map(x=>({value:x,label:x})),'All statuses');
}
async function loadLeads(){
  clearError();const p=new URLSearchParams({limit:'200'});
  if(val('search'))p.set('q',val('search'));if(val('country'))p.set('country',val('country'));if(val('status'))p.set('status',val('status'));if(val('campaign'))p.set('campaign_id',val('campaign'));
  if(state.filters.suppressed!==null)p.set('suppressed',String(state.filters.suppressed));
  const data=(await api('/api/v2/leads?'+p)).body;state.leads=data.items||[];hydrateFilters();render();
}
async function refreshData(message='Refreshed'){
  await loadAll();if(message)toast(message);
}
function metricButton(label,value,view,action=''){
  return '<button class="metric-card metric-link" data-target="'+esc(view)+'" data-action="'+esc(action)+'"><div class="metric">'+esc(value)+'</div><div class="metric-label">'+esc(label)+'</div></button>';
}
function overview(){
  const s=state.stats||{},statuses=s.statuses||[],max=Math.max(1,...statuses.map(x=>x.count||0));
  const metrics=[
    metricButton('Total leads',s.total_leads??state.leads.length,'leads'),
    metricButton('With email',s.with_email??'—','leads'),
    metricButton('With phone',s.with_phone??'—','leads'),
    metricButton('Campaigns',s.campaign_count??state.campaigns.length,'campaigns'),
    metricButton('Suppressed',s.suppressed??'—','leads','suppressed'),
    metricButton('DNC',s.do_not_contact??'—','leads','dnc'),
    metricButton('Pending outbox',s.pending_outbox??state.outbox.filter(x=>x.status==='pending').length,'integrations'),
    metricButton('Candidates',state.candidateSummary?.total??state.candidates.length,'candidates')
  ].join('');
  const lifecycle=statuses.slice(0,12).map(x=>'<div><div class="stat-row"><span>'+esc(x.status)+'</span><strong>'+esc(x.count)+'</strong></div><div class="progress"><span style="width:'+Math.round((x.count/max)*100)+'%"></span></div></div>').join('');
  const campaigns=state.campaigns.slice(0,8).map(c=>'<button class="campaign-card campaign-open" data-id="'+esc(c.campaign_id)+'"><div class="panel-head"><h3>'+esc(c.campaign_code)+'</h3>'+statusBadge(c.state)+'</div><div class="muted small-text">'+esc(c.name)+'</div><div class="tiny muted" style="margin-top:8px">'+esc(c.primary_supervisor||'No primary supervisor')+'</div></button>').join('');
  return '<div class="cards">'+metrics+'</div><div class="grid"><div class="panel"><div class="panel-head"><h3>Lifecycle distribution</h3><button class="ghost small" data-view-jump="kanban">Open Kanban</button></div><div class="stat-list">'+(lifecycle||'<span class="muted">No lifecycle data yet.</span>')+'</div></div><div class="panel"><div class="panel-head"><h3>Active campaigns</h3><button class="ghost small" data-view-jump="campaigns">See all</button></div><div class="campaign-cards">'+(campaigns||'<span class="muted">No campaigns available.</span>')+'</div></div></div>';
}
function leadTable(items){
  if(!items.length)return '<div class="empty"><h3>No leads found</h3><p>Adjust the filters or create a new lead.</p></div>';
  return '<div class="table-wrap"><table><thead><tr><th>Lead</th><th>Country</th><th>Status</th><th>Campaign</th><th>Agent</th><th>Verification</th><th>Contact</th><th>Updated</th></tr></thead><tbody>'+
    items.map(x=>'<tr class="click-row lead-open" data-id="'+esc(x.lead_id)+'"><td><button class="linkbtn lead-open" data-id="'+esc(x.lead_id)+'">'+esc(x.business_name)+'</button><div class="muted tiny">'+esc(x.contact_name||'No contact name')+'</div></td><td>'+esc(x.country)+'</td><td>'+statusBadge(x.status)+'</td><td>'+esc(campaignLabel(x.campaign_id))+'</td><td>'+esc(x.assigned_agent||'Unassigned')+'</td><td>'+statusBadge(x.verification_status||'unverified')+'</td><td>'+esc(x.email||'')+'<div class="tiny muted">'+esc(x.phone||'')+'</div></td><td>'+esc(formatDate(x.updated_at))+'</td></tr>').join('')+
  '</tbody></table></div>';
}
function leadsView(){
  return '<div class="section-head"><div><h2>Lead workspace</h2><div class="muted small-text">'+esc(state.leads.length)+' records in this result</div></div><div class="actions">'+(has('lead:create')?'<button class="primary" id="viewNewLead">+ New lead</button>':'')+'</div></div>'+leadTable(state.leads);
}
function kanbanView(){
  const order=['Needs Verification','New','Assigned','Attempted','Contacted','Qualified','Appointment','Converted','Lost','DNC'];
  const grouped={};for(const x of state.leads)(grouped[x.status||'Unknown']??=[]).push(x);
  const keys=[...new Set([...order,...Object.keys(grouped)])].filter(k=>grouped[k]?.length||order.includes(k));
  return '<div class="section-head"><div><h2>Lifecycle Kanban</h2><div class="muted small-text">Click any card to open lead operations.</div></div></div><div class="kanban">'+keys.map(k=>'<section class="kanban-col"><div class="kanban-head"><span>'+esc(k)+'</span><span class="badge">'+esc((grouped[k]||[]).length)+'</span></div>'+(grouped[k]||[]).slice(0,100).map(x=>'<article class="lead-card lead-open" data-id="'+esc(x.lead_id)+'"><strong>'+esc(x.business_name)+'</strong><div class="muted tiny">'+esc(x.contact_name||x.email||x.phone||'No contact')+'</div><div class="meta"><span class="badge">'+esc(x.assigned_agent||'Unassigned')+'</span></div></article>').join('')+'</section>').join('')+'</div>';
}
function campaignsView(){
  const controls=has('campaign:create')?'<button class="primary" id="newCampaignBtn">+ New campaign</button>':'';
  const cards=state.campaigns.map(c=>'<article class="campaign-card campaign-open" data-id="'+esc(c.campaign_id)+'"><div class="panel-head"><div><h3>'+esc(c.campaign_code)+'</h3><div class="muted small-text">'+esc(c.name)+'</div></div>'+statusBadge(c.state)+'</div><div class="detail-grid"><div class="detail-item"><span>Type</span><strong>'+esc(c.campaign_type)+'</strong></div><div class="detail-item"><span>Supervisor</span><strong>'+esc(c.primary_supervisor||'Not set')+'</strong></div></div></article>').join('');
  return '<div class="section-head"><div><h2>Campaign management</h2><div class="muted small-text">Supervisors, members and routing authority.</div></div>'+controls+'</div><div class="campaign-cards">'+(cards||'<div class="empty"><h3>No campaigns yet</h3></div>')+'</div>';
}
function candidatesView(){
  const summary=state.candidateSummary||{total:0,by_disposition:{}},by=summary.by_disposition||{};
  const batches=[...new Set(state.candidates.map(x=>x.batch_id).filter(Boolean))];
  const promote=has('candidate:promote')&&batches.length?'<button id="promoteCandidatesBtn" class="primary">Promote new in batch</button>':'';
  const rows=state.candidates.map(c=>'<tr><td>'+esc(c.business_name)+'<div class="tiny muted">'+esc(c.contact_name)+'</div></td><td>'+esc(c.batch_id)+'</td><td>'+statusBadge(c.disposition)+'</td><td>'+esc((c.phones||[]).join(', '))+'</td><td>'+(c.match_lead_id?'<button class="linkbtn lead-open" data-id="'+esc(c.match_lead_id)+'">'+esc(c.match_lead_id)+'</button>':'—')+'</td><td>'+esc(c.match_reason||'—')+'</td></tr>').join('');
  return '<div class="section-head"><div><h2>Candidate review</h2><div class="muted small-text">Governed staging area before canonical promotion.</div></div>'+promote+'</div><div class="cards">'+metricButton('Candidates',summary.total||0,'candidates')+metricButton('New',by.new||0,'candidates')+metricButton('Possible matches',by.possible_match||0,'candidates')+metricButton('Promoted',by.promoted||0,'candidates')+'</div>'+(rows?'<div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Batch</th><th>Disposition</th><th>Phones</th><th>Matched lead</th><th>Reason</th></tr></thead><tbody>'+rows+'</tbody></table></div>':'<div class="empty">No candidates found.</div>');
}
function integrationsView(){
  const outboxRows=state.outbox.map(e=>'<tr><td>'+esc(e.event_type)+'</td><td>'+esc(e.aggregate_type)+'<div class="tiny muted">'+esc(e.aggregate_id)+'</div></td><td>'+statusBadge(e.status)+'</td><td>'+esc(e.attempt_count)+'</td><td>'+esc(formatDate(e.created_at))+'</td><td>'+esc(e.last_error||'')+'</td></tr>').join('');
  const webhookRows=state.webhooks.map(w=>'<tr><td>'+esc(w.name)+'</td><td>'+esc(w.url)+'</td><td>'+statusBadge(w.active?'active':'inactive')+'</td><td>'+esc(w.event_types_json||'')+'</td><td>'+esc(w.secret_ref||'')+'</td></tr>').join('');
  return '<div class="section-head"><div><h2>Integrations & delivery</h2><div class="muted small-text">Transactional outbox and signed webhook subscriptions.</div></div>'+(has('webhook:manage')?'<button class="primary" id="newWebhookBtn">+ Webhook</button>':'')+'</div><div class="panel"><div class="panel-head"><h3>Outbox</h3><span class="badge">'+esc(state.outbox.length)+' shown</span></div>'+(outboxRows?'<div class="table-wrap"><table><thead><tr><th>Event</th><th>Aggregate</th><th>Status</th><th>Attempts</th><th>Created</th><th>Error</th></tr></thead><tbody>'+outboxRows+'</tbody></table></div>':'<div class="empty">No outbox events available.</div>')+'</div><div class="panel" style="margin-top:14px"><div class="panel-head"><h3>Webhooks</h3><span class="badge">'+esc(state.webhooks.length)+' configured</span></div>'+(webhookRows?'<div class="table-wrap"><table><thead><tr><th>Name</th><th>URL</th><th>Status</th><th>Events</th><th>Secret</th></tr></thead><tbody>'+webhookRows+'</tbody></table></div>':'<div class="empty">No webhook subscriptions configured.</div>')+'</div>';
}
function render(){
  const host=$('view');$('filterBar').classList.toggle('hidden',!['leads','kanban'].includes(state.view));
  if(state.view==='overview'){setTitle('Overview','Lead operations');host.innerHTML=overview()}
  else if(state.view==='leads'){setTitle('All leads','Lead operations');host.innerHTML=leadsView()}
  else if(state.view==='kanban'){setTitle('Kanban','Lifecycle');host.innerHTML=kanbanView()}
  else if(state.view==='campaigns'){setTitle('Campaigns','Operations control');host.innerHTML=campaignsView()}
  else if(state.view==='candidates'){setTitle('Candidates','Data quality');host.innerHTML=candidatesView()}
  else if(state.view==='integrations'){setTitle('Integrations','Delivery & observability');host.innerHTML=integrationsView()}
  bindViewActions();
}
function campaignLabel(id){const c=state.campaigns.find(x=>x.campaign_id===id);return c?c.campaign_code:(id||'—')}
function formatDate(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.valueOf())?value:d.toLocaleString()}
function formValue(form,name){return String(new FormData(form).get(name)||'').trim()}
function modal(title,html,submit='Save',onSubmit,eyebrow='Action'){
  $('modalTitle').textContent=title;$('modalEyebrow').textContent=eyebrow;$('modalBody').innerHTML=html;$('modalSubmit').textContent=submit;state.modalSubmit=onSubmit;$('modal').showModal();
}
function closeModal(){$('modal').close();state.modalSubmit=null}
function inputField(name,label,value='',type='text',extra=''){return '<div class="field '+extra+'"><label for="f-'+esc(name)+'">'+esc(label)+'</label><input id="f-'+esc(name)+'" name="'+esc(name)+'" type="'+esc(type)+'" value="'+esc(value||'')+'"></div>'}
function selectField(name,label,items,current='',extra=''){return '<div class="field '+extra+'"><label for="f-'+esc(name)+'">'+esc(label)+'</label><select id="f-'+esc(name)+'" name="'+esc(name)+'">'+items.map(x=>'<option value="'+esc(x.value)+'" '+(String(x.value)===String(current)?'selected':'')+'>'+esc(x.label)+'</option>').join('')+'</select></div>'}
function textareaField(name,label,value='',extra=''){return '<div class="field '+extra+'"><label for="f-'+esc(name)+'">'+esc(label)+'</label><textarea id="f-'+esc(name)+'" name="'+esc(name)+'">'+esc(value||'')+'</textarea></div>'}
function openCreateLead(){
  const campaignItems=[{value:'',label:'No campaign'},...state.campaigns.map(c=>({value:c.campaign_id,label:c.campaign_code+' — '+c.name}))];
  modal('Create lead','<div class="form-grid">'+inputField('business_name','Business name','','text','full')+inputField('contact_name','Contact name')+inputField('country','Country','Dominican Republic')+inputField('business_category','Business category')+selectField('campaign_id','Campaign',campaignItems)+inputField('email','Email','','email')+inputField('phone','Phone')+inputField('website','Website','','url')+textareaField('notes','Notes','','full')+'</div>','Create',async form=>{
    const body={business_name:formValue(form,'business_name'),contact_name:formValue(form,'contact_name'),country:formValue(form,'country'),business_category:formValue(form,'business_category'),campaign_id:formValue(form,'campaign_id')||null,email:formValue(form,'email')||null,phone:formValue(form,'phone')||null,website:formValue(form,'website')||null,notes:formValue(form,'notes')||null};
    const r=await api('/api/v2/leads',{method:'POST',body});closeModal();await refreshData('Lead created');await openLead(r.body.lead_id);
  },'Lead');
}
function openEditLead(lead){
  modal('Edit lead','<div class="form-grid">'+inputField('business_name','Business name',lead.business_name,'text','full')+inputField('contact_name','Contact name',lead.contact_name)+inputField('country','Country',lead.country)+inputField('city','City',lead.city)+inputField('business_category','Business category',lead.business_category)+inputField('email','Primary email',lead.email,'email')+inputField('phone','Primary phone',lead.phone)+inputField('website','Website',lead.website,'url')+inputField('priority','Priority',lead.priority)+textareaField('notes','Notes',lead.notes,'full')+'</div>','Save changes',async form=>{
    const body={};for(const k of ['business_name','contact_name','country','city','business_category','email','phone','website','priority','notes'])body[k]=formValue(form,k)||null;
    const r=await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id),{method:'PATCH',headers:{'If-Match':'"'+lead.version+'"'},body});closeModal();toast('Lead updated');await openLead(r.body.lead_id,true);await loadLeads();
  },'Lead');
}
function openAssign(lead){
  const campaigns=state.campaigns.map(c=>({value:c.campaign_id,label:c.campaign_code+' — '+c.name}));
  modal('Assign lead','<div class="form-grid">'+selectField('campaign_id','Campaign',campaigns,lead.campaign_id,'full')+selectField('strategy','Strategy',[{value:'round_robin',label:'Round robin'},{value:'manual',label:'Specific agent'}],'round_robin')+inputField('to_agent','Agent ID / username',lead.assigned_agent||'')+inputField('reason','Reason','dashboard assignment')+'</div>','Assign',async form=>{
    const strategy=formValue(form,'strategy'),body={campaign_id:formValue(form,'campaign_id'),strategy,reason:formValue(form,'reason'),expected_version:lead.version};if(strategy==='manual')body.to_agent=formValue(form,'to_agent');
    const r=await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id)+'/assign',{method:'POST',body});closeModal();toast('Lead assigned');await openLead(r.body.lead_id,true);await loadLeads();
  },'Routing');
}
function openTransition(lead){
  const allowed=state.options?.lifecycle_transitions?.[lead.status]||[];
  if(!allowed.length){toast('No lifecycle transitions are allowed from '+lead.status);return}
  modal('Move lifecycle','<div class="form-grid">'+selectField('to_status','Next status',allowed.map(x=>({value:x,label:x})),allowed[0],'full')+textareaField('reason','Reason','','full')+'</div>','Move lead',async form=>{
    const r=await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id)+'/transition',{method:'POST',body:{to_status:formValue(form,'to_status'),reason:formValue(form,'reason')||null,expected_version:lead.version}});closeModal();toast('Lifecycle updated');await openLead(r.body.lead_id,true);await loadLeads();
  },'Lifecycle');
}
function openAddContact(lead){
  modal('Add contact point','<div class="form-grid">'+selectField('kind','Type',[{value:'phone',label:'Phone'},{value:'email',label:'Email'}],'phone')+inputField('label','Label','mobile')+inputField('value','Value','','text','full')+selectField('verification_status','Verification',(state.options?.contact_verification_states||[]).map(x=>({value:x,label:x})),'unverified')+'<div class="field full"><label class="checkbox"><input type="checkbox" name="primary"> Set as primary</label></div></div>','Add contact',async form=>{
    const body={kind:formValue(form,'kind'),label:formValue(form,'label')||null,value:formValue(form,'value'),verification_status:formValue(form,'verification_status'),primary:new FormData(form).get('primary')==='on',source:'dashboard'};
    await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id)+'/contacts',{method:'POST',body});closeModal();toast('Contact point added');await openLead(lead.lead_id,true);
  },'Contact');
}
function openConsent(lead){
  const items=(state.options?.consent_states||[]).map(x=>({value:x,label:x.replaceAll('_',' ')}));
  modal('Update consent','<div class="form-grid">'+selectField('status','Consent status',items,lead.consent_status||'unknown')+inputField('jurisdiction','Jurisdiction',lead.jurisdiction||'')+inputField('source','Source','dashboard','text','full')+'</div>','Record consent',async form=>{
    const r=await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id)+'/consent',{method:'POST',body:{status:formValue(form,'status'),source:formValue(form,'source'),jurisdiction:formValue(form,'jurisdiction')||null}});closeModal();toast('Consent updated');await openLead(r.body.lead_id,true);await loadLeads();
  },'Compliance');
}
function openSuppress(lead){
  const items=(state.options?.suppression_channels||[]).map(x=>({value:x,label:x}));
  modal('Suppress lead','<div class="form-grid">'+selectField('channel','Channel',items,'call')+inputField('jurisdiction','Jurisdiction',lead.jurisdiction||'')+inputField('reason','Reason','','text','full')+'</div>','Apply suppression',async form=>{
    const r=await api('/api/v2/leads/'+encodeURIComponent(lead.lead_id)+'/suppress',{method:'POST',body:{channel:formValue(form,'channel'),reason:formValue(form,'reason'),jurisdiction:formValue(form,'jurisdiction')||null,source:'dashboard'}});closeModal();toast('Suppression applied');await openLead(r.body.lead_id,true);await loadLeads();
  },'Compliance');
}
function openUnsuppress(focus){
  const active=(focus.suppressions||[]).filter(x=>x.active);if(!active.length){toast('No active suppressions');return}
  modal('Lift suppression','<div class="form-grid">'+selectField('suppression_id','Active suppression',active.map(x=>({value:x.suppression_id,label:x.channel+' — '+x.reason})),active[0].suppression_id,'full')+inputField('reason','Reason for lift','reviewed and approved','text','full')+'</div>','Lift suppression',async form=>{
    const r=await api('/api/v2/leads/'+encodeURIComponent(focus.lead.lead_id)+'/unsuppress',{method:'POST',body:{suppression_id:formValue(form,'suppression_id'),reason:formValue(form,'reason')}});closeModal();toast('Suppression lifted');await openLead(r.body.lead_id,true);await loadLeads();
  },'Compliance');
}
function openVerifyContact(lead,contact){
  const items=(state.options?.contact_verification_states||[]).map(x=>({value:x,label:x}));
  modal('Verify contact','<div class="form-grid">'+selectField('verification_status','Verification',items,contact.verification_status,'full')+inputField('source','Source','dashboard-verification','text','full')+'</div>','Update verification',async form=>{
    await api('/api/v2/contact-points/'+encodeURIComponent(contact.contact_point_id)+'/verify',{method:'POST',body:{verification_status:formValue(form,'verification_status'),source:formValue(form,'source')}});closeModal();toast('Contact verification updated');await openLead(lead.lead_id,true);
  },'Contact');
}
async function openLead(id,refresh=false){
  clearError();
  const [lead,contacts,assignments,transitions,suppressions,events]=await Promise.all([
    api('/api/v2/leads/'+encodeURIComponent(id)),
    safe('/api/v2/leads/'+encodeURIComponent(id)+'/contacts',{items:[]},'lead:read'),
    safe('/api/v2/leads/'+encodeURIComponent(id)+'/assignments',{items:[]},'audit:read'),
    safe('/api/v2/leads/'+encodeURIComponent(id)+'/transitions',{items:[]},'audit:read'),
    safe('/api/v2/leads/'+encodeURIComponent(id)+'/suppressions',{items:[]},'audit:read'),
    safe('/api/v2/leads/'+encodeURIComponent(id)+'/events',{items:[]},'audit:read')
  ]);
  state.focus={lead:lead.body,contacts:contacts.items||[],assignments:assignments.items||[],transitions:transitions.items||[],suppressions:suppressions.items||[],events:events.items||[]};
  renderLeadDrawer(state.focus);openDrawer();if(refresh)toast('Lead details refreshed');
}
function renderLeadDrawer(x){
  const l=x.lead,actions=[
    has('lead:update')?'<button class="secondary small" data-lead-action="edit">Edit</button>':'',
    has('lead:assign')?'<button class="secondary small" data-lead-action="assign">Assign</button>':'',
    has('lead:transition')?'<button class="primary small" data-lead-action="transition">Move status</button>':'',
    has('lead:contact')?'<button class="secondary small" data-lead-action="contact">+ Contact</button>':'',
    has('lead:consent')?'<button class="secondary small" data-lead-action="consent">Consent</button>':'',
    has('lead:suppress')?'<button class="danger small" data-lead-action="suppress">Suppress</button>':'',
    has('lead:suppress')&&(x.suppressions||[]).some(s=>s.active)?'<button class="secondary small" data-lead-action="unsuppress">Lift suppression</button>':''
  ].join('');
  $('drawerEyebrow').textContent='Lead · '+l.lead_id;$('drawerTitle').textContent=l.business_name;
  const contacts=(x.contacts||[]).map(c=>'<div class="contact-row"><div><strong>'+esc(c.value)+'</strong><div class="tiny muted">'+esc(c.kind)+' · '+esc(c.label||'')+' · '+esc(c.source||'')+'</div></div><div class="inline-actions">'+statusBadge(c.verification_status)+(has('lead:contact')?'<button class="ghost small verify-contact" data-contact="'+esc(c.contact_point_id)+'">Verify</button>':'')+'</div></div>').join('');
  const suppressions=(x.suppressions||[]).map(s=>'<div class="suppression-row"><div><strong>'+esc(s.channel)+'</strong><div class="tiny muted">'+esc(s.reason)+' · '+esc(s.jurisdiction||'')+'</div></div>'+statusBadge(s.active?'active':'lifted')+'</div>').join('');
  const activity=(x.events||[]).slice(0,30).map(e=>'<div class="timeline-item"><strong>'+esc(e.event_type)+'</strong><div class="tiny muted">'+esc(e.actor)+' · '+esc(formatDate(e.event_at))+'</div></div>').join('');
  $('drawerBody').innerHTML='<div class="actions">'+actions+'</div><div class="detail-grid" style="margin-top:14px"><div class="detail-item"><span>Status</span><strong>'+statusBadge(l.status)+'</strong></div><div class="detail-item"><span>Version</span><strong>'+esc(l.version)+'</strong></div><div class="detail-item"><span>Contact</span><strong>'+esc(l.contact_name||'—')+'</strong></div><div class="detail-item"><span>Campaign</span><strong>'+esc(campaignLabel(l.campaign_id))+'</strong></div><div class="detail-item"><span>Assigned agent</span><strong>'+esc(l.assigned_agent||'Unassigned')+'</strong></div><div class="detail-item"><span>Consent</span><strong>'+esc(l.consent_status||'unknown')+'</strong></div><div class="detail-item"><span>Country</span><strong>'+esc(l.country)+'</strong></div><div class="detail-item"><span>Category</span><strong>'+esc(l.business_category)+'</strong></div></div><section class="detail-section"><div class="panel-head"><h3>Contact points</h3><span class="badge">'+esc((x.contacts||[]).length)+'</span></div>'+(contacts||'<div class="muted small-text">No contact points.</div>')+'</section><section class="detail-section"><h3>Compliance</h3><div class="detail-grid"><div class="detail-item"><span>DNC</span><strong>'+esc(Boolean(l.do_not_contact))+'</strong></div><div class="detail-item"><span>Suppressed</span><strong>'+esc(Boolean(l.suppressed))+'</strong></div><div class="detail-item"><span>Jurisdiction</span><strong>'+esc(l.jurisdiction||'—')+'</strong></div><div class="detail-item"><span>Verification</span><strong>'+esc(l.verification_status||'unverified')+'</strong></div></div>'+suppressions+'</section><section class="detail-section"><h3>Notes</h3><div class="panel muted small-text">'+esc(l.notes||'No notes')+'</div></section>'+(has('audit:read')?'<section class="detail-section"><h3>Activity</h3><div class="timeline">'+(activity||'<div class="muted small-text">No audit events.</div>')+'</div></section>':'');
  bindDrawerActions();
}
function bindDrawerActions(){
  document.querySelectorAll('[data-lead-action]').forEach(b=>b.onclick=()=>{const l=state.focus.lead;({edit:()=>openEditLead(l),assign:()=>openAssign(l),transition:()=>openTransition(l),contact:()=>openAddContact(l),consent:()=>openConsent(l),suppress:()=>openSuppress(l),unsuppress:()=>openUnsuppress(state.focus)})[b.dataset.leadAction]?.()});
  document.querySelectorAll('.verify-contact').forEach(b=>b.onclick=()=>{const c=state.focus.contacts.find(x=>x.contact_point_id===b.dataset.contact);if(c)openVerifyContact(state.focus.lead,c)});
}
async function openCampaign(id){
  const campaign=state.campaigns.find(x=>x.campaign_id===id);if(!campaign)return;
  const members=(await safe('/api/v2/campaigns/'+encodeURIComponent(id)+'/members',{items:[]},'campaign:read')).items||[];
  state.campaignFocus={campaign,members};$('drawerEyebrow').textContent='Campaign · '+campaign.campaign_code;$('drawerTitle').textContent=campaign.name;
  const actions=(has('campaign:update')?'<button class="secondary small" id="editCampaignBtn">Edit campaign</button>':'')+(has('campaign:member')?'<button class="primary small" id="addMemberBtn">+ Member</button>':'');
  const rows=members.map(m=>'<div class="member-row"><div><strong>'+esc(m.user_id)+'</strong><div class="tiny muted">'+esc(m.member_role)+'</div></div>'+statusBadge(m.active?'active':'inactive')+'</div>').join('');
  $('drawerBody').innerHTML='<div class="actions">'+actions+'</div><div class="detail-grid" style="margin-top:14px"><div class="detail-item"><span>Code</span><strong>'+esc(campaign.campaign_code)+'</strong></div><div class="detail-item"><span>State</span><strong>'+esc(campaign.state)+'</strong></div><div class="detail-item"><span>Type</span><strong>'+esc(campaign.campaign_type)+'</strong></div><div class="detail-item"><span>Supervisor</span><strong>'+esc(campaign.primary_supervisor||'—')+'</strong></div></div><section class="detail-section"><div class="panel-head"><h3>Members</h3><span class="badge">'+esc(members.length)+'</span></div>'+(rows||'<div class="muted">No campaign members.</div>')+'</section>';
  openDrawer();if($('editCampaignBtn'))$('editCampaignBtn').onclick=()=>openEditCampaign(campaign);if($('addMemberBtn'))$('addMemberBtn').onclick=()=>openAddMember(campaign);
}
function openCreateCampaign(){
  const types=(state.options?.campaign_types||[]).map(x=>({value:x,label:x})),states=(state.options?.campaign_states||[]).map(x=>({value:x,label:x}));
  modal('Create campaign','<div class="form-grid">'+inputField('campaign_code','Campaign code','','text','full')+inputField('name','Name','','text','full')+selectField('campaign_type','Type',types,'outbound')+selectField('state','State',states,'draft')+inputField('primary_supervisor','Primary supervisor')+inputField('client_id','Client ID')+textareaField('description','Description','','full')+'</div>','Create campaign',async form=>{
    const body={campaign_code:formValue(form,'campaign_code'),name:formValue(form,'name'),campaign_type:formValue(form,'campaign_type'),state:formValue(form,'state'),primary_supervisor:formValue(form,'primary_supervisor')||null,client_id:formValue(form,'client_id')||null,description:formValue(form,'description')||null};
    const r=await api('/api/v2/campaigns',{method:'POST',body});closeModal();await refreshData('Campaign created');await openCampaign(r.body.campaign_id);
  },'Campaign');
}
function openEditCampaign(c){
  const states=(state.options?.campaign_states||[]).map(x=>({value:x,label:x}));
  modal('Edit campaign','<div class="form-grid">'+inputField('name','Name',c.name,'text','full')+selectField('state','State',states,c.state)+inputField('primary_supervisor','Primary supervisor',c.primary_supervisor)+inputField('client_id','Client ID',c.client_id)+textareaField('description','Description',c.description,'full')+'</div>','Save campaign',async form=>{
    const body={name:formValue(form,'name'),state:formValue(form,'state'),primary_supervisor:formValue(form,'primary_supervisor')||null,client_id:formValue(form,'client_id')||null,description:formValue(form,'description')||null};
    await api('/api/v2/campaigns/'+encodeURIComponent(c.campaign_id),{method:'PATCH',body});closeModal();await refreshData('Campaign updated');await openCampaign(c.campaign_id);
  },'Campaign');
}
function openAddMember(c){
  const roles=(state.options?.member_roles||[]).map(x=>({value:x,label:x.replaceAll('_',' ')}));
  modal('Add campaign member','<div class="form-grid">'+inputField('user_id','User ID / username','','text','full')+selectField('member_role','Role',roles,'agent','full')+'</div>','Add member',async form=>{
    await api('/api/v2/campaigns/'+encodeURIComponent(c.campaign_id)+'/members',{method:'POST',body:{user_id:formValue(form,'user_id'),member_role:formValue(form,'member_role'),active:true}});closeModal();toast('Campaign member added');await openCampaign(c.campaign_id);
  },'Campaign');
}
function openWebhook(){
  modal('Register webhook','<div class="form-grid">'+inputField('name','Name','','text','full')+inputField('url','HTTPS URL','','url','full')+inputField('secret_ref','Secret reference','openbao://secret/leads/webhook#value','text','full')+inputField('event_types','Event types','lead.created,lead.updated','text','full')+'</div>','Register',async form=>{
    const events=formValue(form,'event_types').split(',').map(x=>x.trim()).filter(Boolean);await api('/api/v2/webhooks',{method:'POST',body:{name:formValue(form,'name'),url:formValue(form,'url'),secret_ref:formValue(form,'secret_ref'),event_types:events}});closeModal();await refreshData('Webhook registered');
  },'Integration');
}
function openPromoteCandidates(){
  const batches=[...new Set(state.candidates.filter(x=>x.disposition==='new').map(x=>x.batch_id).filter(Boolean))];if(!batches.length){toast('No promotable candidates');return}
  modal('Promote candidates','<div class="form-grid">'+selectField('batch_id','Batch',batches.map(x=>({value:x,label:x})),batches[0],'full')+'<div class="field full"><div class="notice">Only candidates with disposition <strong>new</strong> are promoted. Existing possible matches are not changed.</div></div></div>','Promote new',async form=>{
    const batch=formValue(form,'batch_id'),r=await api('/api/v2/candidates/promote',{method:'POST',body:{batch_id:batch}});closeModal();await refreshData('Promoted '+r.body.promoted+' candidates; '+r.body.failed+' failed');
  },'Candidate review');
}
function bindViewActions(){
  document.querySelectorAll('.lead-open').forEach(el=>el.onclick=e=>{e.stopPropagation();openLead(el.dataset.id).catch(showError)});
  document.querySelectorAll('.campaign-open').forEach(el=>el.onclick=()=>openCampaign(el.dataset.id).catch(showError));
  document.querySelectorAll('[data-view-jump]').forEach(el=>el.onclick=()=>setView(el.dataset.viewJump));
  document.querySelectorAll('.metric-link').forEach(el=>el.onclick=()=>{if(el.dataset.action==='suppressed'){state.filters.suppressed=true;setView('leads');loadLeads().catch(showError);return}if(el.dataset.action==='dnc'){$('status').value='DNC';setView('leads');loadLeads().catch(showError);return}setView(el.dataset.target)});
  if($('viewNewLead'))$('viewNewLead').onclick=openCreateLead;if($('newCampaignBtn'))$('newCampaignBtn').onclick=openCreateCampaign;if($('newWebhookBtn'))$('newWebhookBtn').onclick=openWebhook;if($('promoteCandidatesBtn'))$('promoteCandidatesBtn').onclick=openPromoteCandidates;
}
function openDrawer(){$('drawer').classList.add('open');$('drawer').setAttribute('aria-hidden','false');$('drawerBackdrop').classList.remove('hidden')}
function closeDrawer(){$('drawer').classList.remove('open');$('drawer').setAttribute('aria-hidden','true');$('drawerBackdrop').classList.add('hidden')}
function setView(name){
  state.view=name;document.querySelectorAll('#nav [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));render();
}
$('modalForm').addEventListener('submit',async e=>{e.preventDefault();if(!state.modalSubmit)return;const btn=$('modalSubmit');btn.disabled=true;clearError();try{await state.modalSubmit(e.currentTarget)}catch(err){showError(err)}finally{btn.disabled=false}});
$('modalCancel').onclick=closeModal;$('modalClose').onclick=closeModal;$('drawerClose').onclick=closeDrawer;$('drawerBackdrop').onclick=closeDrawer;
document.querySelectorAll('#nav [data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('sessionBtn').onclick=()=>$('authPanel').classList.toggle('hidden');
$('authMode').onchange=setAuthControls;
$('connectBtn').onclick=async()=>{state.auth.mode=$('authMode').value;state.auth.user=val('devUser');state.auth.roles=val('devRoles');state.auth.campaigns=val('devCampaigns');state.auth.token=val('bearer');try{await loadAll()}catch(e){setConnection(false,'Authentication failed');showError(e)}};
$('refreshBtn').onclick=()=>refreshData().catch(showError);$('newLeadBtn').onclick=openCreateLead;
$('applyFilters').onclick=()=>{state.filters.suppressed=null;loadLeads().catch(showError)};
$('clearFilters').onclick=()=>{for(const id of ['search','country','status','campaign'])$(id).value='';state.filters.suppressed=null;loadLeads().catch(showError)};
$('search').addEventListener('keydown',e=>{if(e.key==='Enter')loadLeads().catch(showError)});
setAuthControls();render();
"""
