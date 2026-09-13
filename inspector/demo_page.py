"""Self-contained HTML for the bulk demo page (served at GET /).

Kept as a single string so the project needs no template/static folders and stays
fully portable and offline.
"""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>QMS Inspector - Demo</title>
<style>
  :root{--bg:#0f172a;--card:#1e293b;--muted:#94a3b8;--line:#334155;
        --ok:#22c55e;--defect:#ef4444;--uncertain:#f59e0b;--accent:#38bdf8;}
  *{box-sizing:border-box}
  body{margin:0;font-family:Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:#e2e8f0}
  header{padding:20px 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px}
  header h1{font-size:20px;margin:0}
  header .tag{font-size:12px;color:var(--muted);background:#0b1220;border:1px solid var(--line);
        padding:3px 9px;border-radius:999px}
  main{max-width:1200px;margin:0 auto;padding:24px}
  .drop{border:2px dashed var(--line);border-radius:14px;padding:34px;text-align:center;
        background:var(--card);transition:.15s;cursor:pointer}
  .drop.drag{border-color:var(--accent);background:#16243b}
  .drop h2{margin:.2em 0;font-size:17px}
  .drop p{color:var(--muted);margin:.3em 0}
  .btn{display:inline-block;margin-top:12px;background:var(--accent);color:#04283a;font-weight:700;
        border:none;padding:11px 20px;border-radius:9px;cursor:pointer;font-size:14px}
  .btn:disabled{opacity:.5;cursor:default}
  #summary{display:none;gap:12px;flex-wrap:wrap;margin:22px 0}
  .stat{flex:1;min-width:130px;background:var(--card);border:1px solid var(--line);
        border-radius:12px;padding:14px 16px}
  .stat .n{font-size:26px;font-weight:700}
  .stat .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
  .stat.defect .n{color:var(--defect)} .stat.ok .n{color:var(--ok)} .stat.unc .n{color:var(--uncertain)}
  .filters{display:none;gap:8px;margin:6px 0 18px;flex-wrap:wrap}
  .chip{background:var(--card);border:1px solid var(--line);color:#cbd5e1;padding:7px 13px;
        border-radius:999px;cursor:pointer;font-size:13px}
  .chip.active{background:var(--accent);color:#04283a;border-color:var(--accent);font-weight:700}
  #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  .card img{width:100%;height:200px;object-fit:cover;display:block;background:#000;cursor:zoom-in}
  .card .body{padding:10px 12px}
  .badge{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;color:#04121f}
  .badge.DEFECT{background:var(--defect);color:#fff} .badge.OK{background:var(--ok)}
  .badge.UNCERTAIN{background:var(--uncertain)}
  .part{display:inline-block;font-size:11px;color:#cbd5e1;background:#0b1220;border:1px solid var(--line);
        padding:3px 8px;border-radius:999px;margin-left:6px}
  .card .name{font-size:12px;color:var(--muted);margin-top:8px;word-break:break-all}
  .card .def{font-size:13px;margin-top:6px}
  .spin{display:none;margin:26px auto;text-align:center;color:var(--muted)}
  .loader{width:34px;height:34px;border:4px solid var(--line);border-top-color:var(--accent);
        border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 10px}
  @keyframes spin{to{transform:rotate(360deg)}}
  #lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9;
        align-items:center;justify-content:center;flex-direction:column;padding:24px}
  #lightbox img{max-width:92%;max-height:82%;border-radius:8px}
  #lightbox .tools{margin-top:14px;display:flex;gap:10px}
  #lightbox .tools button{background:var(--card);color:#e2e8f0;border:1px solid var(--line);
        padding:8px 16px;border-radius:8px;cursor:pointer}
  footer{color:var(--muted);text-align:center;font-size:12px;padding:24px}
</style>
</head>
<body>
<header>
  <h1>QMS Inspector</h1>
  <span class="tag">100% offline &middot; 0 tokens &middot; instant</span>
</header>
<main>
  <div id="drop" class="drop">
    <h2>Drop images or a .zip here</h2>
    <p>or click to choose files &mdash; bulk upload supported</p>
    <input id="file" type="file" multiple accept="image/*,.zip" hidden/>
    <button class="btn" id="pick">Choose files</button>
  </div>

  <div id="summary"></div>
  <div id="filters" class="filters">
    <span class="chip active" data-f="ALL">All</span>
    <span class="chip" data-f="DEFECT">Defect</span>
    <span class="chip" data-f="OK">OK</span>
    <span class="chip" data-f="UNCERTAIN">Uncertain</span>
  </div>
  <div id="partfilters" class="filters"></div>

  <div class="spin" id="spin"><div class="loader"></div>Inspecting&hellip;</div>
  <div id="grid"></div>
</main>

<div id="lightbox">
  <img id="lbImg" src=""/>
  <div class="tools">
    <button id="lbToggle">Show original</button>
    <button id="lbClose">Close</button>
  </div>
</div>

<footer>QMS Inspector demo &middot; results computed locally on this machine</footer>

<script>
const drop=document.getElementById('drop'), file=document.getElementById('file'),
      pick=document.getElementById('pick'), grid=document.getElementById('grid'),
      spin=document.getElementById('spin'), summary=document.getElementById('summary'),
      filters=document.getElementById('filters'), partfilters=document.getElementById('partfilters'),
      lb=document.getElementById('lightbox'), lbImg=document.getElementById('lbImg'),
      lbToggle=document.getElementById('lbToggle'), lbClose=document.getElementById('lbClose');
let current='ALL', currentPart='ALL', lbPair={a:'',o:'',showOrig:false};

pick.onclick=e=>{e.stopPropagation();file.click();};
drop.onclick=()=>file.click();
file.onchange=()=>{ if(file.files.length) upload(file.files); };
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('drag');}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('drag');}));
drop.addEventListener('drop',e=>{ if(e.dataTransfer.files.length) upload(e.dataTransfer.files); });

filters.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
  filters.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
  c.classList.add('active'); current=c.dataset.f; applyFilter();
});
function applyFilter(){
  grid.querySelectorAll('.card').forEach(card=>{
    const okR=(current==='ALL'||card.dataset.result===current);
    const okP=(currentPart==='ALL'||card.dataset.part===currentPart);
    card.style.display=(okR&&okP)?'':'none';
  });
}
function buildPartFilters(byPart){
  const parts=Object.keys(byPart||{});
  if(parts.length<=1){ partfilters.style.display='none'; return; }
  let html='<span class="chip active" data-p="ALL">All parts</span>';
  for(const p of parts){ html+=`<span class="chip" data-p="${p}">${p} (${byPart[p].total})</span>`; }
  partfilters.innerHTML=html; partfilters.style.display='flex'; currentPart='ALL';
  partfilters.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    partfilters.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
    c.classList.add('active'); currentPart=c.dataset.p; applyFilter();
  });
}

async function upload(files){
  const fd=new FormData();
  for(const f of files) fd.append('files', f);
  grid.innerHTML=''; summary.style.display='none'; filters.style.display='none';
  spin.style.display='block';
  try{
    const r=await fetch('/demo/inspect',{method:'POST',body:fd});
    const data=await r.json();
    if(!r.ok){ alert(data.error||'error'); return; }
    render(data);
  }catch(err){ alert('Upload failed: '+err); }
  finally{ spin.style.display='none'; }
}

function render(data){
  const c=data.counts;
  summary.innerHTML=`
    <div class="stat"><div class="n">${data.total}</div><div class="l">Images</div></div>
    <div class="stat defect"><div class="n">${c.DEFECT}</div><div class="l">Defect</div></div>
    <div class="stat ok"><div class="n">${c.OK}</div><div class="l">OK</div></div>
    <div class="stat unc"><div class="n">${c.UNCERTAIN}</div><div class="l">Uncertain</div></div>`;
  summary.style.display='flex'; filters.style.display='flex';
  buildPartFilters(data.by_part);
  grid.innerHTML='';
  for(const it of data.results){
    if(it.error){ continue; }
    const div=document.createElement('div');
    div.className='card'; div.dataset.result=it.result; div.dataset.part=it.part||'default';
    const defTxt = it.defects && it.defects.length
        ? it.defects.map(d=>d.type+(d.severity?` (P${d.severity})`:'')).join(', ')
        : (it.result==='OK'?'No defect':'Needs review');
    const partTxt = (it.part||'part') + (it.part_confident?'':' ?');
    div.innerHTML=`
      <img src="${it.annotated_url}" data-a="${it.annotated_url}" data-o="${it.original_url}"/>
      <div class="body">
        <span class="badge ${it.result}">${it.result}</span>
        <span class="part">${partTxt}</span>
        <div class="def">${defTxt}</div>
        <div class="name">${it.name}</div>
      </div>`;
    div.querySelector('img').onclick=()=>openLb(it.annotated_url,it.original_url);
    grid.appendChild(div);
  }
  applyFilter();
}

function openLb(a,o){ lbPair={a,o,showOrig:false}; lbImg.src=a; lbToggle.textContent='Show original';
  lb.style.display='flex'; }
lbToggle.onclick=()=>{ lbPair.showOrig=!lbPair.showOrig;
  lbImg.src=lbPair.showOrig?lbPair.o:lbPair.a;
  lbToggle.textContent=lbPair.showOrig?'Show annotated':'Show original'; };
lbClose.onclick=()=>lb.style.display='none';
lb.onclick=e=>{ if(e.target===lb) lb.style.display='none'; };
</script>
</body>
</html>
"""
