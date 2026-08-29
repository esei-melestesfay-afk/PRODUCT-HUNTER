(()=>{
  const DB_NAME="productHunterV5Persistence";
  const DB_VERSION=1;
  const CHUNKS="chunks";
  const JOBS="jobs";
  const originalFetch=window.fetch.bind(window);

  function openDb(){
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DB_NAME,DB_VERSION);
      req.onupgradeneeded=()=>{
        const db=req.result;
        if(!db.objectStoreNames.contains(CHUNKS)) db.createObjectStore(CHUNKS,{keyPath:"id"});
        if(!db.objectStoreNames.contains(JOBS)) db.createObjectStore(JOBS,{keyPath:"job_id"});
      };
      req.onsuccess=()=>resolve(req.result);
      req.onerror=()=>reject(req.error);
    });
  }

  async function tx(store,mode,fn){
    const db=await openDb();
    return new Promise((resolve,reject)=>{
      const t=db.transaction(store,mode);
      const s=t.objectStore(store);
      let value;
      try{ value=fn(s); }catch(e){ db.close(); reject(e); return; }
      t.oncomplete=()=>{ db.close(); resolve(value); };
      t.onerror=()=>{ db.close(); reject(t.error); };
      t.onabort=()=>{ db.close(); reject(t.error); };
    });
  }

  async function digest(text){
    const data=new TextEncoder().encode(String(text||""));
    const hash=await crypto.subtle.digest("SHA-256",data);
    return Array.from(new Uint8Array(hash)).map(x=>x.toString(16).padStart(2,"0")).join("");
  }

  async function putJob(job){
    if(!job?.job_id) return;
    await tx(JOBS,"readwrite",s=>s.put(job));
  }

  async function getJob(jobId){
    const db=await openDb();
    return new Promise((resolve,reject)=>{
      const t=db.transaction(JOBS,"readonly");
      const r=t.objectStore(JOBS).get(jobId);
      r.onsuccess=()=>resolve(r.result||null);
      r.onerror=()=>reject(r.error);
      t.oncomplete=()=>db.close();
    });
  }

  async function putChunk(record){
    await tx(CHUNKS,"readwrite",s=>s.put(record));
  }

  async function getAllChunks(){
    const db=await openDb();
    return new Promise((resolve,reject)=>{
      const t=db.transaction(CHUNKS,"readonly");
      const r=t.objectStore(CHUNKS).getAll();
      r.onsuccess=()=>resolve(r.result||[]);
      r.onerror=()=>reject(r.error);
      t.oncomplete=()=>db.close();
    });
  }

  async function clearArchive(){
    const db=await openDb();
    return new Promise((resolve,reject)=>{
      const t=db.transaction([CHUNKS,JOBS],"readwrite");
      t.objectStore(CHUNKS).clear();
      t.objectStore(JOBS).clear();
      t.oncomplete=()=>{ db.close(); resolve(); };
      t.onerror=()=>{ db.close(); reject(t.error); };
    });
  }

  function parseBody(options){
    try{
      if(!options?.body || typeof options.body!=="string") return null;
      return JSON.parse(options.body);
    }catch(_){ return null; }
  }

  window.fetch=async function(input,options={}){
    const url=typeof input==="string"?input:(input?.url||"");
    const method=String(options?.method||"GET").toUpperCase();
    const body=parseBody(options);
    const response=await originalFetch(input,options);

    try{
      if(response.ok && method==="POST" && url==="/api/jobs"){
        const data=await response.clone().json();
        await putJob({
          job_id:data.job_id,
          country:body?.country||"SE",
          keyword:body?.keyword||"",
          created_at:new Date().toISOString()
        });
      }

      const chunkMatch=url.match(/^\/api\/jobs\/([^/]+)\/chunks$/);
      if(response.ok && method==="POST" && chunkMatch && body?.raw){
        const job=await getJob(chunkMatch[1]);
        const id=await digest(body.raw);
        await putChunk({
          id,
          raw:String(body.raw),
          country:job?.country||"SE",
          keyword:job?.keyword||"",
          saved_at:new Date().toISOString()
        });
      }

      if(response.ok && method==="POST" && url==="/api/reset"){
        await clearArchive();
      }
    }catch(err){
      console.warn("Product Hunter persistence warning",err);
    }

    return response;
  };

  async function restoreIfNeeded(){
    try{
      const top=await originalFetch("/api/top").then(r=>r.json());
      if(Number(top.library_count||0)>0) return;

      const archived=await getAllChunks();
      if(!archived.length) return;

      const statusEl=document.getElementById("status");
      const groups=new Map();
      for(const row of archived){
        const key=`${row.country||"SE"}\u0000${row.keyword||""}`;
        if(!groups.has(key)) groups.set(key,[]);
        groups.get(key).push(row);
      }

      let restored=0;
      if(statusEl) statusEl.textContent=`Återställer bibliotek · ${archived.length} delar`;

      for(const [key,rows] of groups){
        const [country,keyword]=key.split("\u0000");
        const create=await originalFetch("/api/jobs",{
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({country,keyword,total_chunks:rows.length})
        });
        if(!create.ok) throw new Error(`Restore job ${create.status}`);
        const job=await create.json();

        for(let i=0;i<rows.length;i++){
          if(statusEl) statusEl.textContent=`Återställer ${restored+1} / ${archived.length}`;
          const r=await originalFetch(`/api/jobs/${job.job_id}/chunks`,{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({chunk_index:i,raw:rows[i].raw})
          });
          if(!r.ok) throw new Error(`Restore chunk ${r.status}`);
          restored++;
        }
      }

      if(statusEl) statusEl.textContent=`Återställt · ${restored} delar`;
      // Always reload after a successful restore so Top 5 and the current
      // database state are rendered from the restored server data.
      setTimeout(()=>location.reload(),700);
    }catch(err){
      console.warn("Product Hunter auto-restore warning",err);
    }
  }

  window.ProductHunterPersistence={
    count:async()=> (await getAllChunks()).length,
    clear:clearArchive,
    restore:restoreIfNeeded,
  };

  window.addEventListener("load",()=>setTimeout(restoreIfNeeded,1400));
})();
