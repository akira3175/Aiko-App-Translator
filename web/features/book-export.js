const $ = (selector) => document.querySelector(selector);

export function createBookExportFeature({escapeHtml,getChapters,getProject,toast}) {
  const scopedChapters=()=>{
    const chapters=getChapters(),scope=$('#bookExportScope').value;
    if(scope==='volume'){
      const volume=$('#bookExportVolume')?.value;
      return chapters.filter(item=>new RegExp(`^v${volume}_`,'i').test(item.name));
    }
    if(scope==='range'){
      const names=chapters.map(item=>item.name);
      let from=names.indexOf($('#bookExportFrom')?.value),to=names.indexOf($('#bookExportTo')?.value);
      if(from<0||to<0)return [];
      if(from>to)[from,to]=[to,from];
      return chapters.slice(from,to+1);
    }
    return chapters;
  };
  const updateSummary=()=>{
    const selected=scopedChapters(),source=$('#bookExportSource').value;
    const usable=source==='translated'?selected.filter(item=>item.translated):source==='raw'?selected.filter(item=>item.raw):selected;
    const skipped=selected.length-usable.length;
    $('#bookExportSummary').textContent=`Sẽ xuất ${usable.length.toLocaleString('vi-VN')} chương${skipped?` · Bỏ qua ${skipped} chương chưa có nội dung đã chọn`:''}.`;
    $('#confirmBookExport').disabled=!usable.length;
  };
  const renderScope=()=>{
    const chapters=getChapters(),scope=$('#bookExportScope').value;
    if(scope==='volume'){
      const volumes=[...new Set(chapters.map(item=>item.name.match(/^v(\d+)_/i)?.[1]).filter(Boolean))].sort((a,b)=>Number(a)-Number(b));
      $('#bookExportScopeFields').innerHTML=`<label><span>Volume</span><select id="bookExportVolume">${volumes.map(value=>`<option value="${value}">Volume ${value}</option>`).join('')}</select></label>`;
    }else if(scope==='range'){
      const options=chapters.map(item=>`<option value="${escapeHtml(item.name)}">${escapeHtml(item.title||item.id)}</option>`).join('');
      $('#bookExportScopeFields').innerHTML=`<div class="export-range-grid"><label><span>Từ chương</span><select id="bookExportFrom">${options}</select></label><label><span>Đến chương</span><select id="bookExportTo">${options}</select></label></div>`;
      if(chapters.length)$('#bookExportTo').value=chapters[chapters.length-1].name;
    }else $('#bookExportScopeFields').innerHTML='';
    updateSummary();
  };
  const close=()=>$('#bookExportModal').classList.remove('open');
  const open=()=>{
    const project=getProject(),chapters=getChapters();
    if(!project)return toast('Hãy chọn một truyện trước');
    if(!chapters.length)return toast('Truyện chưa có chương để xuất');
    $('#bookExportScope').value='all';$('#bookExportSource').value='translated';
    $('input[name="bookExportFormat"][value="epub"]').checked=true;
    renderScope();$('#bookExportModal').classList.add('open');
  };
  const exportBook=async()=>{
    const button=$('#confirmBookExport');button.disabled=true;button.textContent='Đang tạo file…';
    try{
      const scope=$('#bookExportScope').value;
      const payload={format:$('input[name="bookExportFormat"]:checked').value,source:$('#bookExportSource').value,scope};
      if(scope==='volume')payload.volume=$('#bookExportVolume').value;
      if(scope==='range'){payload.from=$('#bookExportFrom').value;payload.to=$('#bookExportTo').value;}
      const response=await fetch('/api/export-book?project='+encodeURIComponent(getProject()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'Không thể xuất truyện');}
      const blob=await response.blob(),disposition=response.headers.get('Content-Disposition')||'';
      const match=disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=match?decodeURIComponent(match[1]):`export.${payload.format==='markdown'?'md':payload.format}`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
      close();toast('Đã tạo file xuất truyện');
    }catch(error){toast(error.message);}
    finally{button.textContent='Xuất file';updateSummary();}
  };
  const bind=()=>{
    $('#exportBookButton').onclick=open;
    $('#closeBookExport').onclick=close;
    $('#cancelBookExport').onclick=close;
    $('#confirmBookExport').onclick=exportBook;
    $('#bookExportScope').onchange=renderScope;
    $('#bookExportSource').onchange=updateSummary;
    $('#bookExportScopeFields').onchange=updateSummary;
  };
  return {bind};
}
