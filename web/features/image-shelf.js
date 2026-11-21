const natural = new Intl.Collator('vi',{numeric:true,sensitivity:'base'});
const fold = text => text.toLowerCase().normalize('NFD').replace(/\p{M}/gu,'').replaceAll('đ','d');
const compareChapter = (a,b) => a[0]-b[0] || a[1]-b[1] || a[2]-b[2];

export function shelfEntry(item){
  const chapters=[item.name,...(item.chapters||[])].flatMap(id=>{
    const m=/^v(\d+)_c(\d+)_s(\d+)(?=[_.]|$)/i.exec(id);
    return m?[[Number(m[1]),Number(m[2]),Number(m[3])]]:[];
  }).sort(compareChapter);
  let url=item.url;
  try{url=decodeURIComponent(url.split('?')[0]);}catch{}
  const number=Number(item.name.match(/_(\d+)\.[^.]+$/)?.[1]||0);
  return {item,chapters,number,text:fold([item.name,url,...(item.chapters||[])].join(' '))};
}

export function compareImages(a,b){
  if(a.chapters.length && b.chapters.length){
    const order=compareChapter(a.chapters[0],b.chapters[0]) || a.number-b.number;
    if(order)return order;
  }else if(Boolean(a.chapters.length)!==Boolean(b.chapters.length))return a.chapters.length?-1:1;
  return natural.compare(a.item.name,b.item.name)||natural.compare(a.item.url,b.item.url);
}

export function shelfFilter(query){
  const fields=[];
  const rest=fold(query).replace(/(?:^|\s)(vol(?:ume)?|tap|v|chapter|chap|chuong|c)\s*[:#]?\s*(\d+)(?=\s|$)/g,(_,key,n)=>{
    fields.push([/^(v|tap)/.test(key)?0:1,Number(n)]);return ' ';
  }).trim().split(/\s+/).filter(Boolean);
  return entry=>(!fields.length||entry.chapters.some(ch=>fields.every(([i,n])=>ch[i]===n))) &&
    rest.every(term=>entry.text.includes(term));
}

export function imageLineEnd(text,item){
  const local=item.url.startsWith('/api/image/');
  for(const [line,value] of text.split('\n').entries()){
    const matches=value.matchAll(/!\[[^\]\n]*\]\(([^)\n]+)\)|\[img(?:=[^\]]+)?\]([^\[\n]+)\[\/img\]/gi);
    for(const match of matches){
      const ref=match[1]??match[2];
      if(local ? ref==='../image/'+item.name || ref==='image/'+item.name : ref===item.url)
        return {line,ch:value.length};
    }
  }
  return null;
}

export function bindImageShelf({api,state,toast,openChapter,editorFeature,showView}) {
  const el=id=>document.querySelector('#'+id);
  const dialog=el('imageShelf');
  if(!dialog)return;
  const grid=el('imageShelfItems'), status=el('imageShelfStatus'), file=el('imageShelfFile');
  const search=el('imageShelfSearch');
  let endpoint, entries=[];
  search.oninput=render;
  async function refresh(url){
    status.textContent='Đang tải ảnh…';
    grid.replaceChildren();
    const {items}=await api(url);
    if(url!==endpoint||!dialog.open)return;
    entries=items.map(shelfEntry).sort(compareImages);
    render();
  }
  function render(){
    grid.replaceChildren();
    const items=entries.filter(shelfFilter(search.value)).map(entry=>entry.item);
    status.textContent=search.value.trim()?items.length+' / '+entries.length+' ảnh':items.length?items.length+' ảnh':'Truyện chưa có ảnh.';
    for(const item of items){
      const card=document.createElement('article'), img=document.createElement('img');
      const name=document.createElement('p'), button=document.createElement('button');
      img.src=item.url; img.loading='lazy'; img.alt=item.name; img.referrerPolicy='no-referrer';
      const match=item.name.match(/^v(\d+)_c(\d+)_s(\d+)_img_.*?_(\d+)\.[^.]+$/i);
      name.textContent=match?'Tập '+match[1]+' · Chương '+match[2]+' · Ảnh '+Number(match[4]):item.name;
      const linked=new Set((item.chapters||[]).map(id=>id+'.md'));
      if(!linked.size){
        const id=item.name.match(/^(v\d+_c\d+_s\d+)(?:_|\.)/i)?.[1];
        if(id)linked.add(id+'.md');
      }
      const chapter=state.chapters.find(ch=>ch.name===state.current&&linked.has(ch.name))
        ||state.chapters.find(ch=>linked.has(ch.name));
      if(chapter){
        img.title='Nhấp đúp để mở '+chapter.name;
        img.tabIndex=0;
        img.setAttribute('role','button');
        img.setAttribute('aria-label',img.title);
        const jump=async()=>{
          const project=state.project;
          if(state.current!==chapter.name && !await openChapter(chapter.name))return;
          if(state.project!==project||state.current!==chapter.name)return;
          dialog.close();
          showView('workspace');
          const view=editorFeature.views.target;
          const cursor=imageLineEnd(view.getValue(),item);
          if(!cursor)return;
          editorFeature.setWorkspaceMode(window.innerWidth<1000?'target':'split',false);
          editorFeature.setEditorMode('target-text');
          requestAnimationFrame(()=>{
            if(state.project!==project||state.current!==chapter.name)return;
            view.refresh();view.setCursor(cursor);view.scrollIntoView(cursor,90);view.focus();
          });
        };
        card.ondblclick=event=>{if(!button.contains(event.target))jump();};
        img.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();jump();}};
      }
      name.title=item.name;
      button.textContent='Sao chép mã ảnh';
      button.className='shelf-copy';
      button.onclick=async()=>{
        try{
          if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(item.markup);
          else {
            const input=document.createElement('textarea');input.value=item.markup;dialog.append(input);
            input.select();const copied=document.execCommand('copy');input.remove();
            if(!copied)throw Error();
          }
          button.textContent='✓ Đã sao chép';
          clearTimeout(button.resetLabel);
          button.resetLabel=setTimeout(()=>button.textContent='Sao chép mã ảnh',1800);
        }catch{status.textContent=item.markup;}
      };
      card.append(img,name,button);grid.append(card);
    }
  }
  el('imageShelfButton').onclick=()=>{
    if(!state.project)return toast('Hãy chọn truyện trước');
    endpoint='/api/image-shelf?project='+encodeURIComponent(state.project);
    entries=[];search.value='';dialog.showModal();search.focus();refresh(endpoint).catch(e=>status.textContent=e.message);
  };
  el('imageShelfClose').onclick=()=>dialog.close();
  el('imageShelfAdd').onclick=()=>file.click();
  file.onchange=async()=>{
    const url=endpoint, files=Array.from(file.files);file.value='';
    try{
      for(const image of files){
        await api(url+'&name='+encodeURIComponent(image.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:image});
      }
      if(url===endpoint&&dialog.open)await refresh(url);
    }catch(e){status.textContent=e.message;}
  };
}
