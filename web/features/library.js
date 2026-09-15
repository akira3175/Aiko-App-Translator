const $=selector=>document.querySelector(selector);

export function createLibraryFeature({api,escapeHtml,state,renderProjectPicker,selectProject,showView,toast}) {
  let items=[],canOpenFolder=false,revision=0,loading=false;
  const busy=new Set();
  const normalized=value=>value.normalize('NFC').toLocaleLowerCase('vi');

  function render() {
    const query=normalized($('#librarySearch').value.trim()),filter=$('#libraryFilter').value;
    const visible=items.filter(item=>normalized(item.name).includes(query)&&(filter==='all'||item.hidden===(filter==='hidden')));
    $('#libraryStatus').textContent=`${visible.length} / ${items.length} truyện · ${items.filter(item=>item.hidden).length} đã ẩn khỏi danh sách chọn`;
    $('#libraryItems').innerHTML=visible.length?visible.map(item=>{
      const index=items.indexOf(item),disabled=busy.has(item.name)?'disabled':'';
      return `<article class="library-row"><div class="library-details"><h2>${escapeHtml(item.name)}</h2><p>${item.translated} / ${item.total} chương đã dịch · ${item.hidden?'Đã ẩn':'Đang hiện'}${state.project===item.name?' · Đang mở':''}</p></div><div class="library-actions"><button class="primary" type="button" data-library-action="open" data-index="${index}" ${disabled}>Mở truyện</button><button class="secondary" type="button" data-library-action="visibility" data-index="${index}" aria-label="${item.hidden?'Hiện lại':'Ẩn khỏi danh sách chọn'}: ${escapeHtml(item.name)}" ${disabled}>${item.hidden?'Hiện lại':'Ẩn khỏi danh sách'}</button><button class="secondary" type="button" data-library-action="folder" data-index="${index}" ${disabled} ${canOpenFolder?'':'disabled title="Mở thư mục cần dùng app trên máy tính đang lưu truyện"'}>Mở thư mục</button></div></article>`;
    }).join(''):`<p class="library-empty">${items.length?'Không có truyện khớp bộ lọc.':'Chưa có truyện. Bấm + Thêm truyện để bắt đầu.'}</p>`;
  }

  async function load() {
    if(busy.size)return;
    const current=++revision;
    loading=true;
    $('#libraryItems').setAttribute('aria-busy','true');
    $('#libraryRefresh').disabled=true;
    $('#libraryStatus').textContent='Đang tải thư viện…';
    try {
      const data=await api('/api/library');
      if(current!==revision)return;
      items=data.items;canOpenFolder=data.can_open_folder;
      state.projects=items.map(item=>item.name);
      state.hiddenProjects=items.filter(item=>item.hidden).map(item=>item.name);
      renderProjectPicker();render();
    } catch(error) {
      if(current===revision)$('#libraryStatus').textContent=`Không tải được thư viện: ${error.message}. Bấm Làm mới để thử lại.`;
    } finally {
      if(current===revision){loading=false;$('#libraryItems').setAttribute('aria-busy','false');$('#libraryRefresh').disabled=false;}
    }
  }

  function bind() {
    $('#librarySearch').oninput=()=>{if(!loading)render();};
    $('#libraryFilter').onchange=()=>{if(!loading)render();};
    $('#libraryRefresh').onclick=load;
    $('#libraryItems').onclick=async event=>{
      const button=event.target.closest('[data-library-action]');
      if(!button||button.disabled||loading)return;
      const item=items[Number(button.dataset.index)],action=button.dataset.libraryAction;
      if(!item||busy.has(item.name))return;
      busy.add(item.name);render();
      try {
        if(action==='open') {
          await selectProject(item.name);
          if(state.project===item.name&&!state.projectLoading)showView('workspace');
        } else if(action==='visibility') {
          await api('/api/library/visibility?project='+encodeURIComponent(item.name),{method:'POST',body:JSON.stringify({hidden:!item.hidden})});
          item.hidden=!item.hidden;
          state.hiddenProjects=items.filter(entry=>entry.hidden).map(entry=>entry.name);
          renderProjectPicker();
          toast(item.hidden?'Đã ẩn khỏi danh sách chọn. Dữ liệu truyện vẫn được giữ.':'Đã hiện lại trong danh sách chọn.');
        } else if(action==='folder') {
          await api('/api/library/open-folder?project='+encodeURIComponent(item.name),{method:'POST',body:'{}'});
          toast('Đã mở thư mục truyện.');
        }
      } catch(error) {toast(error.message);}
      finally {
        busy.delete(item.name);render();
        const index=items.indexOf(item);
        const next=$(`#libraryItems [data-index="${index}"][data-library-action="${action}"]`);
        if($('#libraryView').classList.contains('active'))(next||$('#libraryFilter')).focus();
      }
    };
  }
  return {bind,load};
}
