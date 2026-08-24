let keywordIndex = 0;
const country = document.getElementById("country");
const keyword = document.getElementById("keyword");
const statusEl = document.getElementById("status");
const adsInput = document.getElementById("adsInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const topList = document.getElementById("topList");
const analysisPreview = document.getElementById("analysisPreview");
const claudeBadge = document.getElementById("claudeBadge");

const BACKUP_KEY = "productHunterV4_adBackup";
const MAX_BACKUP_ADS = 250;

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
    // If storage is full, keep only the latest 80 ads.
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
    analyzeBtn.disabled = !d.claude_ready;
    if(!d.claude_ready){
      analyzeBtn.title = "Lägg ANTHROPIC_API_KEY i Render Environment Variables.";
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
}

document.getElementById("nextKeyword").addEventListener("click", async()=>{
  keywordIndex++;
  await loadKeyword();
});
country.addEventListener("change", ()=>loadKeyword(true));

document.getElementById("copyKeyword").addEventListener("click", async()=>{
  await navigator.clipboard.writeText(keyword.textContent);
  statusEl.textContent = "Kopierat";
  setTimeout(()=>statusEl.textContent="Redo",1000);
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

analyzeBtn.addEventListener("click", async()=>{
  const raw = adsInput.value.trim();
  if(!raw){
    statusEl.textContent="Klistra in annonser";
    return;
  }

  analyzeBtn.disabled=true;
  statusEl.textContent="Claude analyserar varje annons...";

  try{
    const d = await runAnalysis(raw, country.value, keyword.textContent);
    renderPreview(d.analyzed);
    renderTop(d.top5);
    statusEl.textContent = `${d.count} AI-analyserade · ${d.duplicates_skipped} dubletter · ${d.library_count} totalt`;
  }catch(e){
    statusEl.textContent=e.message;
  }finally{
    analyzeBtn.disabled=false;
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

    analyzeBtn.disabled = true;
    const groups = {};
    for(const x of backup){
      const c = x.country || "SE";
      (groups[c] ||= []).push(x.raw_text);
    }

    let last = null;
    let restored = 0;
    for(const [c, raws] of Object.entries(groups)){
      for(let i=0; i<raws.length; i+=100){
        const batch = raws.slice(i,i+100).join("\n\n---\n\n");
        statusEl.textContent = `Återställer backup... ${restored}/${backup.length}`;
        last = await runAnalysis(batch, c, "browser-backup");
        restored += Math.min(100, raws.length-i);
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
    analyzeBtn.disabled = false;
    await loadSystemStatus();
  }
}

document.getElementById("resetBtn").addEventListener("click", async()=>{
  if(!confirm("Ta bort hela kandidatbiblioteket, Top 5 och webbläsarens backup?")) return;
  localStorage.removeItem(BACKUP_KEY);
  const r = await fetch("/api/reset",{method:"POST"});
  const d = await r.json();
  renderTop(d.top5||[]);
  analysisPreview.innerHTML="";
  statusEl.textContent="Nollställt";
});

async function boot(){
  await loadKeyword(true);
  await loadSystemStatus();
  await maybeOfferRestore();
}
boot();
