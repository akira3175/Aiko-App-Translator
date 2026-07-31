const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { projects: [], project: null, projectRevision: 0, chapters: [], reviews: [], context: {index:0,glossary:[],style_notes:'',raw_yaml:''}, characters: {content:'',count:0,exists:false,backup:false}, pronouns: {pairs:[],count:0,locked_count:0,raw_yaml:''}, pronounCurrent: null, characterDirty: false, reviewCurrent: null, currentImages: [], current: null, dirty: false, timer: null };
const editorViews = {};
let syncingEditors = false;
const punctuationStyles = [
  ['single-straight', "' '", "'", "'"],
  ['single-curly', '‘ ’', '‘', '’'],
  ['double-straight', '" "', '"', '"'],
  ['double-curly', '“ ”', '“', '”'],
  ['book-title', '《 》', '《', '》']
];
const findState = { source: { matches: [], index: -1 }, target: { matches: [], index: -1 } };
let selectionTranslationRequest=0;
let activeJobKind=null;
let settingsItems=[];
let activeSettingsGroup='gemini-api';
let geminiApiKeys=[];
let publishingBooks=[];
let manualPromptRequest=0;
let availableUpdate=null;
const settingsGroups={
  'gemini-api':['Gemini API','Model và thông số sinh nội dung khi dịch, hậu dịch và review qua API.'],
  'gemini-web':['Gemini Web','Gem, model và mức suy nghĩ khi tự động hóa trình duyệt Gemini.'],
  'chatgpt-web':['ChatGPT Web','Model và mức suy nghĩ khi tự động hóa trình duyệt ChatGPT.'],
  'gpt-api':['GPT API','Khóa, model và thông số cho quy trình dịch + hiệu đính bằng API.'],
  publishing:['Xuất bản','Tài khoản Hako và kho ảnh Cloudflare R2.'],
  general:['Chung','Hành vi chung của workspace và quy trình hậu xử lý.'],
};
const views = { workspace: ['BÀN DỊCH','Không gian dịch'], chapters: ['THƯ VIỆN','Kho chương'], pipeline: ['TỰ ĐỘNG HÓA','Quy trình AI'], terminology: ['BỘ NHỚ','Thuật ngữ'], characters: ['BỘ NHỚ','Hồ sơ nhân vật'], pronouns: ['BỘ NHỚ','Xưng hô'], help: ['TRỢ GIÚP','Hướng dẫn sử dụng'], settings: ['HỆ THỐNG','Cài đặt'] };

function initCodeEditors() {
  editorViews.source=CodeMirror.fromTextArea($('#sourceEditor'),{mode:'markdown',lineNumbers:true,lineWrapping:true,readOnly:true,viewportMargin:20});
  editorViews.target=CodeMirror.fromTextArea($('#targetEditor'),{mode:'markdown',lineNumbers:true,lineWrapping:true,viewportMargin:20,extraKeys:{'Ctrl-B':()=>applyFormat('bold'),'Cmd-B':()=>applyFormat('bold'),'Ctrl-I':()=>applyFormat('italic'),'Cmd-I':()=>applyFormat('italic')}});
  editorViews.target.on('change',view=>{
    $('#targetEditor').value=view.getValue();
    if(!syncingEditors)markTargetChanged();
  });
  editorViews.source.getWrapperElement().addEventListener('mouseup',translateRawSelection);
}

function editorValue(kind) { return editorViews[kind]?.getValue() ?? $(`#${kind}Editor`).value; }
function setEditorValue(kind,value) {
  const view=editorViews[kind];
  syncingEditors=true;
  if(view)view.setValue(value||'');
  $(`#${kind}Editor`).value=value||'';
  syncingEditors=false;
}
const pipelineGroups = {
  translation:{title:'Dịch thuật',description:'Các engine dịch chương và hậu xử lý bản dịch.'},
  memory:{title:'Bộ nhớ',description:'Tạo context, glossary và hồ sơ nhân vật cho truyện.'},
  quality:{title:'Kiểm tra chất lượng',description:'Review bản dịch và tổ chức kết quả kiểm tra.'},
  publishing:{title:'Xuất bản',description:'Đưa chương hoàn chỉnh lên nền tảng xuất bản.'},
};
let activePipelineGroup='translation';
const pipelineItems = [
  {id:'v1',code:'V1',group:'translation',title:'Gemini API',desc:'Dịch chương chưa xử lý bằng Gemini API.'},
  {id:'v2',code:'V2',group:'translation',title:'Gemini Web',desc:'Dịch đơn chương qua hồ sơ trình duyệt Gemini.'},
  {id:'v3',code:'V3',group:'translation',title:'Gemini Web Batch',desc:'Dịch nhiều chương mỗi batch và chạy hậu xử lý.'},
  {id:'gpt',code:'GPT',group:'translation',title:'ChatGPT Web',desc:'Dịch batch qua hồ sơ trình duyệt ChatGPT.'},
  {id:'gpt-api',code:'GA',group:'translation',title:'GPT API',desc:'Dịch và hiệu đính tuần tự trước khi lưu.'},
  {id:'manual',code:'MN',group:'translation',title:'Dịch thủ công',desc:'Xuất prompt và nhận kết quả AI trực tiếp.'},
  {id:'context-api',code:'CA',group:'memory',title:'Tạo context bằng Gemini API',desc:'Sinh glossary bằng API, không cần mở trình duyệt.'},
  {id:'context-v1',code:'C1',group:'memory',title:'Tạo context bằng Gemini Web',desc:'Sinh glossary qua hồ sơ trình duyệt Gemini.'},
  {id:'context-gpt',code:'CG',group:'memory',title:'Tạo context bằng ChatGPT Web',desc:'Sinh glossary qua hồ sơ trình duyệt ChatGPT.'},
  {id:'characters',code:'CH',group:'memory',title:'Hồ sơ nhân vật',desc:'Phân tích và cập nhật thông tin nhân vật.'},
  {id:'glossary',code:'GL',group:'memory',title:'Chèn thuật ngữ',desc:'Đồng bộ glossary vào dữ liệu truyện.'},
  {id:'review',code:'RV',group:'quality',title:'Review toàn bộ',desc:'Đối chiếu raw và bản dịch để tìm lỗi nội dung.'},
  {id:'split-review',code:'SP',group:'quality',title:'Tách review',desc:'Tách dữ liệu review theo khoảng chương.'},
  {id:'hako',code:'UP',group:'publishing',title:'Đăng lên Hako',desc:'Đăng chương Markdown và tải ảnh lên R2 khi cần.'},
];
const taskSchemas = {
  v1:{title:'Gemini API V1',description:'Chọn số lượng công việc thực hiện trong lần chạy này.',fields:[['run_until_complete','Chạy liên tục đến hết truyện','checkbox',false]]},
  review: {title:'Review đối chiếu toàn bộ',description:'So sánh từng chương raw Hàn với bản dịch Việt. Chọn phạm vi và mức song song trước khi gửi API.',fields:[['start','Bắt đầu từ chương','number','1'],['end','Kết thúc tại chương','number',''],['force','Review lại chương đã có','checkbox',false],['batch_size','Số chương mỗi batch','number','10'],['workers','Số luồng song song','number','10'],['sleep','Giây nghỉ giữa batch','number','4']]},
  'split-review': {title:'Tách review',description:'Để trống để xử lý toàn bộ file review.',fields:[['from','Từ chương','text',''],['to','Đến chương','text','']]},
  hako:{title:'Đăng chương lên Hako',description:'Chọn chương đầu và chương cuối. App tự xác định volume, Book ID và ảnh cần tải lên.',fields:[['set_as_incomplete','Đánh dấu chương chưa hoàn thành','checkbox',false]]},
  v2:{title:'Gemini Web V2',description:'Cấu hình browser và phạm vi chạy ngay tại đây.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true],['run_until_complete','Chạy liên tục đến hết truyện','checkbox',false]]},
  v3:{title:'Gemini Web V3',description:'Cấu hình browser, batch và phạm vi chạy.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true],['run_until_complete','Chạy liên tục đến hết truyện','checkbox',false],['batch_size','Số chương mỗi batch','number','2']]},
  gpt:{title:'ChatGPT Web',description:'Cấu hình browser, batch và phạm vi chạy.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập ChatGPT','checkbox',true],['run_until_complete','Chạy liên tục đến hết truyện','checkbox',false],['batch_size','Số chương mỗi batch','number','1']]},
  'gpt-api':{title:'GPT API · Dịch và hiệu đính',description:'Mỗi chương được dịch rồi hiệu đính bằng hai lượt GPT API trước khi lưu.',fields:[['run_until_complete','Chạy liên tục đến hết truyện','checkbox',false]]},
  characters:{title:'Tạo hồ sơ nhân vật',description:'Phân tích raw theo phạm vi. Chỉ tăng tiến độ khi AI trả về hồ sơ hợp lệ.',fields:[['character_model','Model Gemini','text','gemini-3.5-flash'],['character_batch_size','Số segment mỗi batch','number','10'],['character_start','Bắt đầu từ segment','number','1'],['character_end','Kết thúc tại segment (để trống = hết)','number',''],['character_retries','Số lần thử API','number','3'],['character_force','Chạy lại phạm vi đã xử lý','checkbox',false]]},
  manual:{title:'Dịch thủ công',description:'Sao chép prompt đầy đủ, gửi cho AI rồi dán kết quả để lưu và hậu xử lý.',fields:[]},
  'context-v1':{title:'Tạo context V1',description:'Chọn số chương xử lý trong mỗi batch và tùy chọn kiểm tra đăng nhập Gemini.',fields:[['batch_size','Số chương mỗi batch','number','30'],['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true]]},
  'context-api':{title:'Tạo context bằng Gemini API',description:'Tạo glossary theo từng batch bằng model context đã cấu hình. Không cần mở trình duyệt.',fields:[['batch_size','Số chương mỗi batch','number','30'],['context_retries','Số lần thử mỗi batch','number','3']]},
  'context-gpt':{title:'Tạo context GPT',description:'Chọn số chương xử lý trong mỗi batch và tùy chọn kiểm tra đăng nhập ChatGPT.',fields:[['batch_size','Số chương mỗi batch','number','30'],['open_browser_setup','Mở màn hình kiểm tra đăng nhập ChatGPT','checkbox',true]]},
};
let pendingTask=null;

async function api(path, options) {
  const canRetry=!options?.method||options.method==='GET';
  for(let attempt=0;attempt<(canRetry?2:1);attempt++){
    try {
      const response = await fetch(path, { cache:'no-store', headers: {'Content-Type':'application/json'}, ...options });
      const contentType=response.headers.get('content-type')||'';
      if(!contentType.includes('application/json')){
        throw new Error('Backend đang chạy phiên bản cũ. Hãy khởi động lại app rồi thử lại.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Có lỗi xảy ra');
      return data;
    } catch(error) {
      if(attempt===0&&canRetry&&error instanceof TypeError){
        await new Promise(resolve=>setTimeout(resolve,150));
        continue;
      }
      if(error instanceof TypeError)throw new Error('Không kết nối được server. Hãy chạy lại start_app.bat rồi thử lại.');
      throw error;
    }
  }
}

function renderPythonSettings(items) {
  settingsItems=items;
  $('#settingsTabs').innerHTML=Object.entries(settingsGroups).map(([key,[label]])=>`<button type="button" role="tab" data-settings-tab="${key}" aria-selected="${key===activeSettingsGroup}" class="${key===activeSettingsGroup?'active':''}">${label}<span>${items.filter(item=>item.group===key).length+(key==='general'||key==='publishing'?1:0)}</span></button>`).join('');
  const [title,description]=settingsGroups[activeSettingsGroup];
  $('#settingsGroupTitle').textContent=title; $('#settingsGroupDescription').textContent=description;
  $('#workspaceSettings').classList.toggle('active',activeSettingsGroup==='general');
  $('#geminiApiKeyManager').classList.toggle('active',activeSettingsGroup==='gemini-api');
  $('#publishingManager').classList.toggle('active',activeSettingsGroup==='publishing');
  const settingFields=items.filter(item=>item.group===activeSettingsGroup).map(item=>{
    const control=item.type==='select'
      ? `<select data-python-setting="${escapeHtml(item.key)}">${item.options.map(([value,label])=>`<option value="${escapeHtml(value)}" ${value===item.value?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>`
      : `<input data-python-setting="${escapeHtml(item.key)}" type="${item.type}" value="${escapeHtml(item.value)}" ${item.inputmode?`inputmode="${item.inputmode}"`:''} ${item.type==='number'?`min="${item.min}" max="${item.max}"`:''} autocomplete="off">`;
    return `<label class="python-setting"><span>${escapeHtml(item.label)}${item.overridden?'<em>Đã tùy chỉnh</em>':''}</span>${control}<small>${item.description?escapeHtml(item.description)+' · ':''}Mặc định: ${escapeHtml(item.default||'để trống')}</small></label>`;
  }).join('');
  $('#pythonSettingsFields').innerHTML=activeSettingsGroup==='publishing'&&settingFields
    ? `<details class="publishing-advanced"><summary>Cài đặt nâng cao: tài khoản Hako và kho ảnh</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
    : settingFields;
  $$('[data-settings-tab]').forEach(button=>button.onclick=()=>{
    $$('[data-python-setting]').forEach(input=>{ const item=settingsItems.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=input.value; });
    activeSettingsGroup=button.dataset.settingsTab;
    renderPythonSettings(settingsItems);
  });
}

function syncPublishingBookDraft() {
  publishingBooks=$$('[data-publishing-book]').map(row=>({
    book_id:row.querySelector('[data-book-id]').value,
    volume:row.querySelector('[data-book-volume]').value,
  }));
}

function renderPublishingBooks() {
  $('#publishingProjectLabel').textContent=state.project||'Chưa chọn truyện';
  $('#publishingBookList').innerHTML=publishingBooks.map((book,index)=>`<div class="publishing-book-row" data-publishing-book><span>${index+1}</span><label><small>Volume</small><input data-book-volume type="number" min="0" value="${escapeHtml(book.volume??'')}"></label><label><small>Book ID hoặc link tạo chương</small><input data-book-id value="${escapeHtml(book.book_id||'')}" placeholder="40699"></label><button type="button" data-remove-publishing-book aria-label="Xóa volume ${index+1}">Xóa</button></div>`).join('')||'<div class="publishing-book-empty">Chưa thiết lập nơi đăng. Hãy thêm volume đầu tiên.</div>';
  $$('[data-remove-publishing-book]').forEach((button,index)=>button.onclick=()=>{syncPublishingBookDraft();publishingBooks.splice(index,1);renderPublishingBooks();});
}

async function loadPublishingBooks() {
  if(!state.project){publishingBooks=[];renderPublishingBooks();return;}
  try {
    const data=await api('/api/publishing?project='+encodeURIComponent(state.project));
    publishingBooks=data.books||[];
    renderPublishingBooks();
  } catch(error) { publishingBooks=[];renderPublishingBooks();toast(error.message); }
}

async function savePublishingBooks() {
  if(!state.project)return toast('Hãy chọn truyện trước');
  syncPublishingBookDraft();
  const button=$('#savePublishingBooks');button.disabled=true;
  try {
    const data=await api('/api/publishing?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({books:publishingBooks})});
    publishingBooks=data.books||[];renderPublishingBooks();toast('Đã lưu book ID cho truyện');
  } catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

function renderGeminiApiKeys() {
  $('#geminiApiKeyCount').textContent=`${geminiApiKeys.length} key`;
  $('#geminiApiKeyList').innerHTML=geminiApiKeys.map((key,index)=>`<div class="api-key-row"><span>${index+1}</span><input type="password" value="${escapeHtml(key)}" data-gemini-api-key autocomplete="off" spellcheck="false" aria-label="Gemini API key ${index+1}"><button type="button" class="secondary" data-toggle-api-key>Hiện</button><button type="button" class="api-key-remove" data-remove-api-key aria-label="Xóa API key ${index+1}">Xóa</button></div>`).join('')||'<div class="api-key-empty">Chưa có API key. Hãy thêm key để sử dụng Gemini API.</div>';
  $$('[data-toggle-api-key]').forEach(button=>button.onclick=()=>{ const input=button.parentElement.querySelector('input'); const hidden=input.type==='password'; input.type=hidden?'text':'password'; button.textContent=hidden?'Ẩn':'Hiện'; });
  $$('[data-remove-api-key]').forEach((button,index)=>button.onclick=()=>{ syncGeminiApiKeyDraft(); geminiApiKeys.splice(index,1); renderGeminiApiKeys(); });
}

function syncGeminiApiKeyDraft() {
  geminiApiKeys=$$('[data-gemini-api-key]').map(input=>input.value);
}

async function loadGeminiApiKeys() {
  try { const data=await api('/api/gemini-api-keys'); geminiApiKeys=data.keys; renderGeminiApiKeys(); }
  catch(error) { toast(error.message); }
}

async function saveGeminiApiKeys() {
  syncGeminiApiKeyDraft();
  const button=$('#saveGeminiApiKeys'); button.disabled=true;
  try { const data=await api('/api/gemini-api-keys',{method:'POST',body:JSON.stringify({keys:geminiApiKeys})}); geminiApiKeys=data.keys; renderGeminiApiKeys(); toast(`Đã lưu ${data.count} Gemini API key`); }
  catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

async function loadPythonSettings() {
  try { renderPythonSettings((await api('/api/settings')).items); }
  catch(error) { toast(error.message); }
}

async function loadLanStatus() {
  try {
    const data=await api('/api/lan/status'), card=$('#lanAccessCard');
    card.classList.toggle('active',Boolean(data.configured));
    $('#lanAccessState').textContent=data.active?'Đang mở trong mạng LAN':data.configured?'Đã cấu hình · cần khởi động lại app':'Đang tắt';
    $('#lanAccessHint').textContent=data.active?'Điện thoại cùng Wi-Fi mở địa chỉ dưới đây, nhập PIN và cho phép mạng Private nếu Windows hỏi.':data.configured?'Đóng cửa sổ app rồi chạy lại start_app.bat để áp dụng.':'Bật “Truy cập từ điện thoại” bên dưới rồi lưu cấu hình.';
    $('#lanAccessUrl').textContent=data.url||'';
    $('#lanAccessPin').textContent=data.pin?`PIN: ${data.pin}`:'';
    $('#copyLanAccess').disabled=!data.url;
  } catch(error) { $('#lanAccessState').textContent='Không đọc được trạng thái LAN'; }
}

async function copyLanAccess() {
  const text=$('#lanAccessUrl').textContent;
  if(!text)return;
  try {
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
    else {
      const input=document.createElement('textarea');input.value=text;document.body.appendChild(input);input.select();document.execCommand('copy');input.remove();
    }
    toast('Đã sao chép địa chỉ mở trên điện thoại');
  } catch(error) { toast('Không thể sao chép địa chỉ'); }
}

function renderUpdateStatus(data) {
  availableUpdate=data.update_available&&data.download_ready?data:null;
  $('#updateVersion').textContent=`Phiên bản hiện tại ${data.current_version}`;
  const messages={
    ready:`Nguồn cập nhật: GitHub · ${data.repository}.`,
    no_release:'Repository chưa có bản phát hành. Hãy tạo release đầu tiên trên GitHub.',
    up_to_date:`Bạn đang dùng phiên bản mới nhất${data.latest_version?` (${data.latest_version})`:''}.`,
    update_available:`Có phiên bản ${data.latest_version}. ${data.download_ready?'Gói ZIP đã có checksum và sẵn sàng tải.':'Release còn thiếu ZIP Windows hoặc checksum.'}`,
  };
  $('#updateStatus').textContent=messages[data.status]||'Chưa kiểm tra bản mới.';
  $('#checkUpdate').textContent=availableUpdate?'Tải và cập nhật':'Kiểm tra cập nhật';
  $('#checkUpdate').classList.toggle('primary',Boolean(availableUpdate));
  $('#checkUpdate').classList.toggle('secondary',!availableUpdate);
}

async function loadUpdateStatus(check=false) {
  const button=$('#checkUpdate');
  if(check){button.disabled=true;button.textContent='Đang kiểm tra…';}
  try {
    const data=await api('/api/update'+(check?'?check=1':''));
    renderUpdateStatus(data);
    if(check)toast(data.update_available?`Có bản cập nhật ${data.latest_version}`:'Ứng dụng đã ở phiên bản mới nhất');
  } catch(error) {
    $('#updateStatus').textContent=error.message;
    if(check)toast(error.message);
  } finally {
    if(check){button.disabled=false;button.textContent='Kiểm tra cập nhật';}
  }
}

async function installUpdate() {
  if(state.dirty||state.characterDirty)return toast('Hãy lưu thay đổi đang soạn trước khi cập nhật');
  if(!confirm(`Tải và cập nhật lên phiên bản ${availableUpdate.latest_version}? App sẽ tự khởi động lại.`))return;
  const button=$('#checkUpdate');
  button.disabled=true;button.textContent='Đang tải bản cập nhật…';
  try {
    const result=await api('/api/update',{method:'POST',body:'{}'});
    $('#updateStatus').textContent=result.message;
    button.textContent='Đang khởi động lại…';
    toast(result.message);
  } catch(error) {
    button.disabled=false;button.textContent='Tải và cập nhật';
    $('#updateStatus').textContent=error.message;
    toast(error.message);
  }
}

async function savePythonSettings() {
  const button=$('#savePythonSettings'); button.disabled=true;
  const values=Object.fromEntries(settingsItems.map(item=>[item.key,item.value]));
  $$('[data-python-setting]').forEach(input=>values[input.dataset.pythonSetting]=input.value);
  try { renderPythonSettings((await api('/api/settings',{method:'POST',body:JSON.stringify({values})})).items); await Promise.all([loadUpdateStatus(),loadLanStatus()]); toast('Đã lưu cấu hình · thay đổi LAN cần khởi động lại app'); }
  catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

async function resetPythonSettings() {
  const button=$('#resetPythonSettings'); button.disabled=true;
  try { renderPythonSettings((await api('/api/settings',{method:'POST',body:JSON.stringify({reset:true})})).items); await loadLanStatus(); toast('Đã khôi phục toàn bộ giá trị mặc định'); }
  catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

async function loadChapters() {
  if (!state.project) return;
  const project=state.project, revision=state.projectRevision;
  try {
    const data = await api('/api/chapters?project=' + encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.chapters = data.items;
    $('#chapterBadge').textContent = data.total;
    renderChapterList(); renderPopover();
    updateChapterNavigation();
    if (!state.current && state.chapters.length) openChapter(state.chapters.find(x => !x.translated)?.name || state.chapters[0].name,project,revision);
  } catch (error) { if(state.project===project&&state.projectRevision===revision)toast(error.message); }
}

async function loadProjects() {
  try {
    const data = await api('/api/projects');
    state.projects = data.items;
    $('#projectItems').innerHTML = state.projects.length
      ? state.projects.map(name => `<button class="pop-item" data-project="${name}"><span>${name}</span></button>`).join('')
      : '<div class="empty-state"><p>Chưa tìm thấy truyện.</p></div>';
    const remembered = localStorage.getItem('novel-project');
    const first = state.projects.includes(remembered) ? remembered : state.projects[0];
    if (first) await selectProject(first); else toast('Chưa có truyện nào trong thư mục truyen');
  } catch (error) { toast(error.message); }
}

async function selectProject(name) {
  if (state.dirty) await saveChapter();
  if (state.characterDirty) {
    await saveCharacters();
    if (state.characterDirty) return;
  }
  state.projectRevision+=1;
  state.project = name; state.current = null; state.chapters = [];
  localStorage.setItem('novel-project', name);
  $('#currentProject').textContent = name; $('#activeProjectLabel').textContent = name;
  $('#currentChapter').textContent = 'Chọn một chương';
  updateChapterNavigation();
  setEditorValue('source',''); setEditorValue('target','');
  updateLineNumbers('source'); updateLineNumbers('target');
  state.reviews=[]; state.context={index:0,glossary:[],style_notes:'',raw_yaml:''};
  renderContext();
  state.currentImages=[]; renderMarkdownEditors();
  $('#projectPopover').classList.remove('open');
  await Promise.all([loadChapters(), loadReviews(), loadContext(), loadCharacters(), loadPronouns(), loadPublishingBooks()]); toast('Đã mở ' + name);
}

async function loadContext() {
  if (!state.project) return;
  const project=state.project, revision=state.projectRevision;
  try {
    const context=await api('/api/context?project='+encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.context=context;
  } catch(error) {
    if(state.project!==project||state.projectRevision!==revision)return;
    state.context={index:0,glossary:[],style_notes:'',raw_yaml:''}; toast(error.message);
  }
  renderContext($('#glossarySearch')?.value||'');
}

async function loadCharacters() {
  if(!state.project)return;
  const project=state.project, revision=state.projectRevision;
  try {
    const data=await api('/api/characters?project='+encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.characters=data; state.characterDirty=false;
    $('#characterEditor').value=data.content||'';
    renderCharacters();
  } catch(error) { if(state.project===project&&state.projectRevision===revision)toast(error.message); }
}

function renderCharacters() {
  const content=$('#characterEditor').value, count=(content.match(/^##\s+.+$/gm)||[]).length;
  $('#characterBadge').textContent=count;
  $('#characterSummary').textContent=state.project?`${state.project} · ${count} nhân vật`:'Chưa chọn truyện.';
  $('#characterSaveState').textContent=state.characterDirty?'Chưa lưu':(!state.characters.exists?'Chưa có dữ liệu':state.characters.backup?'Đã lưu · Có backup':'Đã lưu');
  $('#characterPreview').innerHTML=markdownToHtml(content,[]);
  $('#characterEmpty').classList.toggle('open',!content.trim()&&!state.characterDirty);
}

async function loadPronouns() {
  if(!state.project)return;
  const project=state.project, revision=state.projectRevision;
  try {
    const data=await api('/api/pronouns?project='+encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.pronouns=data;
    if(!data.pairs.some(pair=>pair.key===state.pronounCurrent))state.pronounCurrent=data.pairs[0]?.key||null;
    renderPronouns();
  } catch(error) {
    if(state.project!==project||state.projectRevision!==revision)return;
    state.pronouns={pairs:[],count:0,locked_count:0,raw_yaml:''};state.pronounCurrent=null;renderPronouns();toast(error.message);
  }
}

function pronounPairLabel(pair) {
  const latest=pair.latest||{};
  return latest.speaker&&latest.listener?`${latest.speaker} → ${latest.listener}`:(pair.characters||[]).join(' ↔ ');
}

function renderPronouns() {
  const data=state.pronouns||{pairs:[],count:0,locked_count:0,raw_yaml:''};
  const query=($('#pronounSearch')?.value||'').trim().toLocaleLowerCase('vi');
  const filter=$('#pronounFilter')?.value||'all';
  const pairs=data.pairs.filter(pair=>{
    const haystack=`${(pair.characters||[]).join(' ')} ${pronounPairLabel(pair)}`.toLocaleLowerCase('vi');
    return (!query||haystack.includes(query))&&(filter==='all'||(filter==='locked'&&pair.locked)||(filter==='conflict'&&pair.changed));
  });
  $('#pronounBadge').textContent=data.count||0;
  $('#pronounSummary').textContent=state.project?`${state.project} · ${data.count||0} cặp · ${data.locked_count||0} đã khóa`:'Chưa chọn truyện.';
  $('#pronounCount').textContent=`${pairs.length}/${data.count||0} cặp`;
  $('#pronounRawYaml').textContent=data.raw_yaml||'# Chưa có dữ liệu xưng hô.';
  $('#pronounList').innerHTML=pairs.length?pairs.map((pair,index)=>{
    const latest=pair.latest||{};
    return `<button class="pronoun-row ${pair.key===state.pronounCurrent?'active':''}" data-pronoun-key="${escapeHtml(pair.key)}"><span><strong>${escapeHtml(pronounPairLabel(pair))}</strong><small>${escapeHtml(latest.speaker_self||'?')} / ${escapeHtml(latest.speaker_to_listener||'?')} · Chương ${escapeHtml(latest.chapter_number??'—')}</small></span><span class="pronoun-row-meta">${pair.changed?'<i class="pronoun-chip">Đã đổi</i>':''}${pair.locked?'<i class="pronoun-chip locked">Đã khóa</i>':''}</span></button>`;
  }).join(''):'<div class="pronoun-list-empty">Không có cặp xưng hô phù hợp.</div>';
  renderPronounDetail();
}

function renderPronounDetail() {
  const pair=(state.pronouns.pairs||[]).find(item=>item.key===state.pronounCurrent);
  if(!pair){$('#pronounDetail').innerHTML='<div class="pronoun-empty"><strong>Chưa có dữ liệu xưng hô</strong><span>Dữ liệu sẽ xuất hiện sau khi một chương chạy hậu xử lý.</span></div>';return;}
  const latest=pair.latest||{}, history=[...(pair.timeline||[])].reverse();
  $('#pronounDetail').innerHTML=`<div class="pronoun-detail-head"><div><span class="eyebrow">${pair.locked?'QUY TẮC ĐÃ KHÓA':'AI GHI NHẬN'}</span><h3>${escapeHtml(pronounPairLabel(pair))}</h3><p>Cập nhật gần nhất tại chương ${escapeHtml(latest.chapter_number??'—')}</p></div><div class="pronoun-detail-actions"><button class="secondary" id="editPronounPair">Chỉnh sửa</button><button class="secondary pronoun-delete" id="deletePronounPair">Xóa cặp</button></div></div><div class="pronoun-current"><div><span>Tự xưng</span><strong>${escapeHtml(latest.speaker_self||'Chưa rõ')}</strong></div><div><span>Gọi đối phương</span><strong>${escapeHtml(latest.speaker_to_listener||'Chưa rõ')}</strong></div></div><div class="pronoun-context-card"><span>NGỮ CẢNH QUAN HỆ</span><p>${escapeHtml(latest.relationship_status||'Chưa có mô tả quan hệ.')}</p><small>${escapeHtml(latest.emotional_tone||'Chưa ghi nhận giọng điệu.')}</small></div><h4 class="pronoun-history-title">Lịch sử theo chương</h4><div class="pronoun-history">${history.map(item=>`<div class="pronoun-history-item"><b>Chương ${escapeHtml(item.chapter_number??'—')}</b><div><p><strong>${escapeHtml(item.speaker||'?')}</strong> tự xưng “${escapeHtml(item.speaker_self||'?')}”, gọi <strong>${escapeHtml(item.listener||'?')}</strong> là “${escapeHtml(item.speaker_to_listener||'?')}”</p><small>${escapeHtml(item.relationship_status||item.emotional_tone||'Không có ghi chú')}</small></div></div>`).join('')}</div>`;
  $('#editPronounPair').onclick=openPronounEditor;
  $('#deletePronounPair').onclick=deletePronounPair;
}

function openPronounEditor() {
  const pair=(state.pronouns.pairs||[]).find(item=>item.key===state.pronounCurrent);
  if(!pair)return;
  const latest=pair.latest||{};
  $('#pronounModalTitle').textContent=pronounPairLabel(pair);
  $('#pronounSpeaker').value=latest.speaker||'';
  $('#pronounListener').value=latest.listener||'';
  $('#pronounSelf').value=latest.speaker_self||'';
  $('#pronounToListener').value=latest.speaker_to_listener||'';
  $('#pronounRelationship').value=latest.relationship_status||'';
  $('#pronounTone').value=latest.emotional_tone||'';
  $('#pronounLocked').checked=Boolean(pair.locked);
  $('#pronounModal').classList.add('open');
}

async function savePronounEdit() {
  if(!state.pronounCurrent)return;
  const button=$('#savePronounEdit');button.disabled=true;button.textContent='Đang lưu…';
  try {
    state.pronouns=await api('/api/pronouns?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({key:state.pronounCurrent,speaker_self:$('#pronounSelf').value,speaker_to_listener:$('#pronounToListener').value,relationship_status:$('#pronounRelationship').value,emotional_tone:$('#pronounTone').value,locked:$('#pronounLocked').checked})});
    $('#pronounModal').classList.remove('open');renderPronouns();toast('Đã lưu quy tắc xưng hô · Có bản sao .bak');
  } catch(error){toast(error.message);}
  finally{button.disabled=false;button.textContent='Lưu quy tắc';}
}

async function deletePronounPair() {
  const pair=(state.pronouns.pairs||[]).find(item=>item.key===state.pronounCurrent);
  if(!pair||!confirm(`Xóa toàn bộ lịch sử “${pronounPairLabel(pair)}”?`))return;
  try {
    state.pronouns=await api('/api/pronouns?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({action:'delete',key:pair.key})});
    state.pronounCurrent=state.pronouns.pairs[0]?.key||null;renderPronouns();toast('Đã xóa cặp xưng hô · Có thể khôi phục từ .bak');
  } catch(error){toast(error.message);}
}

function setCharacterMode(mode) {
  const preview=mode==='preview';
  if(preview)renderCharacters();
  $('#characterEditor').classList.toggle('editor-hidden',preview);
  $('#characterPreview').classList.toggle('editor-hidden',!preview);
  $$('[data-character-mode]').forEach(button=>button.classList.toggle('active',button.dataset.characterMode===mode));
}

async function saveCharacters() {
  if(!requireProject())return;
  const button=$('#saveCharacters'); button.disabled=true; button.textContent='Đang lưu…';
  try {
    state.characters=await api('/api/characters?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({content:$('#characterEditor').value})});
    state.characterDirty=false; renderCharacters(); toast(state.characters.backup?'Đã lưu hồ sơ · Có bản sao .bak':'Đã lưu hồ sơ');
  } catch(error) { toast(error.message); }
  finally { button.disabled=false; button.textContent='Lưu hồ sơ'; }
}

function renderContext(filter='') {
  const context=state.context||{index:0,glossary:[],style_notes:''};
  const query=filter.trim().toLowerCase();
  const items=(context.glossary||[]).filter(item=>!query||item.source.toLowerCase().includes(query)||item.target.toLowerCase().includes(query));
  $('#contextSummary').textContent=state.project?`${state.project} · context đến chương ${context.index||0}`:'Chưa chọn truyện.';
  $('#glossaryCount').textContent=`${items.length}/${(context.glossary||[]).length} thuật ngữ`;
  $('#glossaryList').innerHTML=items.length?items.map(item=>`<div class="glossary-row"><span>${escapeHtml(item.source)}</span><i>→</i><span>${escapeHtml(item.target)}</span></div>`).join(''):'<div class="memory-empty">Không có thuật ngữ phù hợp.</div>';
  $('#styleNotes').textContent=context.style_notes||'Chưa có style note cho truyện này.';
}

function requireProject() {
  if(state.project)return true;
  toast('Hãy chọn một truyện trước'); return false;
}

function openContextEditor() {
  if(!requireProject())return;
  $('#contextIndexEditor').value=state.context.index||0;
  $('#contextIndexEditor').max=state.chapters.length||0;
  $('#contextIndexHint').textContent=`Đã xử lý ${state.context.index||0}/${state.chapters.length||0} chương.`;
  $('#contextStyleEditor').value=state.context.style_notes||'';
  $('#contextGlossaryEditor').value=(state.context.glossary||[]).map(item=>`${item.source} = ${item.target}`).join('\n');
  setContextTab('writing');
  updateContextEditorStatus();
  $('#contextModal').classList.add('open');
}

function setContextTab(tab) {
  $$('[data-context-tab]').forEach(button=>button.classList.toggle('active',button.dataset.contextTab===tab));
  $$('[data-context-pane]').forEach(pane=>pane.classList.toggle('active',pane.dataset.contextPane===tab));
}

function updateContextEditorStatus() {
  const glossary=$('#contextGlossaryEditor').value.split(/\r?\n/).filter(line=>line.trim());
  const invalid=glossary.filter(line=>{const [source,...target]=line.split('=');return !source?.trim()||!target.join('=').trim();});
  $('#contextGlossaryCount').textContent=`${glossary.length} thuật ngữ`;
  $('#contextGlossaryTabCount').textContent=glossary.length;
  const status=$('#contextEditStatus');
  status.classList.toggle('invalid',invalid.length>0);
  status.querySelector('span').textContent=invalid.length?`${invalid.length} dòng glossary chưa hợp lệ`:'Sẵn sàng kiểm tra và lưu';
  status.querySelector('small').textContent=invalid.length?'Mỗi dòng cần có dạng Raw = Dịch.':'Bản cũ sẽ được sao lưu tự động trước khi thay thế.';
}

async function saveContextYaml() {
  const button=$('#saveContextEdit'); button.disabled=true; button.textContent='Đang lưu…';
  try {
    const nextIndex=Number($('#contextIndexEditor').value);
    if(nextIndex<(state.context.index||0)&&!confirm(`Bạn đang lùi tiến độ từ chương ${state.context.index||0} về ${nextIndex}. Tiếp tục?`))return;
    const context_fields={index:nextIndex,style_notes:$('#contextStyleEditor').value,glossary:$('#contextGlossaryEditor').value};
    state.context=await api('/api/context?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({context_fields})});
    renderContext($('#glossarySearch').value); $('#contextModal').classList.remove('open'); toast('Đã lưu an toàn · Có bản sao lưu .bak');
  } catch(error) { toast(error.message); }
  finally { button.disabled=false; button.textContent='Kiểm tra và lưu an toàn'; }
}

async function importGlossary() {
  const button=$('#confirmGlossaryImport'); button.disabled=true; button.textContent='Đang nạp…';
  try {
    const context=await api('/api/context?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({glossary_text:$('#glossaryImportText').value})});
    state.context=context; renderContext($('#glossarySearch').value); $('#glossaryModal').classList.remove('open');
    $('#glossaryImportText').value=''; toast(`Đã nạp ${context.imported||0} thuật ngữ`);
  } catch(error) { toast(error.message); }
  finally { button.disabled=false; button.textContent='Nạp glossary'; }
}

async function loadReviews(source='') {
  if (!state.project) return;
  const project=state.project, revision=state.projectRevision;
  try {
    const query = '?project='+encodeURIComponent(project)+(source?'&source='+encodeURIComponent(source):'');
    const data = await api('/api/reviews'+query);
    if(state.project!==project||state.projectRevision!==revision)return;
    state.reviews=data.items; state.reviewCurrent=null;
    $('#reviewBadge').textContent=data.items.length;
    $('#reviewSource').innerHTML=data.sources.map(x=>`<option value="${escapeHtml(x)}" ${x===data.source?'selected':''}>${escapeHtml(x)}</option>`).join('');
    renderWorkspaceReview();
  } catch(error) { if(state.project!==project||state.projectRevision!==revision)return; state.reviews=[]; $('#reviewBadge').textContent='0'; toast(error.message); }
}

function renderWorkspaceReview() {
  const chapterId=(state.current||'').replace(/\.md$/,'');
  const item=state.reviews.find(x=>x.chapter_id===chapterId);
  const currentChapter=state.chapters.find(chapter=>chapter.name===state.current);
  $('#reviewCurrentChapter').disabled=!currentChapter?.translated;
  $('#workspaceReviewTitle').textContent=state.current?prettyName(state.current):'Chưa chọn chương';
  if(!item){$('#workspaceReviewBody').innerHTML='<div class="empty-review"><strong>Chưa có review</strong><span>Chương này chưa có dữ liệu trong file đã chọn.</span></div>';return;}
  const issues=item.issues||[];
  $('#workspaceReviewBody').innerHTML=`<div class="review-detail-head"><div class="review-metrics"><span class="metric">Điểm <strong>${item.score??'—'}/10</strong></span><span class="metric"><strong>${item.issue_count??issues.length}</strong> lỗi</span></div></div><p class="review-copy">${escapeHtml(item.summary||'Không có tóm tắt.')}</p><div class="issues">${issues.length?issues.map((issue,index)=>`<section class="issue"><div class="issue-top"><span class="issue-type">Lỗi ${index+1} · ${escapeHtml(issue.type||'khác')}</span><span>${escapeHtml(issue.severity||'')}</span></div><dl><div><dt>NGUYÊN VĂN</dt><dd>${escapeHtml(issue.original_kr||issue.original||'—')}</dd></div><div><dt>BẢN DỊCH</dt><dd>${escapeHtml(issue.original_vi||issue.translation||'—')}</dd></div><div><dt>ĐỀ XUẤT</dt><dd class="suggestion">${escapeHtml(issue.suggestion||'—')}</dd></div></dl></section>`).join(''):'<div class="empty-review"><strong>Không phát hiện lỗi</strong><span>Chương này đã đạt yêu cầu.</span></div>'}</div>`;
}

async function reviewCurrentChapter() {
  const translatedChapters=state.chapters.filter(chapter=>chapter.translated);
  const targetIndex=translatedChapters.findIndex(
    chapter=>chapter.name===state.current
  );
  if(targetIndex<0)return toast('Chương này chưa có bản dịch để review');
  if(state.dirty){
    await saveChapter();
    if(state.dirty)return;
  }
  const target=targetIndex+1;
  await executePipeline('review',{
    start:target,
    end:target,
    force:true,
    batch_size:1,
    workers:1,
    sleep:0,
  });
}

function escapeHtml(value){return String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));}

function renderChapterList(filter='') {
  const query=filter.trim().toLocaleLowerCase('vi');
  const items = state.chapters.filter(item => !query||[item.title,item.id,item.name].some(value=>String(value||'').toLocaleLowerCase('vi').includes(query)));
  $('#chapterList').innerHTML = items.length ? items.map(item => `<div class="chapter-row" data-chapter="${escapeHtml(item.name)}"><span class="chapter-row-copy"><strong>${escapeHtml(item.title||item.id)}</strong><small>${escapeHtml(item.id)}</small></span><span class="words">${item.words.toLocaleString('vi-VN')} ${escapeHtml(item.word_unit||'từ')}</span><span class="status ${item.translated?'':'pending'}">${item.translated?'Đã dịch':'Chờ dịch'}</span><span class="chapter-action">Mở chương →</span></div>`).join('') : '<div class="empty-state"><p>Không tìm thấy chương phù hợp.</p></div>';
}

function renderPopover(filter='') {
  const query=filter.trim().toLocaleLowerCase('vi');
  const items = state.chapters.filter(item => !query||[item.title,item.id,item.name].some(value=>String(value||'').toLocaleLowerCase('vi').includes(query)));
  $('#popoverItems').innerHTML = items.length
    ? items.map(item => `<button class="pop-item chapter-option${item.name===state.current?' current':''}" data-chapter="${escapeHtml(item.name)}" ${item.name===state.current?'aria-current="true"':''}><span class="chapter-option-copy"><strong>${escapeHtml(item.title||item.id)}</strong><small>${escapeHtml(item.id)}</small></span><span class="chapter-option-status ${item.translated?'':'pending'}">${item.translated?'Đã dịch':'Chờ dịch'}</span></button>`).join('')
    : '<div class="chapter-option-empty">Không tìm thấy chương phù hợp.</div>';
}

function focusCurrentChapterInPopover() {
  const current=$('#popoverItems [aria-current="true"]');
  if(current){current.scrollIntoView({block:'center'});current.focus();}
  else $('#popoverSearch').focus();
}

function updateChapterNavigation() {
  const index=state.chapters.findIndex(item=>item.name===state.current);
  $('#previousChapter').disabled=index<=0;
  $('#nextChapter').disabled=index<0||index>=state.chapters.length-1;
}

function openAdjacentChapter(offset) {
  const index=state.chapters.findIndex(item=>item.name===state.current);
  const chapter=state.chapters[index+offset];
  if(chapter)openChapter(chapter.name);
}

async function openChapter(name,project=state.project,revision=state.projectRevision) {
  if (state.dirty) await saveChapter();
  try {
    const chapter = await api('/api/chapter/' + encodeURIComponent(name) + '?project=' + encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.current = name; state.dirty = false;
    const currentItem=state.chapters.find(item=>item.name===name);
    $('#currentChapter').textContent = currentItem?.title||prettyName(name);
    renderPopover(); updateChapterNavigation();
    setEditorValue('source',chapter.raw);
    setEditorValue('target',chapter.translated);
    state.currentImages=chapter.images||[]; renderMarkdownEditors();
    updateCounts(); updateLineNumbers('source'); updateLineNumbers('target'); refreshFind('source'); refreshFind('target'); setSaveState('Đã đồng bộ'); renderWorkspaceReview();
    $('#chapterPopover').classList.remove('open'); showView('workspace');
  } catch (error) { toast(error.message); }
}

function renderMarkdownEditors() {
  $('#sourcePreview').innerHTML=markdownToHtml(editorValue('source'),state.currentImages);
  $('#targetPreview').innerHTML=markdownToHtml(editorValue('target'),state.currentImages);
}

async function copyTargetPreview() {
  renderMarkdownEditors();
  const preview=$('#targetPreview'), text=[...preview.children].filter(element=>!element.classList.contains('paragraph-space')).map(element=>element.innerText).join('\n').trim();
  if(!text)return toast('Bản xem trước đang trống');
  const copy=preview.cloneNode(true);
  copy.querySelectorAll('[data-source-line]').forEach(element=>element.removeAttribute('data-source-line'));
  copy.querySelectorAll('.paragraph-space').forEach(element=>element.remove());
  copy.querySelectorAll('p,h1,h2,h3').forEach(element=>element.style.margin='0');
  const html=`<div>${copy.innerHTML}</div>`;
  try {
    if(window.ClipboardItem&&navigator.clipboard.write){
      await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([text],{type:'text/plain'})})]);
    } else {
      const temporary=document.createElement('div');temporary.contentEditable='true';temporary.style.cssText='position:fixed;left:-10000px;top:0';temporary.innerHTML=html;document.body.appendChild(temporary);
      const selection=getSelection(), range=document.createRange();range.selectNodeContents(temporary);selection.removeAllRanges();selection.addRange(range);
      if(!document.execCommand('copy'))throw new Error('copy failed');
      selection.removeAllRanges();temporary.remove();
    }
    toast('Đã sao chép kèm định dạng');
  }
  catch(error) { toast('Không thể sao chép vào clipboard'); }
}

function markdownToHtml(markdown,images) {
  let imageIndex=0;
  return String(markdown||'').split(/\r?\n/).map((line,lineIndex)=>{
    const trimmed=line.trim();
    const isImage=/^!\[[^\]]*\]\([^)]+\)$/.test(trimmed)||/^\[img(?:=[^\]]+)?\].+\[\/img\]$/i.test(trimmed);
    if(isImage){const image=images[imageIndex++];return image?`<div data-source-line="${lineIndex}"><a href="${escapeHtml(image.url)}" target="_blank" rel="noopener"><img class="inline-story-image" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.id)}" loading="lazy"></a><span class="image-caption">${escapeHtml(image.id)}</span></div>`:'';}
    if(!trimmed)return `<div class="paragraph-space" data-source-line="${lineIndex}"></div>`;
    if(trimmed==='* * *')return `<p data-source-line="${lineIndex}">${escapeHtml(line)}</p>`;
    let text=escapeHtml(line).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/(^|[^*])\*([^*]+?)\*/g,'$1<em>$2</em>');
    if(text.startsWith('### '))return `<h3 data-source-line="${lineIndex}">${text.slice(4)}</h3>`;
    if(text.startsWith('## '))return `<h2 data-source-line="${lineIndex}">${text.slice(3)}</h2>`;
    if(text.startsWith('# '))return `<h1 data-source-line="${lineIndex}">${text.slice(2)}</h1>`;
    return `<p data-source-line="${lineIndex}">${text}</p>`;
  }).join('');
}

function editTargetPreviewLine(event) {
  const previewLine=event.target.closest('[data-source-line]');
  if(!previewLine)return;
  event.preventDefault();
  const lineIndex=Number(previewLine.dataset.sourceLine), editor=editorViews.target;
  const lines=editorValue('target').split('\n');
  if(!Number.isInteger(lineIndex)||lineIndex<0||lineIndex>=lines.length)return;
  setEditorMode('target-text');
  requestAnimationFrame(()=>{
    editor.focus(); editor.setCursor({line:lineIndex,ch:0}); editor.scrollIntoView({line:lineIndex,ch:0},120);
  });
}

function setEditorMode(mode) {
  const source=mode.startsWith('source'), preview=mode.endsWith('preview');
  const editor=$(source?'#sourceEditorShell':'#targetEditorShell'), output=$(source?'#sourcePreview':'#targetPreview');
  if(preview)renderMarkdownEditors();
  editor.classList.toggle('editor-hidden',preview); output.classList.toggle('editor-hidden',!preview);
  $$(`[data-editor-mode^="${source?'source':'target'}-"]`).forEach(x=>x.classList.toggle('active',x.dataset.editorMode===mode));
  if(!preview)requestAnimationFrame(()=>updateLineNumbers(source?'source':'target'));
}

function updateLineNumbers(kind) {
  editorViews[kind]?.refresh();
}

function openFind(kind,replace=false) {
  if(kind==='source')setEditorMode('source-text');
  else setEditorMode('target-text');
  $(`#${kind}FindBar`).classList.add('open');
  const input=$(`#${kind}Find`);
  input.focus(); input.select();
  if(replace&&kind==='target')$('#targetReplace').focus();
}

function refreshFind(kind) {
  const editor=$(`#${kind}Editor`), query=$(`#${kind}Find`).value;
  const matches=[];
  if(query){
    const haystack=editorValue(kind).toLocaleLowerCase('vi'), needle=query.toLocaleLowerCase('vi');
    let position=0;
    while((position=haystack.indexOf(needle,position))!==-1){matches.push(position);position+=Math.max(needle.length,1);}
  }
  findState[kind].matches=matches;
  if(!matches.length)findState[kind].index=-1;
  else if(findState[kind].index>=matches.length)findState[kind].index=0;
  updateFindCount(kind);
}

function updateFindCount(kind) {
  const current=findState[kind];
  $(`#${kind}FindCount`).textContent=current.matches.length?`${current.index+1}/${current.matches.length}`:'0/0';
}

function selectFind(kind,direction=1) {
  refreshFind(kind);
  const current=findState[kind];
  if(!current.matches.length)return;
  current.index=(current.index+direction+current.matches.length)%current.matches.length;
  const editor=editorViews[kind], start=current.matches[current.index], length=$(`#${kind}Find`).value.length;
  editor.setSelection(editor.posFromIndex(start),editor.posFromIndex(start+length));
  editor.focus(); editor.scrollIntoView(editor.posFromIndex(start),90); updateFindCount(kind);
}

function markTargetChanged() {
  state.dirty=true; updateCounts(); updateLineNumbers('target'); renderMarkdownEditors(); refreshFind('target'); setSaveState('Chưa lưu');
  clearTimeout(state.timer); if($('#autosave').checked)state.timer=setTimeout(saveChapter,1200);
}

function replaceCurrent(all=false) {
  const editor=editorViews.target, query=$('#targetFind').value, replacement=$('#targetReplace').value;
  if(!query)return;
  refreshFind('target');
  if(all){
    const escaped=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const matches=findState.target.matches.length;
    if(!matches)return;
    editor.setValue(editor.getValue().replace(new RegExp(escaped,'giu'),()=>replacement));
    toast(`Đã thay ${matches} kết quả`); return;
  }
  const current=findState.target;
  if(!current.matches.length)return;
  const start=current.matches[Math.max(current.index,0)];
  editor.replaceRange(replacement,editor.posFromIndex(start),editor.posFromIndex(start+query.length));
  selectFind('target',0);
}

function applyFormat(type) {
  const editor=editorViews.target;
  if($('#targetEditorShell').classList.contains('editor-hidden'))setEditorMode('target-text');
  const marker=type==='bold'?'**':'*', selected=editor.getSelection()|| (type==='bold'?'văn bản in đậm':'văn bản in nghiêng');
  editor.replaceSelection(marker+selected+marker,'end');
  editor.focus();
}

function initPunctuationOptions() {
  const options=punctuationStyles.map(([value,label])=>`<option value="${value}">${label}</option>`).join('');
  $('#punctuationFrom').innerHTML=options;
  $('#punctuationTo').innerHTML=options;
  $('#punctuationTo').value='single-curly';
}

function replaceDelimitedPairs(text, from, to) {
  let output='', position=0, count=0;
  while(position<text.length){
    const start=text.indexOf(from[2],position);
    if(start<0){output+=text.slice(position);break;}
    const contentStart=start+from[2].length;
    const end=text.indexOf(from[3],contentStart);
    if(end<0){output+=text.slice(position);break;}
    output+=text.slice(position,start)+to[2]+text.slice(contentStart,end)+to[3];
    position=end+from[3].length;
    count++;
  }
  return {text:output,count};
}

function convertPunctuation() {
  if(!state.current)return toast('Hãy chọn một chương trước');
  const from=punctuationStyles.find(item=>item[0]===$('#punctuationFrom').value);
  const to=punctuationStyles.find(item=>item[0]===$('#punctuationTo').value);
  if(from===to)return toast('Hai kiểu dấu đang giống nhau');
  const editor=editorViews.target, result=replaceDelimitedPairs(editor.getValue(),from,to);
  if(!result.count)return toast(`Không tìm thấy cặp ${from[1]}`);
  editor.setValue(result.text);
  toast(`Đã đổi ${result.count} cặp ${from[1]} thành ${to[1]}`);
}

async function createProject() {
  const name=$('#newProjectName').value.trim(), volume=$('#newProjectVolume').value, segmentLimit=Number($('#newProjectSegmentLimit').value), file=$('#newProjectFile').files[0], button=$('#confirmNewProject');
  if(!name)return toast('Hãy nhập tên truyện');
  if(name.length>60)return toast('Tên truyện quá dài; tối đa 60 ký tự');
  if(state.projects.some(project=>project.toLocaleLowerCase('vi')===name.toLocaleLowerCase('vi')))return toast(`Truyện “${name}” đã tồn tại`);
  if(!/^[\p{L}\p{N}_ .-]+$/u.test(name)||/[ .]$/.test(name))return toast('Tên truyện chứa ký tự không hợp lệ');
  if(/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name))return toast('Tên truyện trùng với tên hệ thống Windows');
  if(!file)return toast('Hãy chọn file EPUB hoặc TXT');
  const format=file.name.toLowerCase().endsWith('.epub')?'epub':file.name.toLowerCase().endsWith('.txt')?'txt':'';
  if(!format)return toast('File phải có định dạng EPUB hoặc TXT');
  if(!Number.isInteger(segmentLimit)||segmentLimit<500||segmentLimit>50000)return toast('Giới hạn segment phải từ 500 đến 50.000');
  button.disabled=true; button.textContent=`Đang tách ${format.toUpperCase()}…`;
  try {
    const query=new URLSearchParams({name,volume,format,segment_limit:String(segmentLimit)});
    const result=await api('/api/projects?'+query,{method:'POST',headers:{'Content-Type':format==='epub'?'application/epub+zip':'text/plain;charset=utf-8'},body:file});
    $('#newProjectModal').classList.remove('open');
    await loadProjects(); await selectProject(result.project);
    toast(`Đã tạo ${result.chapters} chương · ${result.segments} segment`);
  } catch(error){toast(error.message);} finally {button.disabled=false;button.textContent='Tạo và tách truyện';}
}

async function saveChapter() {
  if (!state.current) return toast('Hãy chọn một chương trước');
  setSaveState('Đang lưu…');
  try {
    await api('/api/chapter/' + encodeURIComponent(state.current) + '?project=' + encodeURIComponent(state.project), {method:'POST', body:JSON.stringify({translated:editorValue('target')})});
    state.dirty = false; setSaveState('Đã đồng bộ'); toast('Đã lưu bản dịch'); await loadChapters();
  } catch (error) { setSaveState('Lưu thất bại'); toast(error.message); }
}

function showView(name) {
  if(!views[name]||!$('#' + name + 'View'))return;
  $$('.view').forEach(x => x.classList.remove('active'));
  $$('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  $('#' + name + 'View').classList.add('active');
  $('#viewEyebrow').textContent = views[name][0]; $('#viewTitle').textContent = views[name][1];
  $('#saveButton').style.display = name === 'workspace' ? '' : 'none';
  $('#retranslateButton').style.display = name === 'workspace' ? '' : 'none';
  $('#sidebar').classList.remove('open');
}

function filterHelp(query='') {
  const normalized=String(query).trim().toLocaleLowerCase('vi');
  let visible=0;
  $$('[data-help-topic]').forEach(article=>{
    const content=`${article.dataset.helpSearch||''} ${article.textContent}`.toLocaleLowerCase('vi');
    const matches=!normalized||content.includes(normalized);
    article.hidden=!matches;
    visible+=matches?1:0;
  });
  $$('[data-help-topic-button]').forEach(button=>{
    const article=$(`#help-${button.dataset.helpTopicButton}`);
    button.hidden=Boolean(normalized)&&Boolean(article?.hidden);
  });
  $('#helpEmpty').classList.toggle('open',visible===0);
}

function openHelpTopic(key) {
  const target=$(`#help-${key}`);
  if(!target)return;
  $$('[data-help-topic-button]').forEach(button=>{
    const active=button.dataset.helpTopicButton===key;
    button.classList.toggle('active',active);
    button.setAttribute('aria-current',active?'true':'false');
  });
  target.scrollIntoView({block:'start'});
}

function handleHelpAction(action) {
  if(action==='add-project'){
    $('#newProjectModal').classList.add('open');
    requestAnimationFrame(()=>$('#newProjectName').focus());
    return;
  }
  if(action==='gemini-settings'||action==='publishing-settings'){
    activeSettingsGroup=action==='gemini-settings'?'gemini-api':'publishing';
    renderPythonSettings(settingsItems);
    showView('settings');
    return;
  }
  const group={translation:'translation',manual:'translation',quality:'quality',publishing:'publishing'}[action];
  if(!group)return;
  selectPipelineGroup(group);
  showView('pipeline');
  if(action==='manual')requestAnimationFrame(()=>document.querySelector('[data-run="manual"]')?.focus());
}

function updateCounts() {
  const source=countText(editorValue('source'));
  const target=countText(editorValue('target'));
  $('#sourceCount').textContent = `${source.count.toLocaleString('vi-VN')} ${source.unit}`;
  $('#targetCount').textContent = `${target.count.toLocaleString('vi-VN')} ${target.unit}`;
}
function countText(text) {
  const clean=String(text||'')
    .replace(/\[img\][\s\S]*?\[\/img\]/gi,' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g,' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g,'$1')
    .replace(/^[#>\-+*]+\s*/gm,' ')
    .replace(/[*_~`]+/g,' ');
  if(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(clean)){
    return {count:(clean.match(/[\p{L}\p{N}]/gu)||[]).length,unit:'ký tự'};
  }
  const locale=/\p{Script=Hangul}/u.test(clean)?'ko':'vi';
  if(Intl?.Segmenter){
    const segments=new Intl.Segmenter(locale,{granularity:'word'}).segment(clean);
    return {count:[...segments].filter(item=>item.isWordLike).length,unit:'từ'};
  }
  return {count:(clean.match(/[\p{L}\p{N}]+/gu)||[]).length,unit:'từ'};
}
function prettyName(name) { const m=name.match(/c(\d+)/i); return m ? `Chương ${Number(m[1])} · ${name}` : name; }
function setSaveState(text) { $('#saveState span').textContent = text; }
function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('show'); clearTimeout(el._timer); el._timer=setTimeout(()=>el.classList.remove('show'),2400); }

function closeSelectionTranslation() {
  selectionTranslationRequest++;
  $('#selectionTranslation').classList.remove('open');
}

async function translateRawSelection(event) {
  const fromEditor=event.currentTarget===editorViews.source?.getWrapperElement();
  const text=(fromEditor?editorViews.source.getSelection():String(getSelection()||'')).trim();
  if(!text)return closeSelectionTranslation();
  const popup=$('#selectionTranslation'), output=$('#selectionTranslationText'), requestId=++selectionTranslationRequest;
  output.textContent='Đang dịch…'; popup.classList.add('open');
  const width=popup.offsetWidth, provisionalLeft=Math.max(12,Math.min(event.clientX-width/2,innerWidth-width-12));
  popup.style.left=provisionalLeft+'px';
  popup.style.top=Math.max(12,event.clientY-popup.offsetHeight-12)+'px';
  try {
    const result=await api('/api/translate-selection',{method:'POST',body:JSON.stringify({text})});
    if(requestId!==selectionTranslationRequest)return;
    output.textContent=result.translated;
    const above=event.clientY-popup.offsetHeight-12;
    popup.style.top=(above>=12?above:Math.min(innerHeight-popup.offsetHeight-12,event.clientY+14))+'px';
  } catch(error) {
    if(requestId===selectionTranslationRequest)output.textContent='Không thể dịch: '+error.message;
  }
}

function positionPopover(popover, anchor) {
  if(!popover.classList.contains('open'))return;
  const box=anchor.getBoundingClientRect(), width=popover.offsetWidth||340, height=popover.offsetHeight||420, gap=7;
  const left=Math.max(12,Math.min(box.left,innerWidth-width-12));
  const below=box.bottom+gap, above=box.top-height-gap;
  const top=below+height<=innerHeight-12?below:Math.max(12,above);
  popover.style.left=left+'px'; popover.style.top=top+'px';
}

function togglePopover(popover, anchor) {
  const opening=!popover.classList.contains('open');
  $$('.popover.open').forEach(item=>item.classList.remove('open'));
  if(opening){popover.classList.add('open');positionPopover(popover,anchor);}
}

function repositionPopovers() {
  positionPopover($('#chapterPopover'),$('#chapterSelect'));
  positionPopover($('#projectPopover'),$('#projectSelect'));
}

function initPipeline() {
  $('#pipelineTotal').textContent=`${pipelineItems.length} tác vụ`;
  $('#pipelineTabs').innerHTML=Object.entries(pipelineGroups).map(([key,group])=>{
    const count=pipelineItems.filter(item=>item.group===key).length;
    return `<button type="button" data-pipeline-group="${key}" aria-current="${key===activePipelineGroup?'page':'false'}" class="${key===activePipelineGroup?'active':''}"><span>${group.title}</span><b>${count}</b></button>`;
  }).join('');
  renderPipelineGroup();
  $$('[data-pipeline-group]').forEach(button=>button.onclick=()=>selectPipelineGroup(button.dataset.pipelineGroup));
}
function selectPipelineGroup(key) {
  if(!pipelineGroups[key])return;
  activePipelineGroup=key;
  $$('[data-pipeline-group]').forEach(item=>{const active=item.dataset.pipelineGroup===key; item.classList.toggle('active',active); item.setAttribute('aria-current',active?'page':'false');});
  renderPipelineGroup();
}
function renderPipelineGroup() {
  const group=pipelineGroups[activePipelineGroup];
  const items=pipelineItems.filter(item=>item.group===activePipelineGroup);
  $('#pipelineGroupTitle').textContent=group.title;
  $('#pipelineGroupDescription').textContent=group.description;
  $('#pipelineGrid').innerHTML=items.map(item=>`<article class="pipeline-card"><div class="number" aria-hidden="true">${item.code}</div><div><h3>${item.title}</h3><p>${item.desc}</p></div><button class="secondary" data-run="${item.id}">Chạy tác vụ</button></article>`).join('');
}
function updateConsoleOutput(text) {
  const output=$('#consoleOutput');
  output.textContent=text;
  requestAnimationFrame(()=>{output.scrollTop=output.scrollHeight;});
}
function chapterTargetKey(name) {
  const match=String(name||'').match(/^v(\d+)_c(\d+)_s\d+\.md$/i);
  return match?`${String(Number(match[1])).padStart(6,'0')}:${String(Number(match[2])).padStart(9,'0')}`:'';
}
function parseChapterTarget(key) {
  const match=String(key||'').match(/^(\d{6}):(\d{9})$/);
  return match?{key,volume:Number(match[1]),chapter:Number(match[2])}:null;
}
function publishingChapterTargets() {
  const unique=new Map();
  state.chapters.filter(item=>item.translated).forEach(item=>{
    const key=chapterTargetKey(item.name);
    const parsed=parseChapterTarget(key);
    if(!parsed||unique.has(key))return;
    unique.set(key,{...parsed,label:`v${parsed.volume}_c${parsed.chapter} · ${item.title||item.id}`});
  });
  return [...unique.values()].sort((a,b)=>a.key.localeCompare(b.key));
}
async function copyPlainText(text) {
  try {
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
    else {
      const temporary=document.createElement('textarea');
      temporary.value=text;temporary.style.cssText='position:fixed;left:-10000px;top:0';
      document.body.appendChild(temporary);temporary.select();
      if(!document.execCommand('copy'))throw new Error('copy failed');
      temporary.remove();
    }
    toast('Đã sao chép prompt');
  } catch(error) { toast('Không thể sao chép vào clipboard'); }
}
async function configureTask(kind) {
  const promptRequest=++manualPromptRequest;
  const schema=taskSchemas[kind];
  if(!schema) return executePipeline(kind,{});
  pendingTask=kind; $('#taskModalTitle').textContent=schema.title; $('#taskModalDescription').textContent=schema.description;
  $('#confirmTask').textContent=kind==='manual'?'Lưu và hậu xử lý':'Chạy tác vụ';
  $('#confirmTask').disabled=false;
  if(kind==='manual'){
    if(!requireProject())return;
    const project=state.project;
    $('#taskFields').innerHTML='<div class="manual-prompt-loading"><strong>Đang tạo prompt đầy đủ…</strong><span>App đang chuẩn bị raw, context và các chương trước.</span></div>';
    $('#confirmTask').disabled=true;
    $('#taskModal').classList.add('open');
    try {
      const data=await api('/api/manual-prompt?project='+encodeURIComponent(project),{method:'POST',body:'{}'});
      if(promptRequest!==manualPromptRequest||state.project!==project)return;
      $('#taskModalTitle').textContent=`Dịch thủ công · ${data.title||data.chapter}`;
      $('#taskFields').innerHTML=`<input data-task-field="target_chapter" type="hidden" value="${escapeHtml(data.chapter)}"><section class="manual-prompt-step"><div><span>Bước 1 · Prompt cho ${escapeHtml(data.chapter)}</span><button class="secondary" id="copyManualPrompt" type="button">Sao chép prompt</button></div><textarea id="manualPromptText" readonly spellcheck="false">${escapeHtml(data.prompt)}</textarea></section><label class="task-field manual-result-step"><span>Bước 2 · Dán toàn bộ kết quả AI</span><textarea data-task-field="manual_result" rows="12" spellcheck="false" placeholder="###TITLE###&#10;Tiêu đề đã dịch&#10;&#10;###CONTENT###&#10;Nội dung đã dịch&#10;&#10;###END###"></textarea><small>Cần giữ các marker TITLE và CONTENT để app tách đúng tiêu đề, nội dung.</small></label>`;
      $('#copyManualPrompt').onclick=()=>copyPlainText(data.prompt);
      $('#confirmTask').disabled=false;
      $('[data-task-field="manual_result"]').focus();
    } catch(error) {
      if(promptRequest!==manualPromptRequest||state.project!==project)return;
      $('#taskFields').innerHTML=`<div class="manual-prompt-error"><strong>Không thể tạo prompt</strong><span>${escapeHtml(error.message)}</span></div>`;
      toast(error.message);
    }
    return;
  }
  let fields=(schema.fields||[]).map(([id,label,type,value])=>type==='checkbox'
    ? `<label class="task-check"><input data-task-field="${id}" type="checkbox" ${value?'checked':''}><span>${label}</span></label>`
    : `<label class="task-field"><span>${label}</span>${type==='textarea'?`<textarea data-task-field="${id}" rows="9">${escapeHtml(value)}</textarea>`:`<input data-task-field="${id}" type="${type}" value="${value}" ${type==='number'?'min="0"':''}>`}</label>`).join('');
  if(kind==='hako'){
    const targets=publishingChapterTargets();
    if(!targets.length)return toast('Truyện này chưa có chương đã dịch để đăng');
    const currentKey=chapterTargetKey(state.current?.name);
    const selected=targets.some(item=>item.key===currentKey)?currentKey:targets[0].key;
    const options=targets.map(item=>`<option value="${item.key}" ${item.key===selected?'selected':''}>${escapeHtml(item.label)}</option>`).join('');
    const volumes=[...new Set(targets.map(item=>item.volume))];
    const configured=new Set(publishingBooks.map(book=>Number(book.volume)));
    const missing=volumes.filter(volume=>!configured.has(volume));
    fields=`<div class="task-field-row publishing-range"><label class="task-field"><span>Chương bắt đầu</span><select data-task-field="start_target">${options}</select></label><label class="task-field"><span>Chương kết thúc</span><select data-task-field="end_target">${options}</select></label></div><div class="publishing-task-note ${missing.length?'warning':''}">${missing.length?`Chưa có Book ID cho volume ${missing.join(', ')}. Hãy thiết lập trong Cài đặt > Xuất bản.`:`Đã sẵn sàng cho ${publishingBooks.length} volume. Book ID sẽ được chọn tự động.`}</div>${fields}`;
  }
  $('#taskFields').innerHTML=fields;
  $('#taskModal').classList.add('open');
}

function confirmTask() {
  const config=Object.fromEntries($$('[data-task-field]').map(field=>[field.dataset.taskField,field.type==='checkbox'?field.checked:field.value]));
  if(pendingTask==='manual'){
    const result=String(config.manual_result||'').trim();
    if(!result)return toast('Hãy dán kết quả AI trước khi lưu');
    if(!result.includes('###TITLE###')||!result.includes('###CONTENT###'))return toast('Kết quả cần có marker ###TITLE### và ###CONTENT###');
  }
  if(pendingTask==='hako'){
    const start=parseChapterTarget(config.start_target);
    const end=parseChapterTarget(config.end_target);
    if(!start||!end)return toast('Phạm vi chương không hợp lệ');
    if(start.key>end.key)return toast('Chương kết thúc phải nằm sau chương bắt đầu');
    Object.assign(config,{from_vol:start.volume,from_chap:start.chapter,to_vol:end.volume,to_chap:end.chapter});
    delete config.start_target;delete config.end_target;
  }
  $('#taskModal').classList.remove('open'); executePipeline(pendingTask,config);
}

async function executePipeline(kind,config) {
  activeJobKind=kind;
  const pipelineItem=pipelineItems.find(item=>item.id===kind);
  if(pipelineItem)selectPipelineGroup(pipelineItem.group);
  const button = $(`[data-run="${kind}"]`); button.disabled=true; button.textContent='Đang chạy…'; $('#console').classList.add('open'); updateConsoleOutput('Đang khởi động tác vụ…');
  const translation=['v1','v2','v3','gpt','gpt-api','manual'].includes(kind);
  $('#stopAfterCurrent').style.display=translation?'':'none'; $('#stopImmediately').style.display=translation?'':'none'; $('#stopCurrentTask').style.display=translation?'none':'';
  if (!state.project) { button.disabled=false; button.textContent='Chạy tác vụ'; return toast('Hãy chọn truyện trước'); }
  showView('pipeline');
  try { await api('/api/run/'+kind+'?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({config:{skip_login_prompt:true,...config}})}); pollJob(kind,button); } catch(error){ button.disabled=false; button.textContent='Chạy lại'; toast(error.message); }
}
async function pollJob(kind, button) {
  try { const job=await api('/api/job/'+kind); updateConsoleOutput(job.output || 'Đang xử lý…'); if(job.status==='running') return setTimeout(()=>pollJob(kind,button),500); activeJobKind=null; button.disabled=false; button.textContent=job.status==='done'?'Chạy lại':'Thử lại'; toast(job.status==='done'?'Tác vụ đã hoàn tất':job.status==='cancelled'?'Đã dừng tác vụ':'Tác vụ gặp lỗi'); await loadChapters(); if(['review','split-review'].includes(kind))await loadReviews(); if(['context-api','context-v1','context-gpt','glossary'].includes(kind))await loadContext(); if(kind==='characters')await loadCharacters(); } catch(error){ button.disabled=false; toast(error.message); }
}

async function cancelCurrentTask() {
  if(!activeJobKind)return toast('Không có tác vụ đang chạy');
  const button=$('#stopCurrentTask'); button.disabled=true;
  try { await api('/api/job/cancel',{method:'POST',body:JSON.stringify({kind:activeJobKind})}); updateConsoleOutput('Đang dừng tác vụ…'); }
  catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

async function cancelTranslation(mode) {
  const after=mode==='after_current';
  const button=$(after?'#stopAfterCurrent':'#stopImmediately');
  button.disabled=true;
  try {
    await api('/api/translation/cancel',{method:'POST',body:JSON.stringify({mode})});
    if(!after)updateConsoleOutput('Đang hủy dịch ngay lập tức…');
    toast(after?'Sẽ dừng sau chương/batch hiện tại':'Đã gửi lệnh dừng ngay');
  } catch(error) { button.disabled=false; toast(error.message); }
}

async function startRetranslate() {
  if (!state.current) return toast('Hãy chọn một chương trước');
  if (state.dirty) await saveChapter();
  const engine = $('input[name="engine"]:checked').value;
  $('#retranslateModal').classList.remove('open');
  $('#console').classList.add('open');
  showView('pipeline');
  updateConsoleOutput(`Đang dịch lại ${state.current} bằng ${engine.toUpperCase()}…`);
  try {
    await api('/api/retranslate?project='+encodeURIComponent(state.project), {method:'POST', body:JSON.stringify({engine,chapter:state.current})});
    pollRetranslate();
  } catch(error) { toast(error.message); }
}

async function pollRetranslate() {
  try {
    const job=await api('/api/job/retranslate');
    updateConsoleOutput(job.output || 'Đang xử lý…');
    if(job.status==='running') return setTimeout(pollRetranslate,500);
    if(job.status==='done') { toast('Đã dịch lại chương'); await openChapter(state.current); }
    else toast('Dịch lại thất bại, bản cũ đã được khôi phục');
    await loadChapters();
  } catch(error) { toast(error.message); }
}

document.addEventListener('click', (event) => {
  const view=event.target.closest('[data-view]'); if(view) showView(view.dataset.view);
  const helpView=event.target.closest('[data-help-view]'); if(helpView) showView(helpView.dataset.helpView);
  const helpAction=event.target.closest('[data-help-action]'); if(helpAction) handleHelpAction(helpAction.dataset.helpAction);
  const chapter=event.target.closest('[data-chapter]'); if(chapter) openChapter(chapter.dataset.chapter);
  const project=event.target.closest('[data-project]'); if(project) selectProject(project.dataset.project);
  const run=event.target.closest('[data-run]'); if(run) configureTask(run.dataset.run);
  const pronoun=event.target.closest('[data-pronoun-key]'); if(pronoun){state.pronounCurrent=pronoun.dataset.pronounKey;renderPronouns();}
  if(!event.target.closest('.popover,#chapterSelect,#projectSelect'))$$('.popover.open').forEach(item=>item.classList.remove('open'));
});
$('#chapterSelect').onclick = () => { togglePopover($('#chapterPopover'),$('#chapterSelect')); if($('#chapterPopover').classList.contains('open'))requestAnimationFrame(focusCurrentChapterInPopover); };
$('#previousChapter').onclick=()=>openAdjacentChapter(-1);
$('#nextChapter').onclick=()=>openAdjacentChapter(1);
$('#projectSelect').onclick = () => togglePopover($('#projectPopover'),$('#projectSelect'));
$('#addProjectButton').onclick=()=>$('#newProjectModal').classList.add('open');
$('#cancelNewProject').onclick=()=>$('#newProjectModal').classList.remove('open');
$('#confirmNewProject').onclick=createProject;
$('#helpSearch').oninput=event=>filterHelp(event.target.value);
$$('[data-help-topic-button]').forEach(button=>button.onclick=()=>openHelpTopic(button.dataset.helpTopicButton));
$('#chapterSearch').oninput = e => renderChapterList(e.target.value);
$('#reviewSource').onchange=e=>loadReviews(e.target.value);
$('#reviewToggle').onclick=()=>$('#workspaceReview').classList.toggle('open');
$('#reviewCurrentChapter').onclick=reviewCurrentChapter;
$('#copyTargetPreview').onclick=copyTargetPreview;
$('#closeWorkspaceReview').onclick=()=>$('#workspaceReview').classList.remove('open');
$('#cancelTask').onclick=()=>{manualPromptRequest++;$('#taskModal').classList.remove('open');};
$('#confirmTask').onclick=confirmTask;
$('#popoverSearch').oninput = e => renderPopover(e.target.value);
$('#glossarySearch').oninput = e => renderContext(e.target.value);
$('#pronounSearch').oninput=renderPronouns;
$('#pronounFilter').onchange=renderPronouns;
$('#cancelPronounEdit').onclick=()=>$('#pronounModal').classList.remove('open');
$('#savePronounEdit').onclick=savePronounEdit;
$('#editContextButton').onclick=openContextEditor;
$('#cancelContextEdit').onclick=()=>$('#contextModal').classList.remove('open');
$('#saveContextEdit').onclick=saveContextYaml;
['contextIndexEditor','contextStyleEditor','contextGlossaryEditor'].forEach(id=>$(`#${id}`).oninput=updateContextEditorStatus);
$$('[data-context-tab]').forEach(button=>button.onclick=()=>setContextTab(button.dataset.contextTab));
$('#importGlossaryButton').onclick=()=>{if(requireProject()){$('#glossaryModal').classList.add('open');$('#glossaryImportText').focus();}};
$('#cancelGlossaryImport').onclick=()=>$('#glossaryModal').classList.remove('open');
$('#confirmGlossaryImport').onclick=importGlossary;
$('#punctuationToggle').onclick=event=>{
  event.stopPropagation();
  const popover=$('#punctuationPopover'), opening=!popover.classList.contains('open');
  popover.classList.toggle('open',opening);
  $('#punctuationToggle').setAttribute('aria-expanded',String(opening));
  if(opening)$('#punctuationFrom').focus();
};
$('#convertPunctuation').onclick=convertPunctuation;
$('#targetPreview').ondblclick=editTargetPreviewLine;
$('#sourcePreview').addEventListener('mouseup',translateRawSelection);
$('#closeSelectionTranslation').onclick=closeSelectionTranslation;
['source','target'].forEach(kind=>{
  $(`#${kind}Find`).addEventListener('input',()=>{findState[kind].index=-1;refreshFind(kind);});
  $(`#${kind}Find`).addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();selectFind(kind,event.shiftKey?-1:1);}if(event.key==='Escape')$(`#${kind}FindBar`).classList.remove('open');});
});
$('#targetReplace').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();replaceCurrent(false);}if(event.key==='Escape')$('#targetFindBar').classList.remove('open');});
$$('[data-find-panel]').forEach(button=>button.onclick=()=>openFind(button.dataset.findPanel));
$$('[data-find-action]').forEach(button=>button.onclick=()=>{
  const kind=button.dataset.findEditor, action=button.dataset.findAction;
  if(action==='next')selectFind(kind,1);
  if(action==='previous')selectFind(kind,-1);
  if(action==='close')$(`#${kind}FindBar`).classList.remove('open');
  if(action==='replace')replaceCurrent(false);
  if(action==='replace-all')replaceCurrent(true);
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape')closeSelectionTranslation();
  if(!(event.ctrlKey||event.metaKey))return;
  const key=event.key.toLowerCase();
  if(!['f','h'].includes(key))return;
  const kind=editorViews.source?.hasFocus()?'source':'target';
  event.preventDefault(); openFind(kind,key==='h');
});
document.addEventListener('click',event=>{
  if(event.target.closest('#punctuationPopover'))return;
  $('#punctuationPopover').classList.remove('open');
  $('#punctuationToggle').setAttribute('aria-expanded','false');
});
$('#saveButton').onclick=saveChapter;
$('#retranslateButton').onclick=()=>{if(!state.current)return toast('Hãy chọn một chương trước');$('#retranslateChapter').textContent=prettyName(state.current)+' · Bản cũ sẽ được giữ nếu dịch lỗi.';$('#retranslateModal').classList.add('open');};
$('#cancelRetranslate').onclick=()=>$('#retranslateModal').classList.remove('open');
$('#confirmRetranslate').onclick=startRetranslate;
$('#menuButton').onclick=()=>$('#sidebar').classList.toggle('open');
$('#focusButton').onclick=()=>{document.body.classList.toggle('focus'); $('#focusButton').textContent=document.body.classList.contains('focus')?'Thoát tập trung':'Chế độ tập trung';requestAnimationFrame(()=>{updateLineNumbers('source');updateLineNumbers('target');});};
function setWorkspaceMode(mode,remember=true){
  if(!['split','source','target'].includes(mode))mode='split';
  $$('[data-mode]').forEach(button=>button.classList.toggle('active',button.dataset.mode===mode));
  $('#editorGrid').className='editor-grid '+(mode==='split'?'':mode);
  if(remember&&window.matchMedia('(max-width:560px)').matches)localStorage.setItem('mobileWorkspaceMode',mode);
  requestAnimationFrame(()=>{editorViews.source?.refresh();editorViews.target?.refresh();updateLineNumbers('source');updateLineNumbers('target');});
}
$$('[data-mode]').forEach(button=>button.onclick=()=>setWorkspaceMode(button.dataset.mode));
$$('[data-editor-mode]').forEach(button=>button.onclick=()=>setEditorMode(button.dataset.editorMode));
$$('[data-format]').forEach(button=>button.onclick=()=>applyFormat(button.dataset.format));
$('#closeConsole').onclick=()=>$('#console').classList.remove('open');
$('#stopAfterCurrent').onclick=()=>cancelTranslation('after_current');
$('#stopImmediately').onclick=()=>cancelTranslation('immediate');
$('#stopCurrentTask').onclick=cancelCurrentTask;
$('#characterEditor').oninput=()=>{state.characterDirty=true;renderCharacters();};
$$('[data-character-mode]').forEach(button=>button.onclick=()=>setCharacterMode(button.dataset.characterMode));
$('#saveCharacters').onclick=saveCharacters;
$('#runCharacterAnalysis').onclick=()=>configureTask('characters');
$('#emptyRunCharacterAnalysis').onclick=()=>configureTask('characters');
$('#characterEmpty').onclick=event=>{if(event.target.closest('button'))return;state.characterDirty=true;renderCharacters();$('#characterEditor').focus();};
$('#savePythonSettings').onclick=savePythonSettings;
$('#resetPythonSettings').onclick=resetPythonSettings;
$('#copyLanAccess').onclick=copyLanAccess;
$('#checkUpdate').onclick=()=>availableUpdate?installUpdate():loadUpdateStatus(true);
$('#addGeminiApiKey').onclick=()=>{ syncGeminiApiKeyDraft(); geminiApiKeys.push(''); renderGeminiApiKeys(); const inputs=$$('[data-gemini-api-key]'); inputs[inputs.length-1]?.focus(); };
$('#saveGeminiApiKeys').onclick=saveGeminiApiKeys;
$('#addPublishingBook').onclick=()=>{syncPublishingBookDraft();const used=publishingBooks.map(book=>Number(book.volume)).filter(Number.isFinite);publishingBooks.push({book_id:'',volume:used.length?Math.max(...used)+1:1});renderPublishingBooks();};
$('#savePublishingBooks').onclick=savePublishingBooks;
window.addEventListener('beforeunload', e=>{if(state.dirty||state.characterDirty){e.preventDefault();e.returnValue='';}});
window.addEventListener('resize',()=>{repositionPopovers();updateLineNumbers('source');updateLineNumbers('target');});
window.addEventListener('scroll',repositionPopovers,true);
setEditorMode('source-text');
updateLineNumbers('source'); updateLineNumbers('target');
initCodeEditors();
setWorkspaceMode(window.matchMedia('(max-width:560px)').matches?(localStorage.getItem('mobileWorkspaceMode')||'target'):'split',false);
initPunctuationOptions(); initPipeline(); loadProjects(); loadPythonSettings(); loadGeminiApiKeys(); loadUpdateStatus(); loadLanStatus();
