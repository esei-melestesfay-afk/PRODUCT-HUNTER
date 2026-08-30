(()=>{
  const HYBRID_UI_VERSION="5.5";

  function signalText(x){
    const labels=Array.isArray(x?.signal_labels)?x.signal_labels:[];
    if(!labels.length) return "";
    const names={
      "STRONG PROBLEM PRODUCT":"Starkt problem",
      "HIGH EMOTIONAL BUYING MOTIVE":"Högt emotionellt köpmotiv",
      "HIGH PURCHASE URGENCY":"Hög köp-urgency",
      "STRONG DEMO PRODUCT":"Stark demo",
      "NICE-TO-HAVE RISK":"Nice-to-have risk"
    };
    return labels.map(v=>names[v]||v).join(" · ");
  }

  function softMetric(v){ return Number(v||0).toFixed(1); }
  function finalMetric(x){ return Number(x?.final_score ?? x?.opportunity_score ?? 0).toFixed(1); }
  function aiBadge(x){ return x?.claude_reviewed ? "CLAUDE ✓" : "V5"; }

  renderTop=function(items){
    if(!items?.length){ topList.innerHTML=`<div class="empty">Ingen produkt rankad ännu.</div>`; return; }
    topList.innerHTML=items.map((x,i)=>`
      <article class="rank-card" data-cluster-id="${x.id}" data-hybrid-ui="${HYBRID_UI_VERSION}">
        <div class="rank-top"><span class="rank-number">#${i+1}</span><span class="country-badge">${esc(x.country||"")}</span><span class="zero-mini">${aiBadge(x)}</span><span class="decision ${decisionClass(x.decision)}">${esc(x.decision)}</span></div>
        <div class="rank-head"><strong>${esc(x.product_name)}</strong><span>${finalMetric(x)}</span></div>
        <p>${esc(x.problem_summary||x.problem_type||"")}</p>
        <div class="why">${esc(x.why_short||"")}</div>
        ${signalText(x)?`<div style="margin:7px 0 3px;font-size:11px;font-weight:750;line-height:1.45;opacity:.9">${esc(signalText(x))}</div>`:""}
        <div class="score-grid">
          <span>FINAL <b>${finalMetric(x)}</b></span>
          <span>V5 <b>${Number(x.deterministic_score ?? x.opportunity_score ?? 0).toFixed(1)}</b></span>
          <span>Claude <b>${x.claude_reviewed ? Number(x.claude_score||0).toFixed(1) : "—"}</b></span>
          <span>Problem <b>${softMetric(x.problem_solving_score)}</b></span>
          <span>Emotion <b>${softMetric(x.emotional_pressure_score)}</b></span>
          <span>Urgency <b>${softMetric(x.purchase_urgency_score)}</b></span>
          <span>Demo <b>${softMetric(x.demo_wow_score)}</b></span>
          <span>Market Proof <b>${Number(x.market_proof||0).toFixed(1)}</b></span>
          <span>Confidence <b>${Number(x.confidence||0).toFixed(0)}%</b></span>
          <span>Företag <b>${x.independent_advertisers||0}</b></span>
          <span>Annonser <b>${x.ad_count||0}</b></span>
          <span>Status <b>${esc(x.age_status||"UNKNOWN")}</b></span>
        </div>
        ${x.companies?.length ? `<div class="company-row"><span class="company-label">Företag</span><strong class="company-name">${esc(x.companies.slice(0,4).join(" · "))}</strong></div>` : ""}
        ${x.deep_review?.summary_sv ? `<div class="deep-result"><strong>Claude:</strong> ${esc(x.deep_review.summary_sv)}</div>` : ""}
        ${systemInfo.claude_optional ? `<button type="button" class="deep-review small" data-id="${x.id}">${x.claude_reviewed ? "Granska igen med Claude" : "Djupgranska med Claude"}</button>` : ""}
      </article>`).join("");
  };

  renderPreview=function(items){
    if(!items?.length){ analysisPreview.innerHTML=""; return; }
    analysisPreview.innerHTML=`<h3 class="preview-title">Senast hittade produktgrupper</h3>` + items.map(x=>`
      <article class="preview-card">
        <div class="preview-head"><div><strong>${esc(x.product_name)}</strong><small>${esc(x.category)} · ${x.ad_count||0} annonser · ${x.independent_advertisers||0} företag</small></div><span>${finalMetric(x)}/100</span></div>
        <p>${esc(x.problem_summary||x.problem_type||"")}</p>
        ${signalText(x)?`<div class="why">${esc(signalText(x))}</div>`:""}
        <div class="metrics"><span>Final ${finalMetric(x)}</span><span>Problem ${softMetric(x.problem_solving_score)}</span><span>Emotion ${softMetric(x.emotional_pressure_score)}</span><span>Proof ${Number(x.market_proof||0).toFixed(1)}</span>${x.claude_reviewed?`<span>Claude ${Number(x.claude_score||0).toFixed(1)}</span>`:""}</div>
      </article>`).join("");
  };

  setTimeout(async()=>{
    try{
      const d=await fetchJson("/api/top");
      renderTop(d.top5||[]);
      renderWatchlist(d.watchlist||[]);
    }catch(_){ }
  },100);
})();
