const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'private, no-store','x-robots-tag':'noindex, nofollow'}});

const readerHtml=`<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>Aiko Reader</title>
<style>
:root{color-scheme:dark;--paper:#222222;--ink:#ffffff;--muted:#b8b8b8;--line:#444444;--surface:#2b2b2b}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Times New Roman",Times,serif;font-size:18px}.shell{width:min(100%,960px);margin:auto;padding:24px 24px 72px}.top{position:sticky;top:0;z-index:3;margin:0 -8px 24px;padding:12px 8px 16px;background:rgba(34,34,34,.96);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}.brand{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-bottom:12px}.brand small,.meta{color:var(--muted);font-size:13px;line-height:1.4}.brand h1{margin:3px 0 0;font-size:28px;line-height:1.25}.controls{display:grid;grid-template-columns:44px minmax(150px,1fr) 44px;gap:8px}.controls button,.controls select{min-width:0;padding:10px 12px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:16px/1.25 "Times New Roman",Times,serif}.controls button{cursor:pointer}.controls button:disabled{opacity:.35;cursor:default}.content{padding:4px 4px 20px;color:var(--ink);font:18px/1.5 "Times New Roman",Times,serif;overflow-wrap:anywhere;user-select:none}.content h1,.content h2,.content h3{line-height:1.25;margin:1em 0 .55em}.content h1{font-size:1.5em}.content h2{font-size:1.3em}.content h3{font-size:1.15em}.content p{margin:0 0 .95em;white-space:pre-wrap}.content strong{color:#fff;font-weight:700}.content em{color:#ddd}.content figure{margin:20px 0;text-align:center}.content img{display:block;max-width:min(100%,720px);height:auto;margin:auto;border-radius:8px}.content figcaption{margin-top:7px;color:var(--muted);font-size:13px}.status{padding:80px 10px;text-align:center;color:var(--muted);font-size:16px;line-height:1.6}.footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);text-align:center;font-size:13px}@media(max-width:600px){.shell{padding:16px 14px 56px}.top{margin:0 -2px 18px;padding:10px 2px 14px}.brand{align-items:start;flex-direction:column;gap:5px}.brand h1{font-size:24px}.content{padding-inline:2px}}
</style></head><body><main class="shell"><header class="top"><div class="brand"><div><small>AIKO PRIVATE READER</small><h1 id="title">Đang mở bản đọc…</h1></div><div class="meta" id="meta"></div></div><div class="controls"><button id="prev" aria-label="Chương trước">←</button><select id="chapters" aria-label="Chọn chương"></select><button id="next" aria-label="Chương tiếp">→</button></div></header><article class="content" id="content"><div class="status">Đang xác thực bản chia sẻ…</div></article><footer class="footer">Nội dung riêng tư · Không phát tán lại</footer></main><noscript><div class="status">Trình duyệt đang tắt JavaScript.</div></noscript><script src="/reader.js" defer></script></body></html>`;

const readerScript=`(function(){
var params=new URLSearchParams(location.search),share=params.get('share')||'',token=params.get('token')||'',manifest=null,index=0;
var title=document.getElementById('title'),meta=document.getElementById('meta'),select=document.getElementById('chapters'),content=document.getElementById('content'),prev=document.getElementById('prev'),next=document.getElementById('next');
try{if(token)sessionStorage.setItem('aiko-share-'+share,token);else token=sessionStorage.getItem('aiko-share-'+share)||'';}catch(_error){}
if(token&&share){params.delete('token');history.replaceState(null,'',location.pathname+'?'+params.toString());}
function fail(message){title.textContent='Không mở được bản đọc';meta.textContent='';select.innerHTML='';content.textContent=message;prev.disabled=next.disabled=true;}
function auth(){return {'Authorization':'Bearer '+token};}
function updateButtons(){prev.disabled=index<=0;next.disabled=!manifest||index>=manifest.chapters.length-1;}
async function loadImages(){var images=[].slice.call(content.querySelectorAll('[data-share-image]'));await Promise.all(images.map(async function(image){try{var response=await fetch('/v1/shares/'+encodeURIComponent(share)+'/images/'+encodeURIComponent(image.dataset.shareImage),{headers:auth(),cache:'no-store'});if(!response.ok)throw Error('image');image.src=URL.createObjectURL(await response.blob());}catch(_error){image.remove();}}));}
async function loadChapter(position){
  if(!manifest||!manifest.chapters[position])return;index=position;select.selectedIndex=position;updateButtons();content.innerHTML='<div class="status">Đang tải chương…</div>';
  try{var item=manifest.chapters[position],response=await fetch('/v1/shares/'+encodeURIComponent(share)+'/chapters/'+encodeURIComponent(item.name),{headers:auth(),cache:'no-store'});if(!response.ok)throw Error((await response.json()).error||'Không tải được chương');var chapterHtml=await response.text();if(item.format==='html'){content.innerHTML=chapterHtml;await loadImages();}else{content.textContent=chapterHtml;}scrollTo({top:0,behavior:'instant'});}catch(error){content.textContent=error.message;}
}
async function open(){
  if(!share||!token)return fail('Link chia sẻ thiếu mã truy cập.');
  try{var response=await fetch('/v1/shares/'+encodeURIComponent(share)+'/manifest',{headers:auth(),cache:'no-store'});if(!response.ok)throw Error((await response.json()).error||'Không mở được bản chia sẻ');manifest=await response.json();title.textContent=manifest.title||'Bản đọc chia sẻ';meta.textContent=(manifest.chapters||[]).length+' chương · hết hạn '+String(manifest.expires_at||'').slice(0,10);select.innerHTML='';(manifest.chapters||[]).forEach(function(item){var option=document.createElement('option');option.value=item.name;option.textContent=item.title||item.name;select.appendChild(option);});if(!manifest.chapters||!manifest.chapters.length)return fail('Bản chia sẻ chưa có chương.');await loadChapter(0);}catch(error){fail(error.message);}
}
select.addEventListener('change',function(){loadChapter(select.selectedIndex);});prev.addEventListener('click',function(){loadChapter(index-1);});next.addEventListener('click',function(){loadChapter(index+1);});document.addEventListener('contextmenu',function(event){event.preventDefault();});open();
})();`;

const reader=()=>new Response(readerHtml,{headers:{'content-type':'text/html; charset=utf-8','cache-control':'private, no-store','x-robots-tag':'noindex, nofollow, noarchive','referrer-policy':'no-referrer','content-security-policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src blob: https: data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}});

async function sha256(value){
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
}

function bearer(request){
  const value=request.headers.get('authorization')||'';
  return value.startsWith('Bearer ')?value.slice(7):'';
}

async function loadManifest(env,id){
  const object=await env.SHARE_BUCKET.get(`shares/${id}/manifest.json`);
  if(!object)return null;
  return JSON.parse(await object.text());
}

export default {
  async fetch(request,env){
    if(request.method!=='GET')return json({error:'Method not allowed'},405);
    const url=new URL(request.url);
    if(url.pathname==='/'||url.pathname==='/index.html')return reader();
    if(url.pathname==='/reader.js')return new Response(readerScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'private, no-store','x-content-type-options':'nosniff','cross-origin-resource-policy':'same-origin'}});
    const manifestMatch=url.pathname.match(/^\/v1\/shares\/([a-f0-9]+)\/manifest$/);
    const chapterMatch=url.pathname.match(/^\/v1\/shares\/([a-f0-9]+)\/chapters\/([^/]+)$/);
    const imageMatch=url.pathname.match(/^\/v1\/shares\/([a-f0-9]+)\/images\/([^/]+)$/);
    const match=manifestMatch||chapterMatch||imageMatch;
    if(!match)return json({error:'Not found'},404);
    const manifest=await loadManifest(env,match[1]);
    if(!manifest)return json({error:'Share not found'},404);
    if(new Date(manifest.expires_at).getTime()<=Date.now())return json({error:'Share expired'},410);
    const token=bearer(request);
    if(!token||await sha256(token)!==manifest.token_hash)return json({error:'Unauthorized'},401);
    if(manifestMatch){
      const {token_hash,...safe}=manifest;
      return json(safe);
    }
    if(imageMatch){
      const name=decodeURIComponent(imageMatch[2]);
      const image=(manifest.chapters||[]).flatMap(item=>item.images||[]).find(item=>item.name===name);
      if(!image)return json({error:'Image not shared'},404);
      const object=await env.SHARE_BUCKET.get(image.key);
      if(!object)return json({error:'Image missing'},404);
      return new Response(object.body,{headers:{'content-type':image.content_type||'application/octet-stream','cache-control':'private, no-store','x-content-type-options':'nosniff'}});
    }
    const name=decodeURIComponent(match[2]);
    const chapter=(manifest.chapters||[]).find(item=>item.name===name);
    if(!chapter)return json({error:'Chapter not shared'},404);
    const object=await env.SHARE_BUCKET.get(chapter.key);
    if(!object)return json({error:'Chapter missing'},404);
    return new Response(object.body,{headers:{'content-type':chapter.format==='html'?'text/html; charset=utf-8':'text/plain; charset=utf-8','cache-control':'private, no-store','x-robots-tag':'noindex, nofollow','content-security-policy':"default-src 'none'"}});
  }
};
