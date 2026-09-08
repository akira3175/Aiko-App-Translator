const $=selector=>document.querySelector(selector);

export function createStorySearchFeature({api,escapeHtml,state,saveChapter,openChapter,showView,editorFeature,toast}) {
  let controller=null,timer=null,revision=0,items=[],busy=false;
  const panel=document.createElement('aside');
  panel.id='storySearchPanel';panel.hidden=true;panel.setAttribute('aria-label','Tìm trong truyện');
  panel.innerHTML=`<header><h2>Tìm trong truyện</h2><button type="button" id="closeStorySearch" aria-label="Đóng tìm kiếm">×</button></header>
    <form id="storySearchForm"><label for="storySearchQuery">Từ hoặc cụm từ</label><input id="storySearchQuery" type="search" maxlength="200" autocomplete="off" placeholder="Nhập từ cần tìm…">
    <label for="storySearchScope">Tìm trong</label><select id="storySearchScope"><option value="target">Bản dịch</option><option value="source">Bản gốc</option><option value="both">Cả hai</option></select>
    <div class="story-search-options"><label><input id="storySearchCase" type="checkbox">Phân biệt hoa thường</label><label><input id="storySearchWord" type="checkbox">Nguyên từ</label></div><button type="submit" class="secondary">Tìm kiếm</button></form>
    <p id="storySearchStatus" role="status" aria-live="polite">Nhập từ để tìm trong truyện đang mở.</p><div id="storySearchResults"></div>`;
  document.body.appendChild(panel);
  function cancel(){revision++;controller?.abort();clearTimeout(timer);}
  function close(){cancel();panel.hidden=true;document.body.classList.remove('story-search-open');$('#storySearchToggle').setAttribute('aria-expanded','false');$('#storySearchToggle').focus();}
  function reset(){cancel();items=[];$('#storySearchResults').replaceChildren();$('#storySearchStatus').textContent='Nhập từ để tìm trong truyện đang mở.';}
  function render(){
    const groups=new Map();
    items.forEach((item,index)=>{if(!groups.has(item.name))groups.set(item.name,[]);groups.get(item.name).push({...item,index});});
    $('#storySearchResults').innerHTML=[...groups].map(([name,hits])=>`<section class="story-search-group"><h3>${escapeHtml(hits[0].title)}</h3><small>${escapeHtml(name)} · ${hits.length} kết quả</small>${hits.map(hit=>`<button type="button" data-search-hit="${hit.index}"><small>${hit.kind==='source'?'Bản gốc':'Bản dịch'}</small><span>${escapeHtml(hit.before)}<mark>${escapeHtml(hit.match)}</mark>${escapeHtml(hit.after)}</span></button>`).join('')}</section>`).join('');
    return groups.size;
  }
  async function search(){
    cancel();const run=revision,project=state.project,q=$('#storySearchQuery').value.trim();
    items=[];$('#storySearchResults').replaceChildren();
    if(!project||!q){$('#storySearchStatus').textContent=project?'Nhập từ để tìm trong truyện đang mở.':'Hãy mở một truyện trước.';return;}
    controller=new AbortController();const signal=controller.signal;
    $('#storySearchStatus').textContent='Đang tìm…';
    try{
      if(state.dirty)await saveChapter();
      if(run!==revision||project!==state.project)return;
      if(state.dirty)throw new Error('Chưa lưu được chương đang sửa. Hãy lưu lại rồi tìm kiếm.');
      const params=new URLSearchParams({project,q,scope:$('#storySearchScope').value,case:$('#storySearchCase').checked?'1':'0',word:$('#storySearchWord').checked?'1':'0'});
      let cursor='0:0';
      do{
        params.set('cursor',cursor);
        const data=await api('/api/story-search?'+params,{signal});
        if(run!==revision||project!==state.project)return;
        items.push(...data.items);cursor=data.next;
        const count=render();
        $('#storySearchStatus').textContent=`${items.length} kết quả trong ${count} chương${cursor?' · Đang tìm…':''}`;
        if(items.length>=2000&&cursor){$('#storySearchStatus').textContent+=' Đã dừng ở 2.000 kết quả; hãy tìm cụm từ cụ thể hơn.';break;}
      }while(cursor);
    }catch(error){if(run===revision&&error.name!=='AbortError')$('#storySearchStatus').textContent=error.message;}
  }
  async function jump(index){
    if(busy)return;
    const hit=items[index],project=state.project,run=revision;if(!hit)return;
    busy=true;
    try{
      if(state.current!==hit.name){if(!await openChapter(hit.name))return;}
      if(project!==state.project||run!==revision)return;
      const view=editorFeature.views[hit.kind];
      if(view.getValue().slice(hit.start,hit.end)!==hit.match){toast('Nội dung đã thay đổi. Hãy tìm lại để cập nhật vị trí.');return;}
      showView('workspace');
      editorFeature.setWorkspaceMode(window.innerWidth<1000?hit.kind:'split',false);
      editorFeature.setEditorMode(hit.kind+'-text');
      if(window.innerWidth<1280)close();
      requestAnimationFrame(()=>{view.refresh();view.setSelection(view.posFromIndex(hit.start),view.posFromIndex(hit.end));view.scrollIntoView({from:view.posFromIndex(hit.start),to:view.posFromIndex(hit.end)},100);view.focus();});
    }finally{busy=false;}
  }
  function open(){if(state.projectLoading)return;panel.hidden=false;document.body.classList.add('story-search-open');$('#storySearchToggle').setAttribute('aria-expanded','true');$('#storySearchQuery').focus();editorFeature.refreshEditors();}
  function bind(){
    $('#storySearchToggle').onclick=()=>panel.hidden?open():close();$('#closeStorySearch').onclick=close;
    $('#storySearchForm').onsubmit=event=>{event.preventDefault();search();};
    $('#storySearchQuery').oninput=()=>{cancel();timer=setTimeout(search,350);};
    ['Scope','Case','Word'].forEach(key=>$('#storySearch'+key).onchange=search);
    $('#storySearchResults').onclick=event=>{const hit=event.target.closest('[data-search-hit]');if(hit)jump(Number(hit.dataset.searchHit));};
    panel.onkeydown=event=>{if(event.key==='Escape'){event.stopPropagation();close();}};
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.shiftKey&&event.key.toLowerCase()==='f'){event.preventDefault();event.stopImmediatePropagation();open();}},true);
  }
  return {bind,reset};
}
