(()=>{
  async function refreshHybridStatus(){
    try{
      const d=await fetchJson('/api/status');
      systemInfo=d;
      engineBadge.classList.remove('offline');
      engineBadge.classList.add('online');
      if(d.claude_auto){
        engineBadge.innerHTML='<span class="ai-dot"></span><span>V5 · CLAUDE HYBRID</span>';
        engineBadge.title=`V5 grovsorterar allt. Claude slutgranskar upp till ${d.claude_finalist_limit||10} finalister och cachar resultatet.`;
      }else{
        engineBadge.innerHTML='<span class="ai-dot"></span><span>CLAUDE EJ ANSLUTEN</span>';
        engineBadge.title='ANTHROPIC_API_KEY saknas. V5 kan fortfarande köra fallback.';
      }
    }catch(_){ }
  }

  const observer=new MutationObserver(()=>{
    const text=statusEl.textContent||'';
    if(text.startsWith('Klart') && systemInfo?.claude_auto && !text.includes('Claude')){
      statusEl.textContent=text+' · Claude-finalister klara';
    }
  });
  observer.observe(statusEl,{childList:true,characterData:true,subtree:true});

  document.addEventListener('click',(e)=>{
    if(!e.target.closest('.deep-review')) return;
    setTimeout(async()=>{
      try{
        const d=await fetchJson('/api/top');
        renderTop(d.top5||[]);
        renderWatchlist(d.watchlist||[]);
      }catch(_){ }
    },1800);
  });

  setTimeout(refreshHybridStatus,80);
  setTimeout(refreshHybridStatus,800);
})();
