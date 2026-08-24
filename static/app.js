let keywordIndex = 0;
const country = document.getElementById("country");
const keyword = document.getElementById("keyword");
const keywordTranslation = document.getElementById("keywordTranslation");
const statusEl = document.getElementById("status");
const adsInput = document.getElementById("adsInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const stopAnalyzeBtn = document.getElementById("stopAnalyze");
const topList = document.getElementById("topList");
const analysisPreview = document.getElementById("analysisPreview");
const claudeBadge = document.getElementById("claudeBadge");
const bulkProgress = document.getElementById("bulkProgress");
const bulkProgressBar = document.getElementById("bulkProgressBar");
const bulkProgressText = document.getElementById("bulkProgressText");

const BACKUP_KEY = "productHunterV4_adBackup";
const MAX_BACKUP_ADS = 250;
const MAX_BULK_ADS = 1000;
const BULK_BATCH_SIZE = 40;
const MAX_BATCH_CHARS = 220000;
const MAX_PREVIEW_ITEMS = 20;

let bulkRunning = false;
let bulkCancelled = false;

const SWEDISH_KEYWORD_MEANINGS = {
  NO: {
    "lei av":"trött på","slipp":"slipp","vanskelig å":"svårt att","våkner med":"vaknar med",
    "vondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uten å måtte":"utan att behöva",
    "slipp å bøye deg":"slipp böja dig","spar tid":"spara tid","mindre rot":"mindre stök",
    "gjør hverdagen enklere":"gör vardagen enklare","for deg som":"för dig som","aldri mer":"aldrig mer",
    "mer komfort hjemme":"bekvämare hemma","problem med":"problem med"
  },
  DK: {
    "træt af":"trött på","slip for":"slipp","svært ved":"svårt att","vågner med":"vaknar med",
    "ondt i":"ont i","hver dag":"varje dag","endelig":"äntligen","uden at skulle":"utan att behöva",
    "slip for at bøje dig":"slipp böja dig","spar tid":"spara tid","mindre rod":"mindre stök",
    "gør hverdagen lettere":"gör vardagen enklare","til dig der":"för dig som","aldrig mere":"aldrig mer",
    "problem med":"problem med"
  },
  FI: {
    "helpompi arki":"enklare vardag","vaikea":"svårt","joka päivä":"varje dag","vihdoin":"äntligen",
    "säästä aikaa":"spara tid","parempi uni":"bättre sömn","helpompi kotona":"enklare hemma",
    "arkiongelma":"vardagsproblem","ilman että":"utan att","mukavampi":"bekvämare",
    "vähemmän vaivaa":"mindre besvär"
  },
  DE: {
    "müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen",
    "ohne zu müssen":"utan att behöva","zeit sparen":"spara tid","besser schlafen":"sova bättre",
    "ordnung halten":"hålla ordning","alltag leichter":"enklare vardag","weniger aufwand":"mindre besvär",
    "problem mit":"problem med"
  },
  NL: {
    "moe van":"trött på","moeilijk om":"svårt att","elke dag":"varje dag","eindelijk":"äntligen",
    "zonder gedoe":"utan krångel","tijd besparen":"spara tid","beter slapen":"sova bättre",
    "opgeruimd huis":"ordnat hem","dagelijks leven makkelijker":"gör vardagen enklare",
    "probleem met":"problem med"
  },
  AT: {
    "müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen",
    "ohne aufwand":"utan besvär","zeit sparen":"spara tid","besser schlafen":"sova bättre",
    "alltag leichter":"enklare vardag","problem mit":"problem med"
  },
  CH: {
    "müde von":"trött på","schwer zu":"svårt att","jeden tag":"varje dag","endlich":"äntligen",
    "ohne aufwand":"utan besvär","zeit sparen":"spara tid","mehr komfort":"mer komfort",
    "alltag leichter":"enklare vardag","problem mit":"problem med"
  }
};

function esc(v){
  return String(v ?? "")
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");
}

function companyRow(name){
  const value = String(name || "Okänt företag").trim() || "Okänt företag";
  return `
    <div class="company-row">
      <span class="company-label">Företag</span>
      <strong class="company-name">${esc(value)}</strong>
      <button type="button" class="copy-company small" data-company="${esc(value)}">Kopiera</button>
    </div>
  `;
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
  }catch(_){
    return [];
  }
}

function saveBackup(items){
  if(!Array.isArray(items) || !items.length) return;
  const old = getBackup();
  const map = new Map();
  for(const x of old){
    if(x?.raw_text) map.set(x.key || x.raw_text.slice(0,250), x);
  }
  for(const x of items){
    if(!x?.raw_text) continue;
    const raw = String(x.raw_text).slice(0,12000);
    const key = x.meta_library_id ? `meta:${x.meta_library_id}` : (x.fingerprint || raw.slice(0,250));
    map.set(key, {
      key,
      raw_text: raw,
      country: x.country || "SE",
      company: x.company || "",
      saved_at: new Date().toISOString()
    });
  }
  const compact = Array.from(map.values()).slice(-MAX_BACKUP_ADS);
  try{
    localStorage.setItem(BACKUP_KEY, JSON.stringify(compact));
  }catch(_){
    try{ localStorage.setItem(BACKUP_KEY, JSON.stringify(compact.slice(-80))); }catch(__){}
  }
}

async function loadSystemStatus(){
  try{
    const r = await fetch("/api/status");
    const d = await r.json();
    claudeBadge.classList.toggle("online", !!d.claude_ready);
    claudeBadge.classList.toggle("offline", !d.claude_ready);
    claudeBadge.innerHTML = `
      <span class="ai-dot"></span>
      <span>${d.claude_ready ? `Claude AI · ${esc(d.model)}` : "Claude API saknas"}</span>
    `;
    analyzeBtn.disabled = bulkRunning || !d.claude_ready;
    if(!d.claude_ready){
      analyzeBtn.title = "Lägg ANTHROPIC_API_KEY i Render Environment Variables.";
    }else{
      analyzeBtn.title = "";
    }
    return !!d.claude_ready;
  }catch(_){
    return false;
  }
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

document.getElementById("nextKeyword").addEventListener("click", async()=>{
  keywordIndex++;
  await loadKeyword();
});
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
    setTimeout(()=>btn.textContent=old, 1000);
  }catch(_){
    statusEl.textContent = "Kunde inte kopiera";
  }
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
  if(!items?.length){
    topList.innerHTML = `<div class="empty">Ingen Claude-analyserad produkt rankad ännu.</div>`;
    return;
  }
  topList.innerHTML = items.map((x,i)=>`
    <article class="rank-card">
      <div class="rank-top">
        <span class="rank-number">#${i+1}</span>
        <span class="country-badge">${esc(x.country)}</span>
        <span class="ai-mini">AI</span>
        <span class="decision ${decisionClass(x.decision)}">${esc(x.decision)}</span>
      </div>
      <div class="rank-head">
        <strong>${esc(x.product_name)}</strong>
        <span>${Number(x.final_score||0).toFixed(1)}</span>
      </div>
      ${companyRow(x.company)}
      <p>${esc(x.problem_summary)}</p>
      <div class="why">${esc(x.why_short)}</div>
      <div class="score-grid">
        <span>Problem <b>${x.problem_strength}/10</b></span>
        <span>35+ <b>${x.fit35_score}/10</b></span>
        <span>Evergreen <b>${x.evergreen_score}/10</b></span>
        <span>Proof <b>${x.market_validation_score}/10</b></span>
        <span>Betalningsvilja <b>${x.willingness_to_pay}/10</b></span>
        <span>AI confidence <b>${x.ai_confidence}/10</b></span>
        <span>Annons <b>${esc(evidenceLabel(x))}</b></span>
        ${x.meta_library_id ? `<span>Meta ID <b>${esc(x.meta_library_id)}</b></span>` : ""}
      </div>
    </article>
  `).join("");
}

function renderPreview(items){
  if(!items?.length){
    analysisPreview.innerHTML = "";
    return;
  }
  analysisPreview.innerHTML = `<h3 class="preview-title">Senaste Claude-analysen</h3>` + items.map(x=>`
    <article class="preview-card">
      <div class="preview-head">
        <div>
          <strong>${esc(x.product_name)}</strong>
          <small>${esc(x.country)} · Claude · ${esc(evidenceLabel(x))}</small>
        </div>
        <span>${Number(x.final_score||0).toFixed(1)}/100</span>
      </div>
      ${companyRow(x.company)}
      <p>${esc(x.problem_summary)}</p>
      ${x.purchase_reason ? `<div class="purchase-reason">${esc(x.purchase_reason)}</div>` : ""}
      <div class="metrics">
        <span>Problem ${x.problem_strength}/10</span>
        <span>Frequency ${x.frequency_score}/10</span>
        <span>Emotion ${x.emotion_score}/10</span>
        <span>35+ ${x.fit35_score}/10</span>
        <span>Evergreen ${x.evergreen_score}/10</span>
        <span>WTP ${x.willingness_to_pay}/10</span>
        <span>Clarity ${x.clarity_score}/10</span>
        <span>Demo ${x.demo_score}/10</span>
        <span>Proof ${x.market_validation_score}/10</span>
        <span>AI confidence ${x.ai_confidence}/10</span>
      </div>
      ${x.why_could_win ? `<div class="ai-why"><b>Varför:</b> ${esc(x.why_could_win)}</div>` : ""}
      ${x.why_could_fail ? `<div class="warnings"><b>Risk:</b> ${esc(x.why_could_fail)}</div>` : ""}
      ${x.red_flags?.length ? `<div class="warnings">⚠ ${esc(x.red_flags.join(" · "))}</div>` : ""}
    </article>
  `).join("");
}

function previousNonEmpty(lines, from){
  for(let i=from; i>=0; i--){
    if(String(lines[i] || "").trim()) return i;
  }
  return -1;
}

function splitMetaSponsoredPaste(raw){
  const lines = String(raw || "").split(/\r?\n/);
  const sponsored = /^(?:sponsrad|sponsras|sponsored|gesponsert|gesponsord|werbung|annonce|mainos)$/i;
  const starts = [];

  for(let i=0; i<lines.length; i++){
    if(!sponsored.test(lines[i].trim())) continue;
    const p1 = previousNonEmpty(lines, i-1);
    const p2 = p1 >= 0 ? previousNonEmpty(lines, p1-1) : -1;
    if(p1 < 0) continue;

    let start = p1;
    if(p2 >= 0 && lines[p1].trim().toLocaleLowerCase() === lines[p2].trim().toLocaleLowerCase()){
      start = p2;
    }
    if(!starts.length || starts[starts.length-1] !== start) starts.push(start);
  }

  if(starts.length < 2) return [];
  const out = [];
  for(let i=0; i<starts.length; i++){
    const end = i+1 < starts.length ? starts[i+1] : lines.length;
    const block = lines.slice(starts[i], end).join("\n").trim();
    if(block) out.push(block);
  }
  return out;
}

function splitBulkAds(raw){
  const text = String(raw || "").trim();
  if(!text) return [];

  const explicit = text
    .split(/\n\s*(?:-{3,}|={3,}|#{3,}\s*AD\s*#{3,})\s*\n/i)
    .map(x=>x.trim())
    .filter(Boolean);
  if(explicit.length > 1) return explicit;

  const companyMatches = [...text.matchAll(/^(?:Company|Företag|Annonsör)\s*[:\-]\s*/gmi)];
  if(companyMatches.length > 1){
    const out = [];
    for(let i=0; i<companyMatches.length; i++){
      const start = companyMatches[i].index;
      const end = i+1 < companyMatches.length ? companyMatches[i+1].index : text.length;
      const block = text.slice(start, end).trim();
      if(block) out.push(block);
    }
    return out;
  }

  const meta = splitMetaSponsoredPaste(text);
  if(meta.length > 1) return meta;

  return [text];
}

function blockIdentity(block){
  const text = String(block || "");
  const meta = text.match(/(?:Biblioteks?-id|Library\s*ID)\s*:\s*(\d{5,})/i);
  if(meta) return `meta:${meta[1]}`;
  return text.replace(/\s+/g," ").trim().toLocaleLowerCase();
}

function dedupeBlocks(blocks){
  const seen = new Set();
  const unique = [];
  let duplicates = 0;
  for(const block of blocks){
    const key = blockIdentity(block);
    if(seen.has(key)){
      duplicates++;
      continue;
    }
    seen.add(key);
    unique.push(block);
  }
  return {unique, duplicates};
}

function makeSafeBatches(blocks){
  const batches = [];
  let current = [];
  let chars = 0;

  for(const rawBlock of blocks){
    const block = String(rawBlock || "").trim();
    if(!block) continue;
    if(block.length > MAX_BATCH_CHARS){
      throw new Error("En annons/textdel är extremt stor. Lägg --- mellan annonserna så systemet kan dela upp dem rätt.");
    }

    const extra = block.length + 12;
    if(current.length && (current.length >= BULK_BATCH_SIZE || chars + extra > MAX_BATCH_CHARS)){
      batches.push(current);
      current = [];
      chars = 0;
    }
    current.push(block);
    chars += extra;
  }
  if(current.length) batches.push(current);
  return batches;
}

function setProgress(done, total){
  const safeTotal = Math.max(1, Number(total || 0));
  const pct = Math.max(0, Math.min(100, (Number(done || 0) / safeTotal) * 100));
  bulkProgress.style.display = "block";
  bulkProgressBar.style.width = `${pct}%`;
  bulkProgressText.textContent = `${done} / ${total} annonser`;
}

function hideProgress(){
  bulkProgress.style.display = "none";
  bulkProgressBar.style.width = "0%";
  bulkProgressText.textContent = "0 / 0";
}

function sleep(ms){
  return new Promise(resolve=>setTimeout(resolve, ms));
}

async function runAnalysis(raw, selectedCountry, selectedKeyword){
  const r = await fetch("/api/analyze",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({raw, country:selectedCountry, keyword:selectedKeyword})
  });
  const d = await r.json();
  if(!r.ok) throw new Error(d.error || "Fel");
  saveBackup(d.analyzed || []);
  return d;
}

async function runAnalysisBlocks(blocks, selectedCountry, selectedKeyword){
  return runAnalysis(blocks.join("\n\n---\n\n"), selectedCountry, selectedKeyword);
}

async function runBatchWithRecovery(blocks, selectedCountry, selectedKeyword, depth=0){
  let lastError = null;

  try{
    return [await runAnalysisBlocks(blocks, selectedCountry, selectedKeyword)];
  }catch(e){
    lastError = e;
  }

  if(depth === 0 && !bulkCancelled){
    await sleep(1600);
    try{
      return [await runAnalysisBlocks(blocks, selectedCountry, selectedKeyword)];
    }catch(e){
      lastError = e;
    }
  }

  if(blocks.length > 8 && depth < 3 && !bulkCancelled){
    const mid = Math.ceil(blocks.length / 2);
    const left = await runBatchWithRecovery(blocks.slice(0, mid), selectedCountry, selectedKeyword, depth+1);
    if(bulkCancelled) return left;
    const right = await runBatchWithRecovery(blocks.slice(mid), selectedCountry, selectedKeyword, depth+1);
    return [...left, ...right];
  }

  throw lastError || new Error("Batchen kunde inte analyseras.");
}

stopAnalyzeBtn.addEventListener("click", ()=>{
  if(!bulkRunning) return;
  bulkCancelled = true;
  stopAnalyzeBtn.disabled = true;
  statusEl.textContent = "Stoppar efter nuvarande batch...";
});

analyzeBtn.addEventListener("click", async()=>{
  const raw = adsInput.value.trim();
  if(!raw){
    statusEl.textContent="Klistra in annonser";
    return;
  }

  let parsed;
  try{
    parsed = splitBulkAds(raw);
  }catch(e){
    statusEl.textContent = e.message;
    return;
  }

  if(parsed.length > MAX_BULK_ADS){
    statusEl.textContent = `Jag hittade ${parsed.length} annonser. Max är ${MAX_BULK_ADS} per stor körning.`;
    return;
  }

  const deduped = dedupeBlocks(parsed);
  const blocks = deduped.unique;
  if(!blocks.length){
    statusEl.textContent = "Ingen annons hittades";
    return;
  }

  let batches;
  try{
    batches = makeSafeBatches(blocks);
  }catch(e){
    statusEl.textContent = e.message;
    return;
  }

  if(blocks.length >= 200){
    const ok = confirm(
      `${blocks.length} unika annonser hittades.\n\n` +
      `Systemet analyserar dem automatiskt i ${batches.length} säkra batcher. Det kan ta tid och använder Claude API-kredit.\n\nStarta?`
    );
    if(!ok){
      statusEl.textContent = "Avbrutet";
      return;
    }
  }

  bulkRunning = true;
  bulkCancelled = false;
  analyzeBtn.disabled = true;
  stopAnalyzeBtn.disabled = false;
  stopAnalyzeBtn.style.display = "inline-block";
  setProgress(0, blocks.length);

  let processed = 0;
  let totalNew = 0;
  let totalDuplicates = deduped.duplicates;
  let libraryCount = 0;
  let recent = [];
  let lastTop = [];

  try{
    for(let i=0; i<batches.length; i++){
      if(bulkCancelled) break;
      const batch = batches[i];
      statusEl.textContent = `Claude analyserar ${processed + 1}–${Math.min(processed + batch.length, blocks.length)} av ${blocks.length}...`;

      const responses = await runBatchWithRecovery(batch, country.value, keyword.textContent);
      for(const d of responses){
        totalNew += Number(d.count || 0);
        totalDuplicates += Number(d.duplicates_skipped || 0);
        libraryCount = Number(d.library_count || libraryCount || 0);
        lastTop = d.top5 || lastTop;
        recent = [...recent, ...(d.analyzed || [])].slice(-MAX_PREVIEW_ITEMS);
        renderTop(lastTop);
        renderPreview([...recent].reverse());
      }

      processed += batch.length;
      setProgress(processed, blocks.length);
    }

    if(bulkCancelled){
      statusEl.textContent = `Stoppad · ${processed}/${blocks.length} behandlade · ${totalNew} nya`;
    }else{
      setProgress(blocks.length, blocks.length);
      statusEl.textContent = `KLART · ${blocks.length} behandlade · ${totalNew} nya · ${totalDuplicates} dubletter · ${libraryCount} totalt`;
    }
  }catch(e){
    statusEl.textContent = `Stannade vid ${processed}/${blocks.length}: ${e.message}`;
  }finally{
    bulkRunning = false;
    stopAnalyzeBtn.style.display = "none";
    stopAnalyzeBtn.disabled = false;
    await loadSystemStatus();
  }
});

async function maybeOfferRestore(){
  try{
    const r = await fetch("/api/top");
    const d = await r.json();
    if(Number(d.library_count || 0) > 0) return;
    const backup = getBackup();
    if(!backup.length) return;

    const ok = confirm(
      `Render-databasen verkar tom, men den här webbläsaren har backup av ${backup.length} annonser.\n\n` +
      `Vill du återställa dem? Claude behöver analysera dem igen, så det använder API-kredit.`
    );
    if(!ok) return;

    bulkRunning = true;
    analyzeBtn.disabled = true;
    const groups = {};
    for(const x of backup){
      const c = x.country || "SE";
      (groups[c] ||= []).push(x.raw_text);
    }

    let last = null;
    let restored = 0;
    for(const [c, raws] of Object.entries(groups)){
      const batches = makeSafeBatches(raws);
      for(const batch of batches){
        statusEl.textContent = `Återställer backup... ${restored}/${backup.length}`;
        last = await runAnalysisBlocks(batch, c, "browser-backup");
        restored += batch.length;
      }
    }
    if(last){
      renderTop(last.top5 || []);
      renderPreview(last.analyzed || []);
    }
    statusEl.textContent = `Backup återställd · ${restored} annonser`;
  }catch(e){
    statusEl.textContent = `Backup kunde inte återställas: ${e.message}`;
  }finally{
    bulkRunning = false;
    await loadSystemStatus();
  }
}

document.getElementById("resetBtn").addEventListener("click", async()=>{
  if(bulkRunning){
    statusEl.textContent = "Stoppa analysen först";
    return;
  }
  if(!confirm("Ta bort hela kandidatbiblioteket, Top 5 och webbläsarens backup?")) return;
  localStorage.removeItem(BACKUP_KEY);
  const r = await fetch("/api/reset",{method:"POST"});
  const d = await r.json();
  renderTop(d.top5||[]);
  analysisPreview.innerHTML="";
  hideProgress();
  statusEl.textContent="Nollställt";
});

async function boot(){
  await loadKeyword(true);
  await loadSystemStatus();
  await maybeOfferRestore();
}
boot();
