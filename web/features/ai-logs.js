const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const stepLabels={translate:'Dịch',polish:'Hiệu đính',review:'Review',pronouns:'Xưng hô',r19_word:'Dịch R19',fix:'Sửa bản dịch'};

export function createAiLogFeature({api,copyPlainText,escapeHtml,getProject,toast}) {
  let items=[];
  let activeIndex=0;
  let activeTab='prompt';
  let refreshTimer=null;

  const label=(step)=>stepLabels[step]||String(step||'Tác vụ AI');
  const formatTime=(value)=>{
    const date=new Date(value);
    return Number.isNaN(date.getTime())?String(value||''):date.toLocaleString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'2-digit'});
  };
  const tabContent=(item,tab)=>{
    if(tab==='prompt')return item.prompt||'';
    if(tab==='response')return item.response||'';
    const attachment=(item.attachments||[])[Number(tab.replace('attachment-',''))];
    return attachment?.content||'';
  };
  const renderList=()=>{
    $('#aiLogCount').textContent=`${items.length} lượt gọi gần nhất`;
    $('#aiLogList').innerHTML=items.length?items.map((item,index)=>`<button class="ai-log-item ${index===activeIndex?'active':''}" type="button" data-ai-log-index="${index}"><span class="ai-log-item-top"><strong>${escapeHtml(label(item.step))}</strong><i class="ai-log-status ${item.ok?'ok':''}" title="${item.ok?'Thành công':'Có lỗi'}"></i></span><small>${escapeHtml(item.chapter_id||'Không rõ chương')} · ${escapeHtml(item.model||'Không rõ model')}</small><time>${escapeHtml(formatTime(item.ts))}</time></button>`).join(''):'<div class="ai-log-loading">Chưa có nhật ký API trong truyện này.</div>';
    $$('[data-ai-log-index]').forEach(button=>button.onclick=()=>{activeIndex=Number(button.dataset.aiLogIndex)||0;activeTab='prompt';renderList();renderDetail();});
  };
  const renderDetail=()=>{
    const item=items[activeIndex];
    if(!item){$('#aiLogDetail').innerHTML='<div class="ai-log-empty"><strong>Chưa có lượt gọi nào</strong><span>Prompt và phản hồi từ các tác vụ API sẽ xuất hiện tại đây.</span></div>';return;}
    const tabs=[['prompt','Prompt'],['response','Response'],...(item.attachments||[]).map((file,index)=>[`attachment-${index}`,file.name||`Tệp ${index+1}`])];
    $('#aiLogDetail').innerHTML=`<div class="ai-log-meta"><span>${escapeHtml(formatTime(item.ts))}</span><span>${escapeHtml(item.chapter_id||'Không rõ chương')}</span><span>${escapeHtml(item.model||'Không rõ model')}</span><span>${item.ok?'Thành công':'Có lỗi'}</span></div><div class="ai-log-tabs">${tabs.map(([key,name])=>`<button class="${key===activeTab?'active':''}" type="button" data-ai-log-tab="${escapeHtml(key)}">${escapeHtml(name)}</button>`).join('')}</div><button class="ai-log-copy" id="copyAiLog" type="button">Sao chép</button><pre class="ai-log-content" id="aiLogContent">${escapeHtml(tabContent(item,activeTab))}</pre>`;
    $$('[data-ai-log-tab]').forEach(button=>button.onclick=()=>{activeTab=button.dataset.aiLogTab;renderDetail();});
    $('#copyAiLog').onclick=()=>copyPlainText(tabContent(item,activeTab));
  };
  const load=async(silent=false)=>{
    const project=getProject();
    if(!project){items=[];renderList();renderDetail();return;}
    try{
      const data=await api(`/api/ai-logs?project=${encodeURIComponent(project)}&limit=200`);
      const selected=items[activeIndex];
      items=data.items||[];
      activeIndex=Math.max(0,selected?items.findIndex(item=>item.ts===selected.ts&&item.chapter_id===selected.chapter_id):0);
      renderList();renderDetail();
    }catch(error){if(!silent)toast(error.message);}
  };
  const open=()=>{
    $('#aiLogDrawer').classList.add('open');$('#aiLogScrim').classList.add('open');
    $('#aiLogDrawer').setAttribute('aria-hidden','false');$('#aiLogToggle').setAttribute('aria-expanded','true');
    load();clearInterval(refreshTimer);refreshTimer=setInterval(()=>load(true),3000);
  };
  const close=()=>{
    $('#aiLogDrawer').classList.remove('open');$('#aiLogScrim').classList.remove('open');
    $('#aiLogDrawer').setAttribute('aria-hidden','true');$('#aiLogToggle').setAttribute('aria-expanded','false');
    clearInterval(refreshTimer);refreshTimer=null;
  };
  const clear=async()=>{
    const project=getProject();
    if(!project||!confirm('Xóa toàn bộ nhật ký AI của truyện đang mở?'))return;
    try{await api(`/api/ai-logs/clear?project=${encodeURIComponent(project)}`,{method:'POST',body:'{}'});items=[];activeIndex=0;renderList();renderDetail();toast('Đã xóa nhật ký AI');}catch(error){toast(error.message);}
  };
  const download=()=>{
    if(!items.length)return toast('Chưa có nhật ký để tải');
    const blob=new Blob([JSON.stringify(items,null,2)],{type:'application/json;charset=utf-8'});
    const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`ai-logs-${getProject()||'project'}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);
  };
  const bind=()=>{
    $('#aiLogToggle').onclick=open;
    $('#closeAiLog').onclick=close;
    $('#aiLogScrim').onclick=close;
    $('#clearAiLogs').onclick=clear;
    $('#downloadAiLogs').onclick=download;
  };

  return {bind,close,load,open};
}
