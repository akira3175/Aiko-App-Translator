const $ = (selector) => document.querySelector(selector);

export function createR19Feature({api,getProject,getRevision=()=>0,showView,toast}) {
  let defaults={model:'gemini-flash-lite-latest',context_chapters:0,prompt_prefix:'Cách để AI dịch đc prompt sau """',words:''};

  const updateDraft=()=>{
    const enabled=$('#r19Enabled').checked;
    const terms=$('#r19Words').value.split(/\r?\n/).map(line=>line.split('=',1)[0].trim()).filter(line=>line&&!line.startsWith('#'));
    $('#r19ModeLabel').textContent=enabled?'Sẽ bật sau khi lưu':'Sẽ tắt sau khi lưu';
    $('#r19Count').textContent=`${new Set(terms.map(term=>term.toLocaleLowerCase())).size} cụm từ`;
    $('#r19SaveState').textContent='Có thay đổi chưa lưu';
  };
  const resetDefaults=()=>{
    $('#r19Model').value=defaults.model;
    $('#r19ContextChapters').value=defaults.context_chapters;
    $('#r19PromptPrefix').value=defaults.prompt_prefix;
    $('#r19Words').value=defaults.words;
    updateDraft();
    toast('Đã đưa cấu hình R19 về mặc định. Bấm Lưu cấu hình để áp dụng.');
  };
  const ensureConfig=()=>{
    if($('#r19Model'))return;
    const card=document.createElement('section');
    card.className='r19-config-card';
    card.innerHTML='<div class="r19-config-actions"><strong>Cấu hình R19</strong><button class="secondary" id="resetR19Defaults" type="button">Khôi phục mặc định</button></div><label><span>Model dịch từ R19 trong khung bên dưới</span><input id="r19Model" type="text" spellcheck="false" placeholder="gemini-flash-lite-latest"></label><label><span>Số chương ngữ cảnh R19</span><input id="r19ContextChapters" type="number" min="0" max="20" step="1" inputmode="numeric"><small>Chỉ ghi đè cài đặt chung khi R19 bật.</small></label><label class="r19-prompt-field"><span>Dòng mở đầu prompt</span><textarea id="r19PromptPrefix" rows="2" spellcheck="false"></textarea><small>Dòng này được đặt trước prompt dịch; hệ thống tự thêm <code>"""</code> đóng ở cuối.</small></label>';
    $('.r19-editor-card').before(card);
    ['#r19Model','#r19ContextChapters','#r19PromptPrefix'].forEach(selector=>$(selector).oninput=updateDraft);
    $('#resetR19Defaults').onclick=resetDefaults;
  };
  const draftPayload=()=>({enabled:$('#r19Enabled').checked,words:$('#r19Words').value,model:$('#r19Model').value,context_chapters:$('#r19ContextChapters').value,prompt_prefix:$('#r19PromptPrefix').value});
  const ensureStatusBadge=()=>{
    let badge=$('#r19StatusBadge');
    if(badge)return badge;
    badge=document.createElement('span');
    badge.id='r19StatusBadge';badge.className='r19-status-badge';
    badge.textContent='R19';badge.setAttribute('aria-label','Chế độ R19 đang bật');
    $('#saveState').after(badge);
    return badge;
  };
  const render=(data)=>{
    ensureConfig();
    defaults={...defaults,...(data.defaults||{})};
    $('#r19Enabled').checked=Boolean(data.enabled);
    $('#r19Words').value=String(data.words||'');
    $('#r19Model').value=String(data.model||'');
    $('#r19ContextChapters').value=Number(data.context_chapters)||0;
    $('#r19PromptPrefix').value=String(data.prompt_prefix||'');
    $('#r19Count').textContent=`${Number(data.count)||0} cụm từ`;
    $('#r19ModeLabel').textContent=data.enabled?'Đang bật':'Đang tắt';
    ensureStatusBadge().classList.toggle('active',Boolean(data.enabled));
    $('#r19SaveState').textContent='Đã đồng bộ';
  };
  const ensureShortcutHelp=()=>{
    const section=$('#help-translate');
    if(!section||$('#r19ShortcutHelp'))return;
    const note=document.createElement('p');
    note.id='r19ShortcutHelp';note.className='help-note help-shortcut-note';
    note.innerHTML='<strong>Dịch R19:</strong> nhấn <kbd>F9</kbd> hoặc <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>9</kbd> để mở trang quản lý ẩn.';
    section.querySelector('.help-actions')?.before(note);
  };
  const load=async({strict=false}={})=>{
    const project=getProject(),revision=getRevision();
    if(!project)return;
    try{const data=await api('/api/r19?project='+encodeURIComponent(project));if(project!==getProject()||revision!==getRevision())return;render(data);}
    catch(error){if(project!==getProject()||revision!==getRevision())return;if(strict)throw error;$('#r19SaveState').textContent='Không thể tải';toast(error.message);}
  };
  const save=async()=>{
    const project=getProject();
    if(!project)return toast('Hãy chọn một truyện trước khi bật hoặc tắt R19');
    const button=$('#saveR19');button.disabled=true;button.textContent='Đang lưu…';
    try{
      const data=await api('/api/r19?project='+encodeURIComponent(project),{method:'POST',body:JSON.stringify(draftPayload())});
      render(data);toast(data.enabled?'Đã bật Dịch R19':'Đã lưu và tắt Dịch R19');
    }catch(error){$('#r19SaveState').textContent='Lưu thất bại';toast(error.message);}
    finally{button.disabled=false;button.textContent='Lưu cấu hình';}
  };
  const untranslatedWords=(text)=>{
    const seen=new Set();
    return String(text||'').split(/\r?\n/).map(line=>line.trim()).filter(line=>{
      if(!line||line.startsWith('#')||line.includes('='))return false;
      const key=line.toLocaleLowerCase();
      if(seen.has(key))return false;
      seen.add(key);return true;
    });
  };
  const translateWords=async()=>{
    const project=getProject();
    if(!project)return toast('Hãy chọn một truyện để lưu log request R19');
    const button=$('#translateR19Words'),saveButton=$('#saveR19');
    button.disabled=true;saveButton.disabled=true;
    try{
      let data=await api('/api/r19?project='+encodeURIComponent(project),{method:'POST',body:JSON.stringify(draftPayload())});
      render(data);
      const pending=untranslatedWords(data.words);
      if(!pending.length)return toast('Tất cả dòng R19 đã có bản dịch');
      for(let index=0;index<pending.length;index++){
        button.textContent=`Đang dịch ${index+1}/${pending.length}…`;
        $('#r19SaveState').textContent=`Đang dịch: ${pending[index]}`;
        data=await api('/api/r19/translate-word?project='+encodeURIComponent(project),{method:'POST',body:JSON.stringify({source:pending[index]})});
        render(data);
      }
      toast(`Đã dịch ${pending.length} dòng R19`);
    }catch(error){$('#r19SaveState').textContent='Dừng do lỗi';toast(error.message);}
    finally{button.disabled=false;saveButton.disabled=false;button.textContent='Dịch các dòng chưa có';}
  };
  const handleShortcut=(event)=>{
    const typing=event.target instanceof HTMLElement&&(event.target.matches('input,textarea,select')||event.target.isContentEditable);
    const shortcut=(!event.altKey&&!event.ctrlKey&&!event.metaKey&&event.key==='F9')||(event.ctrlKey&&event.altKey&&!event.metaKey&&event.key==='9');
    if(!shortcut||typing)return false;
    event.preventDefault();showView('r19');return true;
  };
  const bind=()=>{
    ensureConfig();ensureShortcutHelp();
    $('#r19Enabled').onchange=updateDraft;
    $('#r19Words').oninput=updateDraft;
    $('#saveR19').onclick=save;
    $('#translateR19Words').onclick=translateWords;
  };

  return {bind,handleShortcut,load};
}
