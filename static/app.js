let keywordIndex = 0;
let bulkRunning = false;
let systemInfo = {};

const country = document.getElementById("country");
const keyword = document.getElementById("keyword");
const keywordTranslation = document.getElementById("keywordTranslation");
const statusEl = document.getElementById("status");
const adsInput = document.getElementById("adsInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const topList = document.getElementById("topList");
const watchList = document.getElementById("watchList");
const analysisPreview = document.getElementById("analysisPreview");
const engineBadge = document.getElementById("engineBadge");

const BATCH_SIZE = 60;
const MAX_BATCH_CHARS = 160000;
const MAX_PREVIEW_ITEMS = 16;
const RESUME_DB = "productHunterV5";
const RESUME_STORE = "imports";
const ACTIVE_RUN_KEY = "active";

const SWEDISH_KEYWORD_MEANINGS = {
  NO:{"lei av":"trött på","slipp":"slipp","vanskelig å":"svårt att","våkner med":"vaknar med","vondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uten å måtte":"utan att behöva","slipp å bøye deg":"slipp böja dig","spar tid":"spara tid","mindre rot":"mindre stök","gjør hverdagen enklere":"gör vardagen enklare","for deg som":"för dig som","aldri mer":"aldrig mer","mer komfort hjemme":"bekvämare hemma","problem med":"problem med"},
  DK:{"træt af":"trött på","slip for":"slipp","svært ved":"svårt att","vågner med":"vaknar med","ondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uden at skulle":"utan att behöva","slip for at bøje dig":"slipp böja dig","spar tid":"spara tid","mindre rod":"mindre stök","gør hverdagen lettere":"gör vardagen enklare","til dig der":"för dig som","aldrig mere":"aldrig mer","problem med":"problem med"},
  FI:{"helpompi arki":"enklare vardag","vaikea":"svårt","joka päivä":"varje dag","vihdoin":"äntligen","säästä aikaa":"spara tid","parempi uni":"bättre sömn","helpompi kotona":"enklare hemma","arkiongelma":"vardagsproblem","ilman että":"utan att","mukavampi":"bekvämare","vähemmän vaivaa":"mindre besvär"},
  DE:{"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne zu müssen":"utan att behöva","zeit sparen":"spara tid","besser schlafen":"sova bättre","ordnung halten":"hålla ordning","alltag leichter":"enklare vardag","weniger aufwand":"mindre besvär","problem mit":"problem med"},
  NL:{"moe van":"trött på","moeilijk om":"svårt att","elke dag":"varje dag","eindelijk":"äntligen","zonder gedoe":"utan krångel","tijd besparen":"spara tid","beter slapen":"sova bättre","opgeruimd huis":"ordnat hem","dagelijks leven makkelijker":"gör vardagen enklare","probleem met":"problem med"},
  AT:{"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne aufwand":"utan besvär","zeit sparen":"spara tid","besser schlafen":"sova bättre","alltag leichter":"enklare vardag","problem mit":"problem med"},
  CH:{"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne aufwand":"utan besvär","zeit sparen":"spara tid","mehr komfort":"mer komfort","alltag leichter":"enklare vardag","problem mit":"problem med"}
};

function esc(v){
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

function decisionClass(d){
  if(d === "TESTA FÖRST") return "best";
  if(d === "STARK KANDIDAT") return "strong";
  if(d === "BEHÅLL / MER RESEARCH") return "keep";
  return "weak";
}

function qualityLabel(v){
  const n = Number(v || 0);
  if(n >= 80) return "HIGH";
  if(n >= 55) return "MEDIUM";
  return "LOW";
}

async function fetchJson(url, options){
  const r = await fetch(url, options);
  const text = await r.text();
  let data = {};
  try{ data = text ? JSON.parse(text) : {}; }
  catch(_){ throw new Error(r.ok ? "Servern gav ett ogiltigt svar." : `Serverfel ${r.status}`); }
  if(!r.ok) throw new Error(data.error || `Fel ${r.status}`);
  return data;
}

function openResumeDb(){
  return new Promise((resolve,reject)=>{
    if(!window.indexedDB){ reject(new Error("IndexedDB saknas")); return; }
    const req=indexedDB.open(RESUME_DB,1);
    req.onupgradeneeded=()=>{
      const db=req.result;
      if(!db.objectStoreNames.contains(RESUME_STORE)) db.createObjectStore(RESUME_STORE,{keyPath:"key"});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error || new Error("IndexedDB-fel"));
  });
}

async function saveActiveRun(run){
  try{
    const db=await openResumeDb();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction(RESUME_STORE,"readwrite");
      tx.objectStore(RESUME_STORE).put({...run,key:ACTIVE_RUN_KEY,updatedAt:new Date().toISOString()});
      tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error);
    });
    db.close();
  }catch(_){ }
}

async function getActiveRun(){
  try{
    const db=await openResumeDb();
    const value=await new Promise((resolve,reject)=>{
      const tx=db.transaction(RESUME_STORE,"readonly");
      const req=tx.objectStore(RESUME_STORE).get(ACTIVE_RUN_KEY);
      req.onsuccess=()=>resolve(req.result || null); req.onerror=()=>reject(req.error);
    });
    db.close(); return value;
  }catch(_){ return null; }
}

async function clearActiveRun(){
  try{
    const db=await openResumeDb();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction(RESUME_STORE,"readwrite");
      tx.objectStore(RESUME_STORE).delete(ACTIVE_RUN_KEY);
      tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error);
    });
    db.close();
  }catch(_){ }
}

async function loadSystemStatus(){
  try{
    systemInfo = await fetchJson("/api/status");
    engineBadge.classList.add("online");
    engineBadge.innerHTML = `<span class="ai-dot"></span><span>V5 · ZERO CREDIT</span>`;
    engineBadge.title = systemInfo.database_persistent ? "Permanent Postgres-databas" : "SQLite används tills DATABASE_URL kopplas";
    analyzeBtn.disabled = bulkRunning;
  }catch(_){
    engineBadge.classList.remove("online");
    engineBadge.classList.add("offline");
    engineBadge.innerHTML = `<span class="ai-dot"></span><span>Server offline</span>`;
  }
}

async function loadKeyword(reset=false){
  if(reset) keywordIndex = 0;
  const d = await fetchJson(`/api/keyword?country=${encodeURIComponent(country.value)}&index=${keywordIndex}`);
  keyword.textContent = d.keyword;
  const meaning = SWEDISH_KEYWORD_MEANINGS[country.value]?.[d.keyword];
  if(country.value !== "SE" && meaning){
    keywordTranslation.textContent = `Svenska: ${meaning}`;
    keywordTranslation.style.display = "block";
  }else{
    keywordTranslation.textContent = "";
    keywordTranslation.style.display = "none";
  }
}

document.getElementById("nextKeyword").addEventListener("click", async()=>{ keywordIndex++; await loadKeyword(); });
country.addEventListener("change", ()=>loadKeyword(true));

document.getElementById("copyKeyword").addEventListener("click", async()=>{
  await navigator.clipboard.writeText(keyword.textContent);
  statusEl.textContent="Kopierat";
  setTimeout(()=>{ if(!bulkRunning) statusEl.textContent="Redo"; },900);
});

document.getElementById("clearInput").addEventListener("click",()=>{
  if(bulkRunning) return;
  adsInput.value="";
  analysisPreview.innerHTML="";
});

function previousNonEmpty(lines, from){
  for(let i=from;i>=0;i--) if(String(lines[i]||"").trim()) return i;
  return -1;
}

function splitMetaSponsoredPaste(raw){
  const lines = String(raw||"").split(/\r?\n/);
  const sponsored = /^(?:sponsrad|sponsras|sponsored|gesponsert|gesponsord|werbung|annonce|mainos)$/i;
  const starts=[];
  for(let i=0;i<lines.length;i++){
    if(!sponsored.test(lines[i].trim())) continue;
    const p1=previousNonEmpty(lines,i-1);
    const p2=p1>=0?previousNonEmpty(lines,p1-1):-1;
    if(p1<0) continue;
    let start=p1;
    if(p2>=0 && lines[p1].trim().toLocaleLowerCase()===lines[p2].trim().toLocaleLowerCase()) start=p2;
    if(!starts.length || starts[starts.length-1]!==start) starts.push(start);
  }
  if(starts.length<2) return [];
  return starts.map((start,i)=>lines.slice(start,i+1<starts.length?starts[i+1]:lines.length).join("\n").trim()).filter(Boolean);
}

function splitBulkAds(raw){
  const text=String(raw||"").trim();
  if(!text) return [];
  const explicit=text.split(/\n\s*(?:-{3,}|={3,}|#{3,}\s*AD\s*#{3,})\s*\n/i).map(x=>x.trim()).filter(Boolean);
  if(explicit.length>1) return explicit;
  const company=[...text.matchAll(/^(?:Company|Företag|Annonsör)\s*[:\-]\s*/gmi)];
  if(company.length>1){
    return company.map((m,i)=>text.slice(m.index,i+1<company.length?company[i+1].index:text.length).trim()).filter(Boolean);
  }
  const sponsored=splitMetaSponsoredPaste(text);
  if(sponsored.length>1) return sponsored;
  return [text];
}

function blockIdentity(block){
  const text=String(block||"");
  const meta=text.match(/(?:Biblioteks?-id|Library\s*ID|Bibliotheek[- ]?ID|Bibliotheks[- ]?ID)\s*:\s*(\d{5,})/i);
  return meta ? `meta:${meta[1]}` : text.replace(/\s+/g," ").trim().toLocaleLowerCase();
}

function dedupeBlocks(blocks){
  const seen=new Set(), unique=[];
  let duplicates=0;
  for(const block of blocks){
    const key=blockIdentity(block);
    if(seen.has(key)){ duplicates++; continue; }
    seen.add(key); unique.push(block);
  }
  return {unique,duplicates};
}

function makeBatches(blocks){
  const batches=[];
  let current=[], chars=0;
  for(const rawBlock of blocks){
    const block=String(rawBlock||"").trim();
    if(!block) continue;
    const extra=block.length+12;
    if(current.length && (current.length>=BATCH_SIZE || chars+extra>MAX_BATCH_CHARS)){
      batches.push(current); current=[]; chars=0;
    }
    current.push(block); chars+=extra;
  }
  if(current.length) batches.push(current);
  return batches;
}

function renderTop(items){
  if(!items?.length){ topList.innerHTML=`<div class="empty">Ingen produkt rankad ännu.</div>`; return; }
  topList.innerHTML=items.map((x,i)=>`
    <article class="rank-card" data-cluster-id="${x.id}">
      <div class="rank-top"><span class="rank-number">#${i+1}</span><span class="country-badge">${esc(x.country||"")}</span><span class="zero-mini">0 kr</span><span class="decision ${decisionClass(x.decision)}">${esc(x.decision)}</span></div>
      <div class="rank-head"><strong>${esc(x.product_name)}</strong><span>${Number(x.opportunity_score||0).toFixed(1)}</span></div>
      <p>${esc(x.problem_summary||x.problem_type||"")}</p><div class="why">${esc(x.why_short||"")}</div>
      <div class="score-grid">
        <span>Opportunity <b>${Number(x.opportunity_score||0).toFixed(1)}</b></span><span>Market Proof <b>${Number(x.market_proof||0).toFixed(1)}</b></span><span>Confidence <b>${Number(x.confidence||0).toFixed(0)}%</b></span><span>Företag <b>${x.independent_advertisers||0}</b></span><span>Annonser <b>${x.ad_count||0}</b></span><span>Status <b>${esc(x.age_status||"UNKNOWN")}</b></span><span>Data <b>${qualityLabel(x.data_quality)}</b></span>
      </div>
      ${x.companies?.length ? `<div class="company-row"><span class="company-label">Företag</span><strong class="company-name">${esc(x.companies.slice(0,4).join(" · "))}</strong></div>` : ""}
      ${systemInfo.claude_optional ? `<button type="button" class="deep-review small" data-id="${x.id}">Djupgranska med Claude</button>` : ""}
      ${x.deep_review?.summary_sv ? `<div class="deep-result">${esc(x.deep_review.summary_sv)}</div>` : ""}
    </article>`).join("");
}

function renderWatchlist(items){
  if(!watchList) return;
  if(!items?.length){ watchList.innerHTML=""; return; }
  watchList.innerHTML=`<div class="watch-title">Nya · för lite historik</div>` + items.map(x=>`<div class="watch-item"><strong>${esc(x.product_name)}</strong><span>${Number(x.opportunity_score||0).toFixed(1)}</span></div>`).join("");
}

function renderPreview(items){
  if(!items?.length){ analysisPreview.innerHTML=""; return; }
  analysisPreview.innerHTML=`<h3 class="preview-title">Senast hittade produktgrupper</h3>` + items.map(x=>`
    <article class="preview-card">
      <div class="preview-head"><div><strong>${esc(x.product_name)}</strong><small>${esc(x.category)} · ${x.ad_count||0} annonser · ${x.independent_advertisers||0} företag</small></div><span>${Number(x.opportunity_score||0).toFixed(1)}/100</span></div>
      <p>${esc(x.problem_summary||x.problem_type||"")}</p>
      <div class="metrics"><span>Proof ${Number(x.market_proof||0).toFixed(1)}</span><span>Confidence ${Number(x.confidence||0).toFixed(0)}%</span><span>${esc(x.age_status||"UNKNOWN")}</span><span>Data ${qualityLabel(x.data_quality)}</span></div>
    </article>`).join("");
}

document.addEventListener("click", async(e)=>{
  const deep=e.target.closest(".deep-review");
  if(!deep) return;
  const id=deep.dataset.id, old=deep.textContent;
  deep.disabled=true; deep.textContent="Granskar…";
  try{
    const d=await fetchJson(`/api/clusters/${id}/deep-review`,{method:"POST"});
    const card=deep.closest(".rank-card");
    let box=card.querySelector(".deep-result");
    if(!box){ box=document.createElement("div"); box.className="deep-result"; card.appendChild(box); }
    box.textContent=d.review?.summary_sv || d.review?.strongest_reason_sv || "Claude-granskning klar.";
    deep.textContent="Granskad";
  }catch(err){ statusEl.textContent=err.message; deep.textContent=old; deep.disabled=false; }
});

async function newServerJob(run){
  return fetchJson("/api/jobs",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({country:run.country,keyword:run.keyword,total_chunks:makeBatches(run.blocks).length})
  });
}

async function serverJobStillExists(jobId){
  if(!jobId) return false;
  try{ await fetchJson(`/api/jobs/${jobId}`); return true; }catch(_){ return false; }
}

async function processRun(run){
  if(bulkRunning) return;
  bulkRunning=true; analyzeBtn.disabled=true; analyzeBtn.dataset.running="1";
  const batches=makeBatches(run.blocks||[]);
  let recent=[], last=null;

  try{
    let exists=await serverJobStillExists(run.job_id);
    if(!exists){
      const fresh=await newServerJob(run);
      run.job_id=fresh.job_id;
      run.next_batch=0;
      run.processed_ads=0;
      await saveActiveRun(run);
    }

    for(let i=Number(run.next_batch||0);i<batches.length;i++){
      const batch=batches[i];
      const start=Number(run.processed_ads||0)+1;
      statusEl.textContent=`Analyserar ${start}–${Math.min(start+batch.length-1,run.blocks.length)} / ${run.blocks.length}`;
      last=await fetchJson(`/api/jobs/${run.job_id}/chunks`,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({chunk_index:i,raw:batch.join("\n\n---\n\n")})
      });
      run.next_batch=i+1;
      run.processed_ads=Number(run.processed_ads||0)+batch.length;
      await saveActiveRun(run);
      recent=[...recent,...(last.recent_clusters||[])].slice(-MAX_PREVIEW_ITEMS);
      renderTop(last.top5||[]); renderWatchlist(last.watchlist||[]); renderPreview([...recent].reverse());
    }

    const total=run.blocks.length;
    statusEl.textContent=`Klart · ${total} behandlade · ${last?.new_ads||0} nya · ${(last?.duplicate_ads||0)+Number(run.local_duplicates||0)} dubletter`;
    await clearActiveRun();
  }catch(err){
    statusEl.textContent=`Pausad · ${err.message}`;
    await saveActiveRun(run);
  }finally{
    bulkRunning=false; analyzeBtn.disabled=false; delete analyzeBtn.dataset.running; await loadSystemStatus();
  }
}

analyzeBtn.addEventListener("click", async()=>{
  if(bulkRunning) return;
  const raw=adsInput.value.trim();
  if(!raw){ statusEl.textContent="Klistra in annonser"; return; }

  bulkRunning=true; analyzeBtn.disabled=true; analyzeBtn.dataset.running="1"; statusEl.textContent="Läser annonser…";
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));

  try{
    const parsed=splitBulkAds(raw);
    const deduped=dedupeBlocks(parsed);
    if(!deduped.unique.length) throw new Error("Ingen annons hittades.");
    const run={
      job_id:null,
      country:country.value,
      keyword:keyword.textContent,
      blocks:deduped.unique,
      next_batch:0,
      processed_ads:0,
      local_duplicates:deduped.duplicates,
      createdAt:new Date().toISOString()
    };
    const job=await newServerJob(run);
    run.job_id=job.job_id;
    await saveActiveRun(run);
    bulkRunning=false; analyzeBtn.disabled=false; delete analyzeBtn.dataset.running;
    await processRun(run);
  }catch(err){
    statusEl.textContent=err.message;
    bulkRunning=false; analyzeBtn.disabled=false; delete analyzeBtn.dataset.running;
  }
});

document.getElementById("resetBtn").addEventListener("click", async()=>{
  if(bulkRunning){ statusEl.textContent="Analysen kör fortfarande"; return; }
  if(!confirm("Ta bort V5-biblioteket och Top 5?")) return;
  await clearActiveRun();
  const d=await fetchJson("/api/reset",{method:"POST"});
  renderTop(d.top5||[]); renderWatchlist(d.watchlist||[]); analysisPreview.innerHTML=""; statusEl.textContent="Nollställt";
});

async function resumeIfNeeded(){
  const run=await getActiveRun();
  if(!run?.blocks?.length || bulkRunning) return;
  statusEl.textContent=`Fortsätter tidigare analys · ${Number(run.processed_ads||0)} / ${run.blocks.length}`;
  await processRun(run);
}

async function boot(){
  await loadKeyword(true); await loadSystemStatus();
  try{ const d=await fetchJson("/api/top"); renderTop(d.top5||[]); renderWatchlist(d.watchlist||[]); }catch(_){ }
  await resumeIfNeeded();
}
boot();
