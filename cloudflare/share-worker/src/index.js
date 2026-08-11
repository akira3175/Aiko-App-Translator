const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'private, no-store','x-robots-tag':'noindex, nofollow'}});

const readerHtml=`<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>Aiko Reader</title>
<style>
:root{color-scheme:dark;--paper:#1b1c1e;--ink:#f1f0ec;--muted:#a4a49f;--line:rgba(255,255,255,.12);--surface:#242527;--surface-hover:#2b2c2f;--focus:#d7d3c8}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Times New Roman",Times,serif;font-size:18px}.shell{width:100%;margin:auto;padding:36px 28px 80px}.top{width:min(100%,780px);margin:0 auto 38px;padding-bottom:24px;border-bottom:1px solid var(--line)}.brand small,.meta{color:var(--muted);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px;line-height:1.5}.brand small{letter-spacing:.12em}.brand h1{margin:8px 0 7px;color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:34px;font-weight:650;letter-spacing:-.025em;line-height:1.2;overflow-wrap:anywhere}.reader-layout{display:grid;grid-template-columns:240px minmax(0,780px) 240px;gap:32px;justify-content:center;align-items:start}.content{grid-column:2;grid-row:1;min-width:0;padding:10px 0 24px;color:var(--ink);font:18px/1.72 "Times New Roman",Times,serif;overflow-wrap:anywhere;user-select:none}.controls{grid-column:3;grid-row:1;position:sticky;top:28px;display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--surface);box-shadow:0 14px 40px rgba(0,0,0,.16);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}.nav-label{grid-column:1/-1;color:var(--muted);font-size:11px;font-weight:650;letter-spacing:.12em}.controls select{grid-column:1/-1}.controls button,.controls select{min-width:0;height:44px;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:#1f2022;color:var(--ink);font:500 14px/1.2 system-ui,-apple-system,"Segoe UI",sans-serif}.controls select{padding-right:34px;text-overflow:ellipsis}.controls button{cursor:pointer;transition:background-color .15s ease,border-color .15s ease,transform .1s ease}.controls button:hover:not(:disabled){background:var(--surface-hover);border-color:rgba(255,255,255,.2)}.controls button:active:not(:disabled){transform:translateY(1px)}.controls button:focus-visible,.controls select:focus-visible{outline:2px solid var(--focus);outline-offset:2px}.controls button:disabled{opacity:.35;cursor:default}.content h1,.content h2,.content h3{color:var(--ink);line-height:1.3;margin:1.25em 0 .65em}.content h1{font-size:1.72em;letter-spacing:-.02em}.content h2{font-size:1.38em}.content h3{font-size:1.16em}.content p{margin:0 0 1.05em;white-space:pre-wrap}.content strong{color:#fff;font-weight:700}.content em{color:#d6d4ce}.content figure{margin:26px 0;text-align:center}.content img{display:block;max-width:100%;height:auto;margin:auto;border-radius:12px}.content figcaption{margin-top:9px;color:var(--muted);font:12px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}.status{padding:80px 10px;text-align:center;color:var(--muted);font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}.footer{width:min(100%,780px);margin:48px auto 0;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);text-align:center;font:12px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}@media(max-width:1370px){.shell{width:min(100%,836px);padding:28px 28px 64px}.top{margin-bottom:18px;padding-bottom:20px}.reader-layout{display:flex;flex-direction:column;gap:0}.controls{position:sticky;top:0;z-index:3;width:calc(100% + 16px);margin:0 -8px 22px;padding:10px 8px;grid-template-columns:48px minmax(160px,1fr) 48px;background:rgba(27,28,30,.94);backdrop-filter:blur(14px);border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none}.nav-label{display:none}.controls select{grid-column:2;grid-row:1}.controls button:first-of-type{grid-column:1;grid-row:1}.controls button:last-of-type{grid-column:3;grid-row:1}.controls button span{display:none}.content{width:100%;padding-top:8px}}@media(max-width:600px){.shell{padding:20px 16px 56px}.brand h1{font-size:28px}.top{margin-bottom:12px;padding-bottom:16px}.content{font-size:17px;line-height:1.68}.content h1{font-size:1.48em}.controls{width:calc(100% + 12px);margin-inline:-6px;padding-inline:6px;grid-template-columns:44px minmax(120px,1fr) 44px}}
@media(max-width:1370px){.shell{padding-bottom:calc(112px + env(safe-area-inset-bottom))}.controls{position:fixed;top:auto;right:auto;bottom:0;left:50%;width:min(calc(100% - 24px),780px);margin:0;padding:10px 8px calc(10px + env(safe-area-inset-bottom));transform:translateX(-50%);border:1px solid var(--line);border-bottom:0;border-radius:12px 12px 0 0;box-shadow:0 -12px 40px rgba(0,0,0,.22)}}@media(max-width:600px){.shell{padding-bottom:calc(104px + env(safe-area-inset-bottom))}.controls{width:calc(100% - 12px);margin:0;padding-inline:6px}}
</style></head><body><main class="shell"><header class="top"><div class="brand"><small>AIKO PRIVATE READER</small><h1 id="title">Đang mở bản đọc…</h1><div class="meta" id="meta"></div></div></header><div class="reader-layout"><nav class="controls" aria-label="Điều hướng chương"><span class="nav-label">ĐIỀU HƯỚNG CHƯƠNG</span><select id="chapters" aria-label="Chọn chương"></select><button id="prev" aria-label="Chương trước">← <span>Trước</span></button><button id="next" aria-label="Chương tiếp"><span>Sau</span> →</button></nav><article class="content" id="content"><div class="status">Đang xác thực bản chia sẻ…</div></article></div><footer class="footer">Nội dung riêng tư · Không phát tán lại</footer></main><noscript><div class="status">Trình duyệt đang tắt JavaScript.</div></noscript><script src="/reader.js" defer></script></body></html>`;

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
select.addEventListener('change',function(){this.blur();loadChapter(select.selectedIndex);});prev.addEventListener('click',function(){this.blur();loadChapter(index-1);});next.addEventListener('click',function(){this.blur();loadChapter(index+1);});
document.addEventListener('keydown',function(event){
  var target=event.target,tag=target&&target.tagName;
  if((event.key===' '||event.code==='Space')&&tag==='BUTTON'){event.preventDefault();target.blur();scrollBy({top:(event.shiftKey?-1:1)*Math.max(innerHeight*.8,320),behavior:'smooth'});return;}
  if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey||event.shiftKey||event.repeat||tag==='SELECT'||tag==='INPUT'||tag==='TEXTAREA'||target&&target.isContentEditable)return;
  if(event.key==='ArrowLeft'){event.preventDefault();loadChapter(index-1);}else if(event.key==='ArrowRight'){event.preventDefault();loadChapter(index+1);}
});
document.addEventListener('contextmenu',function(event){event.preventDefault();});open();
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
      const extension=name.split('.').pop().toLowerCase();
      const inferredType={webp:'image/webp',avif:'image/avif',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif'}[extension];
      const contentType=image.content_type&&image.content_type!=='application/octet-stream'?image.content_type:(inferredType||'application/octet-stream');
      return new Response(object.body,{headers:{'content-type':contentType,'cache-control':'private, no-store','x-content-type-options':'nosniff'}});
    }
    const name=decodeURIComponent(match[2]);
    const chapter=(manifest.chapters||[]).find(item=>item.name===name);
    if(!chapter)return json({error:'Chapter not shared'},404);
    const object=await env.SHARE_BUCKET.get(chapter.key);
    if(!object)return json({error:'Chapter missing'},404);
    return new Response(object.body,{headers:{'content-type':chapter.format==='html'?'text/html; charset=utf-8':'text/plain; charset=utf-8','cache-control':'private, no-store','x-robots-tag':'noindex, nofollow','content-security-policy':"default-src 'none'"}});
  }
};
