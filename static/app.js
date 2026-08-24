let keywordIndex = 0;
const country = document.getElementById("country");
const keyword = document.getElementById("keyword");
const keywordTranslation = document.getElementById("keywordTranslation");
const statusEl = document.getElementById("status");
const adsInput = document.getElementById("adsInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const topList = document.getElementById("topList");
const analysisPreview = document.getElementById("analysisPreview");
const claudeBadge = document.getElementById("claudeBadge");

const BACKUP_KEY = "productHunterV4_adBackup";
const MAX_BACKUP_ADS = 250;
const BATCH_SIZE = 40;
const MAX_BATCH_CHARS = 220000;
const MAX_PREVIEW_ITEMS = 20;
let bulkRunning = false;

const SWEDISH_KEYWORD_MEANINGS = {
  NO: {"lei av":"trött på","slipp":"slipp","vanskelig å":"svårt att","våkner med":"vaknar med","vondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uten å måtte":"utan att behöva","slipp å bøye deg":"slipp böja dig","spar tid":"spara tid","mindre rot":"mindre stök","gjør hverdagen enklere":"gör vardagen enklare","for deg som":"för dig som","aldri mer":"aldrig mer","mer komfort hjemme":"bekvämare hemma","problem med":"problem med"},
  DK: {"træt af":"trött på","slip for":"slipp","svært ved":"svårt att","vågner med":"vaknar med","ondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uden at skulle":"utan att behöva","slip for at bøje dig":"slipp böja dig","spar tid":"spara tid","mindre rod":"mindre stök","gør hverdagen lettere":"gör vardagen enklare","til dig der":"för dig som","aldrig mere":"aldrig mer","problem med":"problem med"},
  FI: {"helpompi arki":"enklare vardag","vaikea":"svårt","joka päivä":"varje dag","vihdoin":"äntligen","säästä aikaa":"spara tid","parempi uni":"bättre sömn","helpompi kotona":"enklare hemma","arkiongelma":"vardagsproblem","ilman että":"utan att","mukavampi":"bekvämare","vähemmän vaivaa":"mindre besvär"},
  DE: {"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne zu müssen":"utan att behöva","zeit sparen":"spara tid","besser schlafen":"sova bättre","ordnung halten":"hålla ordning","alltag leichter":"enklare vardag","weniger aufwand":"mindre besvär","problem mit":"problem med"},
  NL: {"moe van":"trött på","moeilijk om":"svårt att","elke dag":"varje dag","eindelijk":"äntligen","zonder gedoe":"utan krångel","tijd besparen":"spara tid","beter slapen":"sova bättre","opgeruimd huis":"ordnat hem","dagelijks leven makkelijker":"gör vardagen enklare","probleem met":"problem med"},
  AT: {"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne aufwand":"utan besvär","zeit sparen":"spara tid","besser schlafen":"sova bättre","alltag leichter":"enklare vardag","problem mit":"problem med"},
  CH: {"müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen","ohne aufwand":"utan besvär","zeit sparen":"spara tid","mehr komfort":"mer komfort","alltag leichter":"enklare vardag","problem mit":"problem med"}
};

function esc(v){
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

function companyRow(name){
  const value = String(name || "Okänt företag").trim() || "Okänt företag";
  return `<div class="company-row"><span class="company-label">Företag</span><strong class="company-name">${esc(value)}</strong><button type="button" class="copy-company small" data-company="${esc(value)}">Kopiera</button></div>`;
}

function evidenceLabel(x){
  const days = Number(x.ad_age_days || 0);
  const s = String(x.ad_status || "unknown");
  if(s === "active") return days ? `Aktiv · ${days} dagar` : "Aktiv";
  if(s === "inactive") return days ? `Inaktiv · kördes ${days} dagar` : "Inaktiv";
  return days ? `${days} dagar observerat` : "Datum saknas";
}

function getBackup(){
  try{
    const data = JSON.parse(localStorage.getItem(BACKUP_KEY) || "[]");
    return Array.isArray(data) ? data : [];
  }catch(_){ return []; }
}

function saveBackup(items){
  if(!Array.isArray(items) || !items.length) return;
  const map = new Map();
  for(const x of getBackup()) if(x?.raw_text) map.set(x.key || x.raw_text.slice(0,250), x);
  for(const x of items){
    if(!x?.raw_text) continue;
    const raw = String(x.raw_text).slice(0,12000);
    const key = x.meta_library_id ? `meta:${x.meta_library_id}` : (x.fingerprint || raw.slice(0,250));
    map.set(key,{key,raw_text:raw,country:x.country||"SE",company:x.company||"",saved_at:new Date().toISOString()});
  }
  const compact = Array.from(map.values()).slice(-MAX_BACKUP_ADS);
  try{ localStorage.setItem(BACKUP_KEY, JSON.stringify(compact)); }
  catch(_){ try{ localStorage.setItem(BACKUP_KEY, JSON.stringify(compact.slice(-80))); }catch(__){} }
}

async function loadSystemStatus(){
  try{
    const r = await fetch("/api/status");
    const d = await r.json();
    claudeBadge.classList.toggle("online", !!d.claude_ready);
    claudeBadge.classList.toggle("offline", !d.claude_ready);
    claudeBadge.innerHTML = `<span class="ai-dot"></span><span>${d.claude_ready ? `Claude AI · ${esc(d.model)}` : "Claude API saknas"}</span>`;
    analyzeBtn.disabled = bulkRunning || !d.claude_ready;
    return !!d.claude_ready;
  }catch(_){ return false; }
}

async function loadKeyword(reset=false){
  if(reset) keywordIndex = 0;
  const r = await fetch(`/api/keyword?country=${encodeURIComponent(country.value)}&index=${keywordIndex}`);
  const d = await r.json();
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
  statusEl.textContent = "Kopierat";
  setTimeout(()=>{ if(!bulkRunning) statusEl.textContent="Redo"; },1000);
});

document.addEventListener("click", async(e)=>{
  const btn = e.target.closest(".copy-company");
  if(!btn) return;
  const value = btn.dataset.company || "";
  if(!value) return;
  try{
    await navigator.clipboard.writeText(value);
    const old = btn.textContent;
    btn.textContent = "Kopierat";
    setTimeout(()=>btn.textContent=old,1000);
  }catch(_){ statusEl.textContent = "Kunde inte kopiera"; }
});

document.getElementById("clearInput").addEventListener("click",()=>{
  if(bulkRunning) return;
  adsInput.value="";
  analysisPreview.innerHTML="";
});

function decisionClass(d){
  if(d === "TESTA FÖRST") return "best";
  if(d === "STARK KANDIDAT") return "strong";
  if(d === "BEHÅLL / MER RESEARCH") return "keep";
  return "weak";
}

function renderTop(items){
  if(!items?.length){ topList.innerHTML = `<div class="empty">Ingen Claude-analyserad produkt rankad ännu.</div>`; return; }
  topList.innerHTML = items.map((x,i)=>`
    <article class="rank-card">
      <div class="rank-top"><span class="rank-number">#${i+1}</span><span class="country-badge">${esc(x.country)}</span><span class="ai-mini">AI</span><span class="decision ${decisionClass(x.decision)}">${esc(x.decision)}</span></div>
      <div class="rank-head"><strong>${esc(x.product_name)}</strong><span>${Number(x.final_score||0).toFixed(1)}</span></div>
      ${companyRow(x.company)}
      <p>${esc(x.problem_summary)}</p><div class="why">${esc(x.why_short)}</div>
      <div class="score-grid">
        <span>Problem <b>${x.problem_strength}/10</b></span><span>35+ <b>${x.fit35_score}/10</b></span><span>Evergreen <b>${x.evergreen_score}/10</b></span><span>Proof <b>${x.market_validation_score}/10</b></span><span>Betalningsvilja <b>${x.willingness_to_pay}/10</b></span><span>AI confidence <b>${x.ai_confidence}/10</b></span><span>Annons <b>${esc(evidenceLabel(x))}</b></span>${x.meta_library_id ? `<span>Meta ID <b>${esc(x.meta_library_id)}</b></span>` : ""}
      </div>
    </article>`).join("");
}

function renderPreview(items){
  if(!items?.length){ analysisPreview.innerHTML=""; return; }
  analysisPreview.innerHTML = `<h3 class="preview-title">Senaste Claude-analysen</h3>` + items.map(x=>`
    <article class="preview-card">
      <div class="preview-head"><div><strong>${esc(x.product_name)}</strong><small>${esc(x.country)} · Claude · ${esc(evidenceLabel(x))}</small></div><span>${Number(x.final_score||0).toFixed(1)}/100</span></div>
      ${companyRow(x.company)}<p>${esc(x.problem_summary)}</p>${x.purchase_reason ? `<div class="purchase-reason">${esc(x.purchase_reason)}</div>` : ""}
      <div class="metrics"><span>Problem ${x.problem_strength}/10</span><span>Frequency ${x.frequency_score}/10</span><span>Emotion ${x.emotion_score}/10</span><span>35+ ${x.fit35_score}/10</span><span>Evergreen ${x.evergreen_score}/10</span><span>WTP ${x.willingness_to_pay}/10</span><span>Clarity ${x.clarity_score}/10</span><span>Demo ${x.demo_score}/10</span><span>Proof ${x.market_validation_score}/10</span><span>AI confidence ${x.ai_confidence}/10</span></div>
      ${x.why_could_win ? `<div class="ai-why"><b>Varför:</b> ${esc(x.why_could_win)}</div>` : ""}${x.why_could_fail ? `<div class="warnings"><b>Risk:</b> ${esc(x.why_could_fail)}</div>` : ""}${x.red_flags?.length ? `<div class="warnings">⚠ ${esc(x.red_flags.join(" · "))}</div>` : ""}
    </article>`).join("");
}

function previousNonEmpty(lines, from){
  for(let i=from;i>=0;i--) if(String(lines[i]||"").trim()) return i;
  return -1;
}

function splitMetaSponsoredPaste(raw){
  const lines = String(raw||"").split(/\r?\n/);
  const sponsored = /^(?:sponsrad|sponsras|sponsored|gesponsert|gesponsord|werbung|annonce|mainos)$/i;
  const starts = [];
  for(let i=0;i<lines.length;i++){
    if(!sponsored.test(lines[i].trim())) continue;
    const p1 = previousNonEmpty(lines,i-1);
    const p2 = p1>=0 ? previousNonEmpty(lines,p1-1) : -1;
    if(p1<0) continue;
    let start=p1;
    if(p2>=0 && lines[p1].trim().toLocaleLowerCase()===lines[p2].trim().toLocaleLowerCase()) start=p2;
    if(!starts.length || starts[starts.length-1]!==start) starts.push(start);
  }
  if(starts.length<2) return [];
  return starts.map((start,i)=>lines.slice(start,i+1<starts.length?starts[i+1]:lines.length).join("\n").trim()).filter(Boolean);
}

function splitByLibraryIds(raw){
  const text = String(raw||"");
  const matches = [...text.matchAll(/(?:Biblioteks?-id|Library\s*ID)\s*:\s*\d{5,}/gi)];
  if(matches.length<2) return [];
  const out=[];
  let start=0;
  for(let i=0;i<matches.length;i++){
    const end = i+1<matches.length ? matches[i+1].index : text.length;
    const block=text.slice(start,end).trim();
    if(block) out.push(block);
    start=end;
  }
  return out;
}

function splitBulkAds(raw){
  const text=String(raw||"").trim();
  if(!text) return [];
  const explicit=text.split(/\n\s*(?:-{3,}|={3,}|#{3,}\s*AD\s*#{3,})\s*\n/i).map(x=>x.trim()).filter(Boolean);
  if(explicit.length>1) return explicit;
  const companyMatches=[...text.matchAll(/^(?:Company|Företag|Annonsör)\s*[:\-]\s*/gmi)];
  if(companyMatches.length>1){
    return companyMatches.map((m,i)=>text.slice(m.index,i+1<companyMatches.length?companyMatches[i+1].index:text.length).trim()).filter(Boolean);
  }
  const meta=splitMetaSponsoredPaste(text);
  if(meta.length>1) return meta;
  const byId=splitByLibraryIds(text);
  if(byId.length>1) return byId;
  return [text];
}

function blockIdentity(block){
  const text=String(block||"");
  const meta=text.match(/(?:Biblioteks?-id|Library\s*ID)\s*:\s*(\d{5,})/i);
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

function makeSafeBatches(blocks){
  const batches=[];
  let current=[], chars=0;
  for(const rawBlock of blocks){
    const block=String(rawBlock||"").trim();
    if(!block) continue;
    if(block.length>MAX_BATCH_CHARS) throw new Error("Kunde inte dela upp texten rätt. Lägg --- mellan annonserna och försök igen.");
    const extra=block.length+12;
    if(current.length && (current.length>=BATCH_SIZE || chars+extra>MAX_BATCH_CHARS)){
      batches.push(current); current=[]; chars=0;
    }
    current.push(block); chars+=extra;
  }
  if(current.length) batches.push(current);
  return batches;
}

function sleep(ms){ return new Promise(resolve=>setTimeout(resolve,ms)); }

async function runAnalysisBlocks(blocks,selectedCountry,selectedKeyword){
  const r=await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({raw:blocks.join("\n\n---\n\n"),country:selectedCountry,keyword:selectedKeyword})});
  const d=await r.json();
  if(!r.ok) throw new Error(d.error||"Fel");
  saveBackup(d.analyzed||[]);
  return d;
}

async function runBatchWithRecovery(blocks,selectedCountry,selectedKeyword,depth=0){
  try{ return [await runAnalysisBlocks(blocks,selectedCountry,selectedKeyword)]; }
  catch(firstError){
    if(depth===0){
      await sleep(1500);
      try{ return [await runAnalysisBlocks(blocks,selectedCountry,selectedKeyword)]; }catch(_){}
    }
    if(blocks.length>5 && depth<4){
      const mid=Math.ceil(blocks.length/2);
      const left=await runBatchWithRecovery(blocks.slice(0,mid),selectedCountry,selectedKeyword,depth+1);
      const right=await runBatchWithRecovery(blocks.slice(mid),selectedCountry,selectedKeyword,depth+1);
      return [...left,...right];
    }
    throw firstError;
  }
}

analyzeBtn.addEventListener("click",async()=>{
  const raw=adsInput.value.trim();
  if(!raw){ statusEl.textContent="Klistra in annonser"; return; }

  let blocks;
  try{
    const parsed=splitBulkAds(raw);
    const deduped=dedupeBlocks(parsed);
    blocks=deduped.unique;
    if(!blocks.length){ statusEl.textContent="Ingen annons hittades"; return; }
    const batches=makeSafeBatches(blocks);

    bulkRunning=true;
    analyzeBtn.disabled=true;
    let processed=0,totalNew=0,totalDuplicates=deduped.duplicates,libraryCount=0,recent=[],lastTop=[];

    for(const batch of batches){
      statusEl.textContent=`Analyserar ${processed+1}–${Math.min(processed+batch.length,blocks.length)} av ${blocks.length}`;
      const responses=await runBatchWithRecovery(batch,country.value,keyword.textContent);
      for(const d of responses){
        totalNew+=Number(d.count||0);
        totalDuplicates+=Number(d.duplicates_skipped||0);
        libraryCount=Number(d.library_count||libraryCount||0);
        lastTop=d.top5||lastTop;
        recent=[...recent,...(d.analyzed||[])].slice(-MAX_PREVIEW_ITEMS);
        renderTop(lastTop);
        renderPreview([...recent].reverse());
      }
      processed+=batch.length;
    }
    statusEl.textContent=`Klart · ${processed} behandlade · ${totalNew} nya · ${totalDuplicates} dubletter · ${libraryCount} totalt`;
  }catch(e){
    statusEl.textContent=e.message;
  }finally{
    bulkRunning=false;
    await loadSystemStatus();
  }
});

async function maybeOfferRestore(){
  try{
    const r=await fetch("/api/top");
    const d=await r.json();
    if(Number(d.library_count||0)>0) return;
    const backup=getBackup();
    if(!backup.length) return;
    const ok=confirm(`Databasen verkar tom men den här webbläsaren har backup av ${backup.length} annonser. Återställa?`);
    if(!ok) return;
    bulkRunning=true; analyzeBtn.disabled=true;
    const groups={};
    for(const x of backup){ const c=x.country||"SE"; (groups[c] ||= []).push(x.raw_text); }
    let last=null,restored=0;
    for(const [c,raws] of Object.entries(groups)){
      for(const batch of makeSafeBatches(raws)){
        statusEl.textContent=`Återställer ${restored+1}–${restored+batch.length}`;
        last=await runAnalysisBlocks(batch,c,"browser-backup");
        restored+=batch.length;
      }
    }
    if(last){ renderTop(last.top5||[]); renderPreview(last.analyzed||[]); }
    statusEl.textContent=`Backup återställd · ${restored} annonser`;
  }catch(e){ statusEl.textContent=`Backup kunde inte återställas: ${e.message}`; }
  finally{ bulkRunning=false; await loadSystemStatus(); }
}

document.getElementById("resetBtn").addEventListener("click",async()=>{
  if(bulkRunning){ statusEl.textContent="Analysen kör fortfarande"; return; }
  if(!confirm("Ta bort hela kandidatbiblioteket, Top 5 och webbläsarens backup?")) return;
  localStorage.removeItem(BACKUP_KEY);
  const r=await fetch("/api/reset",{method:"POST"});
  const d=await r.json();
  renderTop(d.top5||[]); analysisPreview.innerHTML=""; statusEl.textContent="Nollställt";
});

async function boot(){ await loadKeyword(true); await loadSystemStatus(); await maybeOfferRestore(); }
boot();