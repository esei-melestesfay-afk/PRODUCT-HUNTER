let keywordIndex = 0;
const country = document.getElementById("country");
const keyword = document.getElementById("keyword");
const statusEl = document.getElementById("status");
const adsInput = document.getElementById("adsInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const topList = document.getElementById("topList");
const analysisPreview = document.getElementById("analysisPreview");
const claudeBadge = document.getElementById("claudeBadge");

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
  }catch(_){}
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
  if(!items.length){
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
      </div>
    </article>
  `).join("");
}

function renderPreview(items){
  if(!items.length){
    analysisPreview.innerHTML = "";
    return;
  }
  analysisPreview.innerHTML = `<h3 class="preview-title">Senaste Claude-analysen</h3>` + items.map(x=>`
    <article class="preview-card">
      <div class="preview-head">
        <div>
          <strong>${esc(x.product_name)}</strong>
          <small>${esc(x.country)} · Claude</small>
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

analyzeBtn.addEventListener("click", async()=>{
  const raw = adsInput.value.trim();
  if(!raw){
    statusEl.textContent="Klistra in annonser";
    return;
  }

  analyzeBtn.disabled=true;
  statusEl.textContent="Claude analyserar varje annons...";

  try{
    const r = await fetch("/api/analyze",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        raw,
        country:country.value,
        keyword:keyword.textContent
      })
    });
    const d = await r.json();
    if(!r.ok) throw new Error(d.error || "Fel");

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

document.getElementById("resetBtn").addEventListener("click", async()=>{
  if(!confirm("Ta bort hela kandidatbiblioteket och Top 5?")) return;
  const r = await fetch("/api/reset",{method:"POST"});
  const d = await r.json();
  renderTop(d.top5||[]);
  analysisPreview.innerHTML="";
  statusEl.textContent="Nollställt";
});

loadKeyword(true);
loadSystemStatus();