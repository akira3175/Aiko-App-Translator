const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

export function createHakoEditFeature({api,escapeHtml,executePipeline,getProject,getTargets,toast}) {
  let remoteChapters=[];
  let mapping=[];

  function resetHakoEdit() {
    mapping=[];
    $('#confirmHakoMapping').checked=false;
    $('#runHakoEdit').disabled=true;
    const targets=getTargets();
    const options=targets.map((item,index)=>`<option value="${index}">${escapeHtml(item.label)}</option>`).join('');
    $('#hakoLocalFrom').innerHTML=options;
    $('#hakoLocalTo').innerHTML=options;
    if(targets.length)$('#hakoLocalTo').value=String(targets.length-1);
    $('#hakoRemoteFrom').innerHTML=remoteChapters.map((item,index)=>`<option value="${index}">${escapeHtml(item.title)}</option>`).join('');
    $('#hakoMapping').innerHTML='<div class="memory-empty">Chưa có bảng đối chiếu.</div>';
  }
  
  async function loadHakoChapterList() {
    const button=$('#loadHakoChapters'),url=$('#hakoPublicUrl').value.trim();
    if(!url)return toast('Hãy dán URL trang truyện Hako');
    button.disabled=true;$('#hakoScanStatus').textContent='Đang tải danh sách chương Hako…';
    try{
      const data=await api('/api/hako/chapters?url='+encodeURIComponent(url));
      remoteChapters=data.items||[];
      localStorage.setItem(`hako-public-url:${getProject()||''}`,data.url);
      resetHakoEdit();
      $('#hakoScanStatus').textContent=`Đã tải ${data.total} chương Hako. Chọn điểm bắt đầu tương ứng để đối chiếu.`;
    }catch(error){remoteChapters=[];resetHakoEdit();$('#hakoScanStatus').textContent=error.message;toast(error.message);}
    finally{button.disabled=false;}
  }
  
  function buildHakoEditMapping() {
    const local=getTargets();
    const from=Number($('#hakoLocalFrom').value),to=Number($('#hakoLocalTo').value),remoteFrom=Number($('#hakoRemoteFrom').value);
    if(!local.length||!remoteChapters.length)return toast('Hãy tải danh sách Hako trước');
    if(!Number.isInteger(from)||!Number.isInteger(to)||from>to)return toast('Range local không hợp lệ');
    if(to-from+1>50)return toast('Mỗi lượt chỉ cập nhật tối đa 50 chương');
    if(remoteFrom+to-from>=remoteChapters.length)return toast('Range Hako không đủ chương để ghép');
    mapping=local.slice(from,to+1).map((item,index)=>({local:item,remoteIndex:remoteFrom+index,selected:true}));
    renderHakoEditMapping();
  }
  
  function renderHakoEditMapping() {
    $('#confirmHakoMapping').checked=false;$('#runHakoEdit').disabled=true;
    $('#hakoMapping').innerHTML=mapping.length?`<table><thead><tr><th>Cập nhật</th><th>Chương local</th><th>Chương trên Hako</th><th>Trạng thái</th></tr></thead><tbody>${mapping.map((row,index)=>{
      const remote=remoteChapters[row.remoteIndex],match=normalizeTitle(row.local.title)===normalizeTitle(remote?.title);
      return `<tr class="${match?'matched':'warning'}"><td><input type="checkbox" data-hako-selected="${index}" ${row.selected?'checked':''}></td><td><strong>${escapeHtml(row.local.label)}</strong></td><td><select data-hako-remote="${index}">${remoteChapters.map((item,remoteIndex)=>`<option value="${remoteIndex}" ${remoteIndex===row.remoteIndex?'selected':''}>${escapeHtml(item.title)}</option>`).join('')}</select></td><td><span>${match?'Khớp tiêu đề':'Cần kiểm tra'}</span></td></tr>`;
    }).join('')}</tbody></table>`:'<div class="memory-empty">Chưa có bảng đối chiếu.</div>';
    $$('[data-hako-selected]').forEach(input=>input.onchange=()=>{mapping[Number(input.dataset.hakoSelected)].selected=input.checked;$('#confirmHakoMapping').checked=false;$('#runHakoEdit').disabled=true;});
    $$('[data-hako-remote]').forEach(select=>select.onchange=()=>{mapping[Number(select.dataset.hakoRemote)].remoteIndex=Number(select.value);renderHakoEditMapping();});
  }
  
  function normalizeTitle(value){return String(value||'').trim().replace(/\s+/g,' ').toLocaleLowerCase('vi');}
  
  async function runHakoEdit() {
    const chosen=mapping.filter(row=>row.selected);
    if(!chosen.length)return toast('Chưa chọn chương nào để cập nhật');
    const ids=chosen.map(row=>remoteChapters[row.remoteIndex]?.chapter_id);
    if(new Set(ids).size!==ids.length)return toast('Một chương Hako đang bị chọn nhiều lần');
    if(!$('#confirmHakoMapping').checked)return toast('Hãy xác nhận bảng đối chiếu');
    const targets=chosen.map(row=>({local_name:row.local.local_name,chapter_id:remoteChapters[row.remoteIndex].chapter_id,remote_title:remoteChapters[row.remoteIndex].title}));
    if(!confirm(`Sắp ghi đè tiêu đề và nội dung của ${targets.length} chương Hako. Tiếp tục?`))return;
    await executePipeline('hako-edit',{hako_edit_targets:targets});
  }
  
  function bind() {
    $('#loadHakoChapters').onclick=loadHakoChapterList;
    $('#buildHakoMapping').onclick=buildHakoEditMapping;
    $('#confirmHakoMapping').onchange=()=>{$('#runHakoEdit').disabled=!$('#confirmHakoMapping').checked||!mapping.some(row=>row.selected);};
    $('#runHakoEdit').onclick=runHakoEdit;
  }

  return {bind,reset:resetHakoEdit};
}
