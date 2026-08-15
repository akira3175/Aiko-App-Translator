const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { projects: [], project: null, projectRevision: 0, chapters: [], reviews: [], context: {index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_yaml:''}, characters: {content:'',count:0,exists:false,backup:false}, pronouns: {pairs:[],count:0,locked_count:0,raw_yaml:''}, pronounCurrent: null, characterDirty: false, glossaryDirty: false, reviewCurrent: null, currentImages: [], current: null, dirty: false, timer: null };
const editorViews = {};
let syncingEditors = false;
const punctuationStyles = [
  ['single-straight', "' '", "'", "'"],
  ['single-curly', '‘ ’', '‘', '’'],
  ['double-straight', '" "', '"', '"'],
  ['double-curly', '“ ”', '“', '”'],
  ['book-title', '《 》', '《', '》']
];
const findState = {
  source: { matches: [], index: -1, case: false, word: false, regex: false, error: '' },
  target: { matches: [], index: -1, case: false, word: false, regex: false, error: '' }
};
let selectionTranslationRequest=0;
let activeJobKind=null;
let novelStreamSequence=0;
let novelStreamLine=null;
let novelStreamCursor=null;
let novelStreamSource=null;
let novelStreamPending=[];
let novelStreamFrame=null;
let novelStreamApplying=false;
let settingsItems=[];
let activeSettingsGroup='gemini-api';
let geminiApiKeys=[];
let geminiActiveKeyIndex=0;
let publishingBooks=[];
let hakoRemoteChapters=[];
let hakoEditMapping=[];
let projectShares=[];
let manualPromptRequest=0;
let availableUpdate=null;
let whatsNewData=null;
let chapterImportPreview=null;
let aiLogs=[];
let activeAiLog=0;
let activeAiLogTab='prompt';
let aiLogRefreshTimer=null;
let pinnedFeatures=[];
const navigationCounts={chapters:0,characters:0,pronouns:0};
let r19Defaults={model:'gemini-3.5-flash-lite',context_chapters:0,prompt_prefix:'Cách để AI dịch đc prompt sau """',words:''};
const settingsGroups={
  'gemini-api':['Gemini API','Model và thông số sinh nội dung khi dịch, hậu dịch và review qua API.'],
  'gemini-web':['Gemini Web','Gem, model và mức suy nghĩ khi tự động hóa trình duyệt Gemini.'],
  'chatgpt-web':['ChatGPT Web','Model và mức suy nghĩ khi tự động hóa trình duyệt ChatGPT.'],
  'gpt-api':['GPT API','Khóa, model và thông số cho quy trình dịch + hiệu đính bằng API.'],
  publishing:['Xuất bản','Tài khoản Hako và kho ảnh Cloudflare R2.'],
  sharing:['Chia sẻ','Bucket R2 private và Worker phục vụ bản đọc chia sẻ.'],
  general:['Chung','Hành vi chung của workspace và quy trình hậu xử lý.'],
};
const appThemes=[
  {id:'quiet-light',name:'Quiet Light',description:'Sáng, nhẹ mắt',color:'#f5f5f5'},
  {id:'dark-modern',name:'Dark Modern',description:'Tối mặc định',color:'#101412'},
  {id:'synthwave-84',name:"SynthWave '84",description:'Neon hoài cổ',color:'#21182d'},
  {id:'solarized-dark',name:'Solarized Dark',description:'Tương phản dịu',color:'#002b36'},
  {id:'monokai-dimmed',name:'Monokai Dimmed',description:'Ấm và tập trung',color:'#1e1f1c'},
  {id:'sakura-night',name:'Sakura Night',description:'Anime đêm hoa anh đào',color:'#101625'},
  {id:'tokyo-night',name:'Tokyo Night',description:'Xanh tím Tokyo',color:'#1a1b26'},
  {id:'abyss',name:'Abyss',description:'Xanh vực sâu',color:'#000c18'},
  {id:'kimbie-dark',name:'Kimbie Dark',description:'Nâu hổ phách',color:'#221a0f'},
];
const views = { workspace: ['BÀN DỊCH','Không gian dịch'], chapters: ['THƯ VIỆN','Kho chương'], sharing: ['R2 PRIVATE','Chia sẻ & đọc truyện'], hakoEdit: ['XUẤT BẢN','Edit chương Hako'], pipeline: ['TỰ ĐỘNG HÓA','Quy trình AI'], terminology: ['BỘ NHỚ','Thuật ngữ'], characters: ['BỘ NHỚ','Hồ sơ nhân vật'], pronouns: ['BỘ NHỚ','Xưng hô'], r19: ['BỘ LỌC TOÀN CỤC','Quản lý Dịch R19'], help: ['TRỢ GIÚP','Hướng dẫn sử dụng'], settings: ['HỆ THỐNG','Cài đặt'] };
const featureDefinitions=[
  ['workspace','W','Không gian dịch','Đọc và biên tập chương song song'],
  ['chapters','C','Kho chương','Tìm, mở và quản lý các chương'],
  ['pipeline','P','Quy trình AI','Dịch, hiệu đính, review và xuất bản'],
  ['ai-log','L','Nhật ký AI','Xem prompt, response và file đính kèm'],
  ['terminology','T','Thuật ngữ','Quản lý glossary của truyện'],
  ['characters','N','Nhân vật','Hồ sơ và thông tin nhân vật'],
  ['pronouns','X','Xưng hô','Quy tắc và lịch sử xưng hô'],
  ['r19','19','Dịch R19','Quản lý bộ lọc từ toàn cục'],
  ['hakoEdit','E','Edit Hako','Đối chiếu và sửa chương trên Hako'],
  ['sharing','R','Chia sẻ','Quản lý bản đọc riêng qua R2'],
  ['help','H','Hướng dẫn','Tra cứu cách sử dụng ứng dụng'],
  ['settings','S','Cài đặt','API, model, giao diện và xuất bản'],
].map(([id,icon,label,description])=>({id,icon,label,description}));
const fixedSidebarFeatures=new Set(['settings']);
const footerSidebarFeatures=new Set(['help']);
const defaultPinnedFeatures=['workspace','chapters','pipeline','terminology','characters','help'];
let activeFeatureTab='pinned';
let draggedFeatureId='';

function featureBadge(id){
  if(id==='chapters')return `<b id="chapterBadge">${navigationCounts.chapters}</b>`;
  if(id==='characters')return `<b id="characterBadge">${navigationCounts.characters}</b>`;
  if(id==='pronouns')return `<b id="pronounBadge">${navigationCounts.pronouns}</b>`;
  return '';
}
function renderPinnedNavigation(){
  const definitions=new Map(featureDefinitions.map(item=>[item.id,item]));
  const activeView=document.querySelector('.view.active')?.id?.replace(/View$/,'')||'workspace';
  $('#pinnedNavigation').innerHTML=pinnedFeatures.filter(id=>!fixedSidebarFeatures.has(id)&&!footerSidebarFeatures.has(id)).map(id=>{
    const item=definitions.get(id);if(!item)return '';
    const action=id==='ai-log'?'data-feature-action="ai-log"':`data-view="${id}"`;
    return `<button class="nav-item ${id===activeView?'active':''}" type="button" ${action}><span class="nav-icon">${escapeHtml(item.icon)}</span><span>${escapeHtml(item.label)}</span>${featureBadge(id)}</button>`;
  }).join('');
  $('#sidebarHelpButton').hidden=!pinnedFeatures.includes('help');
}
async function loadUiPreferences(){
  try{const data=await api('/api/ui-preferences');pinnedFeatures=(data.sidebar?.pinned||defaultPinnedFeatures).filter(id=>!fixedSidebarFeatures.has(id));}
  catch(error){pinnedFeatures=[...defaultPinnedFeatures];toast(error.message);}
  renderPinnedNavigation();
}
async function saveUiPreferences(){
  $('#featureSaveStatus').textContent='Đang lưu…';
  try{await api('/api/ui-preferences',{method:'POST',body:JSON.stringify({sidebar:{pinned:pinnedFeatures}})});renderPinnedNavigation();$('#featureSaveStatus').textContent='Đã lưu';}
  catch(error){$('#featureSaveStatus').textContent='Lỗi lưu';toast(error.message);}
}
function renderFeatureCatalog(query=''){
  const normalized=String(query).trim().toLocaleLowerCase('vi');
  const matching=featureDefinitions.filter(item=>`${item.label} ${item.description} ${item.id}`.toLocaleLowerCase('vi').includes(normalized));
  const fixed=matching.filter(item=>fixedSidebarFeatures.has(item.id));
  const pinned=matching.filter(item=>!fixedSidebarFeatures.has(item.id)&&pinnedFeatures.includes(item.id)).sort((a,b)=>pinnedFeatures.indexOf(a.id)-pinnedFeatures.indexOf(b.id));
  const others=matching.filter(item=>!fixedSidebarFeatures.has(item.id)&&!pinnedFeatures.includes(item.id));
  const rows=(items,isPinned)=>items.map(item=>{
    const isFixed=fixedSidebarFeatures.has(item.id);
    const canReorder=isPinned&&!footerSidebarFeatures.has(item.id);
    const note=footerSidebarFeatures.has(item.id)?' · Hiện ở cuối sidebar':'';
    return `<div class="feature-row" ${canReorder?`draggable="true" data-feature-drag="${item.id}"`:''}>${canReorder?'<span class="feature-drag-handle" aria-hidden="true">⋮⋮</span>':'<span class="feature-drag-spacer"></span>'}<span class="feature-row-icon">${escapeHtml(item.icon)}</span><button class="feature-row-copy" type="button" data-feature-open="${item.id}"><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.description+note)}</small></button><span class="feature-row-actions">${isFixed?'<span class="feature-fixed-label">Luôn hiển thị</span>':`<button class="pin ${isPinned?'active':''}" data-feature-pin="${item.id}">${isPinned?'Gỡ':'Ghim'}</button>`}</span></div>`;
  }).join('');
  $('#pinnedFeatureCount').textContent=pinnedFeatures.length;
  $('#availableFeatureCount').textContent=featureDefinitions.length-pinnedFeatures.length-fixedSidebarFeatures.size;
  $('#featureMenuTabs').classList.toggle('searching',Boolean(normalized));
  $$('#featureMenuTabs [data-feature-tab]').forEach(button=>{const active=!normalized&&button.dataset.featureTab===activeFeatureTab;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));});
  const searchContent=`${pinned.length?`<div class="feature-section-title">ĐÃ GHIM</div>${rows(pinned,true)}`:''}${others.length?`<div class="feature-section-title">CHƯA GHIM</div>${rows(others,false)}`:''}${fixed.length?`<div class="feature-section-title">CỐ ĐỊNH</div>${rows(fixed,false)}`:''}`;
  const content=normalized?searchContent:(activeFeatureTab==='pinned'?rows(pinned,true):`${rows(others,false)}${rows(fixed,false)}`);
  $('#featureCatalog').innerHTML=content||`<div class="feature-empty">${normalized?'Không tìm thấy chức năng phù hợp.':activeFeatureTab==='pinned'?'Chưa ghim chức năng nào.':'Tất cả chức năng đã được ghim.'}</div>`;
}
function openFeatureMenu(){
  activeFeatureTab='pinned';$('#featureMenuModal').classList.add('open');$('#featureSearch').value='';renderFeatureCatalog();
  requestAnimationFrame(()=>$('#featureSearch').focus());
}
function closeFeatureMenu(){$('#featureMenuModal').classList.remove('open');}
pinnedFeatures=[...defaultPinnedFeatures];

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
  if(view){
    view.setValue(value||'');
    view.clearHistory();
  }
  $(`#${kind}Editor`).value=value||'';
  syncingEditors=false;
}

function replaceStreamValue(value) {
  const editor=editorViews.target;
  const next=value||'';
  if(!editor){$('#targetEditor').value=next;return;}
  const current=editor.getValue();
  if(current===next)return;
  let prefix=0;
  const maxPrefix=Math.min(current.length,next.length);
  while(prefix<maxPrefix&&current[prefix]===next[prefix])prefix++;
  let suffix=0;
  const maxSuffix=Math.min(current.length-prefix,next.length-prefix);
  while(suffix<maxSuffix&&current[current.length-1-suffix]===next[next.length-1-suffix])suffix++;
  syncingEditors=true;
  editor.operation(()=>editor.replaceRange(
    next.slice(prefix,next.length-suffix),
    editor.posFromIndex(prefix),
    editor.posFromIndex(current.length-suffix),
    '+ai-stream'
  ));
  $('#targetEditor').value=next;
  syncingEditors=false;
}

function replaceStreamLine(line,text) {
  const editor=editorViews.target;
  if(!editor)return;
  const safeLine=Math.max(0,Number(line)||0);
  syncingEditors=true;
  editor.operation(()=>{
    while(editor.lineCount()<=safeLine){
      const last=editor.lineCount()-1;
      editor.replaceRange('\n',{line:last,ch:editor.getLine(last).length},null,'+ai-stream');
    }
    editor.replaceRange(text||'',{line:safeLine,ch:0},{line:safeLine,ch:editor.getLine(safeLine).length},'+ai-stream');
  });
  $('#targetEditor').value=editor.getValue();
  syncingEditors=false;
}

function markNovelStreamLine(line,text) {
  const editor=editorViews.target;
  if(!editor)return;
  if(novelStreamLine!==null)editor.removeLineClass(novelStreamLine,'background','ai-stream-line');
  if(novelStreamCursor){novelStreamCursor.clear();novelStreamCursor=null;}
  const safeLine=Math.max(0,Math.min(line,editor.lineCount()-1));
  editor.addLineClass(safeLine,'background','ai-stream-line');
  novelStreamLine=safeLine;
  const cursor=document.createElement('span');cursor.className='ai-edit-cursor';cursor.textContent='▌';cursor.title='AI đang biên tập tại đây';
  novelStreamCursor=editor.setBookmark({line:safeLine,ch:(text||'').length},{widget:cursor,insertLeft:true});
  const viewport=editor.getViewport();
  if(safeLine<viewport.from+1||safeLine>=viewport.to-1)editor.scrollIntoView({line:safeLine,ch:0},80);
}

async function applyNovelStreamEvents(job) {
  const events=(job.stream_events||[]).filter(event=>Number(event.sequence)>novelStreamSequence);
  let marker=null;
  let changed=false;
  let workspaceShown=novelStreamSequence>0;
  for(const event of events){
    novelStreamSequence=Math.max(novelStreamSequence,Number(event.sequence)||0);
    if(!event.chapter)continue;
    if(state.current!==event.chapter){
      if(!state.chapters.some(chapter=>chapter.name===event.chapter))continue;
      await openChapter(event.chapter);
    }
    if(!workspaceShown){showView('workspace');workspaceShown=true;}
    if(event.type==='translation_snapshot'){
      replaceStreamValue(event.text||'');
      const last=Math.max(0,editorViews.target.lineCount()-1);
      marker={line:last,text:editorViews.target.getLine(last)||''};
      changed=true;
    } else if(event.type==='polish_line'){
      const line=Math.max(0,Number(event.line)||0);
      replaceStreamLine(line,event.text||'');
      marker={line,text:event.text||''};
      changed=true;
    } else if(event.type==='polish_complete'){
      replaceStreamValue(event.text||'');
      changed=true;
    }
  }
  if(marker)markNovelStreamLine(marker.line,marker.text);
  if(changed){
    state.dirty=false;
    updateCounts();
  }
}

function queueNovelStreamEvent(event) {
  const previous=novelStreamPending[novelStreamPending.length-1];
  if(previous&&previous.type==='translation_snapshot'&&event.type==='translation_snapshot'&&previous.chapter===event.chapter)novelStreamPending[novelStreamPending.length-1]=event;
  else novelStreamPending.push(event);
  if(!novelStreamFrame)novelStreamFrame=requestAnimationFrame(flushNovelStreamEvents);
}

async function flushNovelStreamEvents() {
  novelStreamFrame=null;
  if(novelStreamApplying){novelStreamFrame=requestAnimationFrame(flushNovelStreamEvents);return;}
  const events=novelStreamPending.splice(0);
  if(!events.length)return;
  novelStreamApplying=true;
  try { await applyNovelStreamEvents({stream_events:events}); }
  finally {
    novelStreamApplying=false;
    if(novelStreamPending.length&&!novelStreamFrame)novelStreamFrame=requestAnimationFrame(flushNovelStreamEvents);
  }
}

function openNovelEventStream(kind) {
  if(novelStreamSource)novelStreamSource.close();
  novelStreamPending=[];
  const source=new EventSource(`/api/job-stream/${encodeURIComponent(kind)}?after=${novelStreamSequence}`);
  novelStreamSource=source;
  source.onmessage=event=>{
    try { queueNovelStreamEvent(JSON.parse(event.data)); }
    catch(_error) {}
  };
  source.addEventListener('done',()=>{
    source.close();
    if(novelStreamSource===source)novelStreamSource=null;
  });
  source.onerror=()=>{
    source.close();
    if(novelStreamSource===source)novelStreamSource=null;
  };
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
  {id:'v1-interactions',code:'VI',group:'translation',title:'Gemini Interactions (Beta)',desc:'Dịch trực tiếp trong editor; biên tập chỉ hiện từng dòng thay đổi.'},
  {id:'v2',code:'V2',group:'translation',title:'Gemini Web',desc:'Dịch đơn chương qua hồ sơ trình duyệt Gemini.'},
  {id:'v3',code:'V3',group:'translation',title:'Gemini Web Batch',desc:'Dịch nhiều chương mỗi batch và chạy hậu xử lý.'},
  {id:'gpt',code:'GPT',group:'translation',title:'ChatGPT Web',desc:'Dịch batch qua hồ sơ trình duyệt ChatGPT.'},
  {id:'gpt-api',code:'GA',group:'translation',title:'GPT API',desc:'Dịch và hiệu đính tuần tự trước khi lưu.'},
  {id:'manual',code:'MN',group:'translation',title:'Dịch thủ công',desc:'Xuất prompt và nhận kết quả AI trực tiếp.'},
  {id:'context-api',code:'CA',group:'memory',title:'Tạo context bằng Gemini API',desc:'Sinh glossary bằng API, không cần mở trình duyệt.'},
  {id:'context-v1',code:'C1',group:'memory',title:'Tạo context bằng Gemini Web',desc:'Sinh glossary qua hồ sơ trình duyệt Gemini.'},
  {id:'context-gpt',code:'CG',group:'memory',title:'Tạo context bằng ChatGPT Web',desc:'Sinh glossary qua hồ sơ trình duyệt ChatGPT.'},
  {id:'characters',code:'CH',group:'memory',title:'Hồ sơ nhân vật',desc:'Phân tích và cập nhật thông tin nhân vật.'},
  {id:'review',code:'RV',group:'quality',title:'Review toàn bộ',desc:'Đối chiếu raw và bản dịch để tìm lỗi nội dung.'},
  {id:'hako',code:'UP',group:'publishing',title:'Đăng lên Hako',desc:'Đăng chương Markdown và tải ảnh lên R2 khi cần.'},
];
const taskSchemas = {
  v1:{title:'Gemini API V1',description:'Chọn số lượng công việc thực hiện trong lần chạy này.',fields:[]},
  'v1-interactions':{title:'V1 · Gemini Interactions Streaming (Beta)',description:'Dịch trực tiếp trong Không gian truyện; khi biên tập chỉ cập nhật dòng thay đổi và đặt con trỏ tại vị trí AI đang sửa. Dùng bộ lọc an toàn mặc định của Google.',fields:[]},
  review: {title:'Review đối chiếu toàn bộ',description:'So sánh từng chương ở ngôn ngữ nguồn với bản dịch Việt. Chọn phạm vi và mức song song trước khi gửi API.',fields:[['start','Bắt đầu từ chương','number','1'],['end','Kết thúc tại chương','number',''],['force','Review lại chương đã có','checkbox',false],['batch_size','Số chương mỗi batch','number','10'],['workers','Số luồng song song','number','10'],['sleep','Giây nghỉ giữa batch','number','4']]},
  hako:{title:'Đăng chương lên Hako',description:'Chọn chương đầu và chương cuối. App tự xác định volume, Book ID và ảnh cần tải lên.',fields:[['set_as_incomplete','Đánh dấu chương chưa hoàn thành','checkbox',false]]},
  v2:{title:'Gemini Web V2',description:'Cấu hình browser và phạm vi chạy ngay tại đây.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true]]},
  v3:{title:'Gemini Web V3',description:'Cấu hình browser, batch và phạm vi chạy.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true],['batch_size','Số chương mỗi batch','number','2'],['batch_runs','Số lần chạy batch (0 = đến hết)','number','1']]},
  gpt:{title:'ChatGPT Web',description:'Cấu hình browser, batch và phạm vi chạy.',fields:[['open_browser_setup','Mở màn hình kiểm tra đăng nhập ChatGPT','checkbox',true],['batch_size','Số chương mỗi batch','number','1'],['batch_runs','Số lần chạy batch (0 = đến hết)','number','1']]},
  'gpt-api':{title:'GPT API · Dịch và hiệu đính',description:'Mỗi chương được dịch rồi hiệu đính bằng hai lượt GPT API trước khi lưu.',fields:[]},
  characters:{title:'Tạo hồ sơ nhân vật',description:'Phân tích raw theo phạm vi. Chỉ tăng tiến độ khi AI trả về hồ sơ hợp lệ.',fields:[['character_model','Model Gemini','text','gemini-3.5-flash'],['character_batch_size','Số segment mỗi batch','number','10'],['character_start','Bắt đầu từ segment','number','1'],['character_end','Kết thúc tại segment (để trống = hết)','number',''],['character_retries','Số lần thử API','number','3'],['character_force','Chạy lại phạm vi đã xử lý','checkbox',false]]},
  manual:{title:'Dịch thủ công',description:'Sao chép prompt đầy đủ, gửi cho AI rồi dán kết quả để lưu và hậu xử lý.',fields:[]},
  'context-v1':{title:'Tạo context V1',description:'Chọn số chương xử lý trong mỗi batch và tùy chọn kiểm tra đăng nhập Gemini.',fields:[['batch_size','Số chương mỗi batch','number','30'],['open_browser_setup','Mở màn hình kiểm tra đăng nhập Gemini','checkbox',true]]},
  'context-api':{title:'Tạo context bằng Gemini API',description:'Tạo glossary theo từng batch bằng model context đã cấu hình. Không cần mở trình duyệt.',fields:[['batch_size','Số chương mỗi batch','number','30'],['context_retries','Số lần thử mỗi batch','number','3']]},
  'context-gpt':{title:'Tạo context GPT',description:'Chọn số chương xử lý trong mỗi batch và tùy chọn kiểm tra đăng nhập ChatGPT.',fields:[['batch_size','Số chương mỗi batch','number','30'],['open_browser_setup','Mở màn hình kiểm tra đăng nhập ChatGPT','checkbox',true]]},
};
const multiChapterTasks=new Set(['v1','v1-interactions','v2','gpt-api']);
let pendingTask=null;
let pronounEditIndex=null;

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

function renderThemeOptions() {
  const current=document.documentElement.dataset.theme||'dark-modern';
  $('#themeOptions').innerHTML=appThemes.map(theme=>`<button class="theme-option ${theme.id===current?'active':''}" type="button" data-theme-option="${theme.id}" aria-pressed="${theme.id===current}"><span class="theme-swatch" aria-hidden="true"></span><span><strong>${theme.name}</strong><small>${theme.description}</small></span></button>`).join('');
  $$('[data-theme-option]').forEach(button=>button.onclick=()=>applyTheme(button.dataset.themeOption));
}

function applyTheme(themeId) {
  const theme=appThemes.find(item=>item.id===themeId)||appThemes[1];
  document.documentElement.dataset.theme=theme.id;
  localStorage.setItem('novel-theme',theme.id);
  $('#themeColor').setAttribute('content',theme.color);
  renderThemeOptions();
  requestAnimationFrame(()=>{editorViews.source?.refresh();editorViews.target?.refresh();});
}

function r2CredentialGuide(kind){
  const label=kind==='sharing'?'Share R2':'R2 Xuất bản';
  const note=kind==='sharing'?'<p>Nếu dùng <strong>Tự động thiết lập Cloudflare</strong> ở trên, app sẽ tự điền ba giá trị này.</p>':'';
  return `<details class="cloudflare-token-guide r2-credential-guide"><summary>Cách lấy ${label} Account ID và Access Key</summary>${note}<ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong>.</li><li>Chọn <strong>Manage R2 API Tokens</strong> rồi tạo Account API token hoặc User API token.</li><li>Chọn quyền <strong>Object Read & Write</strong>. Có thể giới hạn token vào bucket dùng cho ${kind==='sharing'?'chia sẻ':'ảnh xuất bản'}.</li><li>Sau khi tạo, sao chép đúng hai giá trị <strong>Access Key ID</strong> và <strong>Secret Access Key</strong> vào app.</li></ol><small>Secret Access Key chỉ được Cloudflare hiển thị một lần. Đây không phải chuỗi API Token dùng để deploy Worker.</small></details>`;
}

function renderPythonSettings(items) {
  settingsItems=items;
  if(!$('#publishingR2Manager')){
    $('#publishingManager').insertAdjacentHTML('afterend',`<div class="cloudflare-deploy-manager" id="publishingR2Manager"><div class="cloudflare-deploy-head"><strong>Tự động thiết lập R2 xuất bản</strong><small>Tạo hoặc cập nhật bucket ảnh public và tự điền toàn bộ cấu hình R2.</small></div><div class="cloudflare-deploy-fields"><label><small>Cloudflare Account ID</small><input id="publishingR2Account" autocomplete="off" placeholder="32 ký tự"></label><label><small>API Token</small><input id="publishingR2Token" type="password" autocomplete="new-password" placeholder="Không lưu token gốc"></label><label><small>Tên bucket ảnh</small><input id="publishingR2Bucket" placeholder="aiko-images"></label></div><details class="cloudflare-token-guide"><summary>Cách lấy Account ID và API Token</summary><ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong> vào ô trên.</li><li>Mở <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noopener noreferrer">Cloudflare → API Tokens</a>, chọn <strong>Create Token</strong> rồi <strong>Create Custom Token</strong>.</li><li>Thêm quyền <strong>Account · Workers R2 Storage · Edit</strong>.</li><li>Ở Account Resources, chọn tài khoản cần dùng; tạo token rồi sao chép vào ô API Token.</li></ol><small>App chỉ dùng token một lần để thiết lập và không lưu token gốc.</small></details><div class="cloudflare-deploy-actions"><small id="publishingR2Status">Bucket này sẽ được bật public qua r2.dev.</small><button class="primary" id="setupPublishingR2" type="button">Tự động thiết lập</button></div></div>`);
    $('#setupPublishingR2').onclick=setupPublishingR2;
  }
  if(!$('#cloudflareDeployManager')){
    $('#geminiApiKeyManager').insertAdjacentHTML('beforebegin',`<div class="cloudflare-deploy-manager" id="cloudflareDeployManager"><div class="cloudflare-deploy-head"><strong>Tự động thiết lập Cloudflare</strong><small>Nhập một token; Python tự tạo khóa R2, bucket, Worker và URL chia sẻ.</small></div><div class="cloudflare-deploy-fields"><label><small>Cloudflare Account ID</small><input id="cloudflareDeployAccount" autocomplete="off" placeholder="32 ký tự"></label><label><small>API Token</small><input id="cloudflareDeployToken" type="password" autocomplete="new-password" placeholder="Không lưu token gốc"></label><label><small>Tên Worker</small><input id="cloudflareDeployWorker" value="aiko-share-reader"></label></div><details class="cloudflare-token-guide"><summary>Cách lấy Account ID và API Token</summary><ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong> vào ô trên.</li><li>Mở <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noopener noreferrer">Cloudflare → API Tokens</a>, chọn <strong>Create Token</strong> rồi <strong>Create Custom Token</strong>.</li><li>Thêm quyền <strong>Account · Workers Scripts · Edit</strong>.</li><li>Thêm quyền <strong>Account · Workers R2 Storage · Edit</strong>.</li><li>Ở Account Resources, chọn tài khoản cần dùng; tạo token rồi sao chép vào ô API Token.</li></ol><small>Token chỉ hiển thị một lần. App không lưu token gốc sau khi thiết lập.</small></details><div class="cloudflare-deploy-actions"><small id="cloudflareDeployStatus">Token cần quyền Workers Scripts Edit và Workers R2 Storage Edit.</small><button class="primary" id="deployShareWorker" type="button">Tự động thiết lập</button></div></div>`);
    $('#deployShareWorker').onclick=deployShareWorker;
  }
  if(!$('#publishingR2Account').value)$('#publishingR2Account').value=items.find(item=>item.key==='r2_account_id')?.value||items.find(item=>item.key==='share_r2_account_id')?.value||'';
  if(!$('#publishingR2Bucket').value)$('#publishingR2Bucket').value=items.find(item=>item.key==='r2_bucket')?.value||'aiko-images';
  if(!$('#cloudflareDeployAccount').value)$('#cloudflareDeployAccount').value=items.find(item=>item.key==='share_r2_account_id')?.value||'';
  $('#settingsTabs').innerHTML=Object.entries(settingsGroups).map(([key,[label]])=>`<button type="button" role="tab" data-settings-tab="${key}" aria-selected="${key===activeSettingsGroup}" class="${key===activeSettingsGroup?'active':''}">${label}<span>${items.filter(item=>item.group===key).length+(key==='general'||key==='publishing'?1:0)}</span></button>`).join('');
  const [title,description]=settingsGroups[activeSettingsGroup];
  $('#settingsGroupTitle').textContent=title; $('#settingsGroupDescription').textContent=description;
  $('#workspaceSettings').classList.toggle('active',activeSettingsGroup==='general');
  $('#geminiApiKeyManager').classList.toggle('active',activeSettingsGroup==='gemini-api');
  $('#publishingManager').classList.toggle('active',activeSettingsGroup==='publishing');
  $('#publishingR2Manager').classList.toggle('active',activeSettingsGroup==='publishing');
  $('#cloudflareDeployManager').classList.toggle('active',activeSettingsGroup==='sharing');
  const settingFields=items.filter(item=>item.group===activeSettingsGroup).map(item=>{
    const control=item.type==='select'
      ? `<select data-python-setting="${escapeHtml(item.key)}">${item.options.map(([value,label])=>`<option value="${escapeHtml(value)}" ${value===item.value?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>`
      : item.type==='textarea'
        ? `<textarea data-python-setting="${escapeHtml(item.key)}" rows="10" spellcheck="false">${escapeHtml(item.value)}</textarea>`
      : `<input data-python-setting="${escapeHtml(item.key)}" type="${item.type}" value="${escapeHtml(item.value)}" ${item.inputmode?`inputmode="${item.inputmode}"`:''} ${item.type==='number'?`min="${item.min}" max="${item.max}"`:''} autocomplete="off">`;
    return `<label class="python-setting ${item.type==='textarea'?'textarea-setting':''}"><span>${escapeHtml(item.label)}${item.overridden?'<em>Đã tùy chỉnh</em>':''}</span>${control}<small>${item.description?escapeHtml(item.description)+' · ':''}${item.type==='textarea'?'Dùng “Khôi phục mặc định” để lấy lại tiêu chí chuẩn.':`Mặc định: ${escapeHtml(item.default||'để trống')}`}</small></label>`;
  }).join('');
  $('#pythonSettingsFields').innerHTML=activeSettingsGroup==='publishing'&&settingFields
    ? `${r2CredentialGuide('publishing')}<details class="publishing-advanced"><summary>Cài đặt nâng cao: tài khoản Hako và kho ảnh</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
    : activeSettingsGroup==='sharing'&&settingFields
      ? `${r2CredentialGuide('sharing')}<details class="publishing-advanced"><summary>Cài đặt R2 nâng cao</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
      : settingFields;
  $$('[data-settings-tab]').forEach(button=>button.onclick=()=>{
    $$('[data-python-setting]').forEach(input=>{ const item=settingsItems.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=input.value; });
    activeSettingsGroup=button.dataset.settingsTab;
    renderPythonSettings(settingsItems);
  });
}

async function setupPublishingR2(){
  const button=$('#setupPublishingR2'),token=$('#publishingR2Token').value.trim();
  if(!token)return toast('Hãy nhập Cloudflare API Token');
  button.disabled=true;button.textContent='Đang thiết lập…';
  $('#publishingR2Status').textContent='Đang tạo bucket và bật đường dẫn public…';
  try{
    const data=await api('/api/publishing-r2/setup',{method:'POST',body:JSON.stringify({account_id:$('#publishingR2Account').value.trim(),api_token:token,bucket:$('#publishingR2Bucket').value.trim()||'aiko-images'})});
    $('#publishingR2Token').value='';
    renderPythonSettings(data.items);
    $('#publishingR2Status').textContent=`Hoàn tất: ${data.public_url}`;
    toast(data.bucket_created?'Đã tạo và cấu hình bucket ảnh':'Đã cập nhật cấu hình bucket ảnh');
  }catch(error){$('#publishingR2Status').textContent=error.message;toast(error.message);}
  finally{button.disabled=false;button.textContent='Tự động thiết lập';}
}

async function deployShareWorker(){
  const button=$('#deployShareWorker'), token=$('#cloudflareDeployToken').value.trim();
  if(!token)return toast('Hãy nhập Cloudflare API Token');
  const visibleBucket=$('[data-python-setting="share_r2_bucket"]')?.value;
  const bucket=visibleBucket||settingsItems.find(item=>item.key==='share_r2_bucket')?.value||'private-shares';
  button.disabled=true;button.textContent='Đang thiết lập…';
  $('#cloudflareDeployStatus').textContent='Đang tạo bucket và tải Worker lên Cloudflare…';
  try{
    const data=await api('/api/share-worker/deploy',{method:'POST',body:JSON.stringify({account_id:$('#cloudflareDeployAccount').value.trim(),api_token:token,bucket,worker_name:$('#cloudflareDeployWorker').value.trim()})});
    $('#cloudflareDeployToken').value='';
    renderPythonSettings(data.items);
    $('#cloudflareDeployStatus').textContent=`Hoàn tất: ${data.worker_url}`;
    toast(data.bucket_created?'Đã tạo bucket và deploy Worker':'Đã cập nhật Worker');
  }catch(error){$('#cloudflareDeployStatus').textContent=error.message;toast(error.message);}
  finally{button.disabled=false;button.textContent='Tự động thiết lập';}
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

function selectedShareChapters(){return $$('[data-share-chapter]:checked').flatMap(input=>JSON.parse(input.dataset.shareFiles||'[]'));}
function groupedShareChapters(items){
  const groups=new Map();
  items.filter(item=>item.translated).forEach(item=>{
    const match=String(item.name||'').match(/^v(\d+)_c(\d+)_s(\d+)\.md$/i);
    const key=match?`v${Number(match[1])}_c${Number(match[2])}`:`file:${item.name}`;
    if(!groups.has(key))groups.set(key,{title:item.title||item.id,names:[],order:match?[Number(match[1]),Number(match[2])]:[Number.MAX_SAFE_INTEGER,item.name]});
    groups.get(key).names.push({name:item.name,segment:match?Number(match[3]):0});
  });
  return [...groups.values()]
    .map(group=>({...group,names:group.names.sort((a,b)=>a.segment-b.segment).map(item=>item.name)}))
    .sort((a,b)=>a.order[0]-b.order[0]||(typeof a.order[1]==='number'?a.order[1]-b.order[1]:String(a.order[1]).localeCompare(String(b.order[1]))));
}
function matchingShareDraft(){
  const recipient=$('#shareRecipient').value.trim().toLocaleLowerCase();
  const title=($('#shareTitle').value.trim()||state.project||'').toLocaleLowerCase();
  return [...projectShares].reverse().find(item=>recipient
    ? String(item.recipient||'').trim().toLocaleLowerCase()===recipient
    : String(item.title||'').trim().toLocaleLowerCase()===title);
}
function updateSharePrimaryAction(){
  if($('#createShare').dataset.loading==='true')return;
  const match=matchingShareDraft();
  $('#createShare').textContent=match?'Cập nhật bản share':'Tạo bản share';
  $('#createShare').dataset.matchedShare=match?.id||'';
}
function renderSharedChapterCatalog(){
  const catalog=$('#sharedChapterCatalog');if(!catalog)return;
  catalog.innerHTML=projectShares.map(item=>`<section class="shared-catalog-group"><div class="shared-catalog-head"><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.recipient||'Không gắn người nhận')} · ${item.chapters?.length||0} chương</small></div><button type="button" data-close-share="${escapeHtml(item.id)}">Đóng share</button></div><div class="shared-catalog-list">${(item.chapters||[]).map(chapter=>`<div class="shared-catalog-row"><span>${escapeHtml(chapter.title||chapter.name)}</span><button type="button" data-remove-shared-chapter="${escapeHtml(chapter.name)}" data-share-id="${escapeHtml(item.id)}">Thu hồi</button></div>`).join('')||'<div class="memory-empty">Bản share chưa có chương.</div>'}</div></section>`).join('')||'<div class="memory-empty">Chưa có chương nào đang được chia sẻ.</div>';
}
function renderShares(){
  const translated=groupedShareChapters(state.chapters);
  $('#shareTitle').placeholder=state.project||'Tên bản đọc';
  $('#shareChapterList').innerHTML=translated.map(item=>`<label class="share-chapter"><input type="checkbox" data-share-chapter data-share-files="${escapeHtml(JSON.stringify(item.names))}"><span>${escapeHtml(item.title)}${item.names.length>1?` <small>· ${item.names.length} phần</small>`:''}</span></label>`).join('')||'<div class="memory-empty">Chưa có chương đã dịch.</div>';
  $('#shareList').innerHTML=projectShares.map(item=>`<article class="share-item"><div class="share-item-head"><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.recipient||'Không gắn người nhận')} · ${item.chapters?.length||0} chương</small></div><small>${escapeHtml(String(item.expires_at||'').slice(0,10))}</small></div><div class="share-item-actions"><button class="secondary" type="button" data-copy-share="${escapeHtml(item.url||'')}" ${item.url?'':'disabled'}>Sao chép link</button><button class="primary" type="button" data-update-share="${escapeHtml(item.id)}">Cập nhật chương đã chọn</button></div></article>`).join('')||'<div class="memory-empty">Chưa tạo bản share nào cho truyện này.</div>';
  renderSharedChapterCatalog();
  updateSharePrimaryAction();
}
async function loadShares(){
  if(!state.project){projectShares=[];renderShares();return;}
  try{const data=await api('/api/shares?project='+encodeURIComponent(state.project));projectShares=data.items||[];renderShares();}
  catch(error){projectShares=[];renderShares();toast(error.message);}
}
async function writeShare(shareId=''){
  if(!requireProject())return;
  if($('#createShare').dataset.loading==='true')return;
  const chapters=selectedShareChapters();
  if(!chapters.length)return toast('Hãy chọn ít nhất một chương đã dịch');
  if(!shareId)shareId=matchingShareDraft()?.id||'';
  const existing=projectShares.find(item=>item.id===shareId);
  const title=$('#shareTitle').value.trim()||existing?.title||state.project;
  const recipient=$('#shareRecipient').value.trim()||existing?.recipient||'';
  const button=$('#createShare');
  button.disabled=true;button.dataset.loading='true';button.setAttribute('aria-busy','true');button.classList.add('is-loading');
  button.textContent=shareId?'Đang cập nhật…':'Đang tạo share…';
  try{
    const data=await api('/api/shares?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({share_id:shareId,title,recipient,expires_days:$('#shareExpiresDays').value,chapters})});
    projectShares=data.items||[];renderShares();toast(shareId?'Đã cập nhật các chương lên R2':'Đã tạo bản share private');
  }catch(error){toast(error.message);}
  finally{
    button.disabled=false;button.dataset.loading='false';button.removeAttribute('aria-busy');button.classList.remove('is-loading');updateSharePrimaryAction();
  }
}
async function changeShare(action,shareId,chapter=''){
  const prompt=action==='close'?'Đóng bản share và xóa toàn bộ chương của nó khỏi R2?':'Thu hồi chương này khỏi bản share và R2?';
  if(!confirm(prompt))return;
  try{
    const data=await api('/api/shares?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({action,share_id:shareId,chapter})});
    projectShares=data.items||[];renderShares();toast(action==='close'?'Đã đóng và thu hồi bản share':'Đã thu hồi chương khỏi R2');
  }catch(error){toast(error.message);}
}

function renderGeminiApiKeys() {
  $('#geminiApiKeyCount').textContent=geminiApiKeys.length?`${geminiApiKeys.length} key · hiện tại #${geminiActiveKeyIndex+1}`:'0 key';
  const startSelect=$('#geminiStartKey');
  if(startSelect){
    startSelect.innerHTML=geminiApiKeys.map((_,index)=>`<option value="${index}">Key #${index+1}</option>`).join('');
    startSelect.value=String(Math.min(geminiActiveKeyIndex,Math.max(0,geminiApiKeys.length-1)));
    startSelect.disabled=!geminiApiKeys.length;
  }
  $('#geminiApiKeyList').innerHTML=geminiApiKeys.map((key,index)=>`<div class="api-key-row"><span>${index+1}</span><input type="password" value="${escapeHtml(key)}" data-gemini-api-key autocomplete="off" spellcheck="false" aria-label="Gemini API key ${index+1}"><button type="button" class="secondary" data-toggle-api-key>Hiện</button><button type="button" class="secondary" data-test-api-key>Kiểm tra</button><button type="button" class="api-key-remove" data-remove-api-key aria-label="Xóa API key ${index+1}">Xóa</button><small class="api-key-test-status" data-api-key-test-status></small></div>`).join('')||'<div class="api-key-empty">Chưa có API key. Hãy thêm key để sử dụng Gemini API.</div>';
  $$('[data-toggle-api-key]').forEach(button=>button.onclick=()=>{ const input=button.parentElement.querySelector('input'); const hidden=input.type==='password'; input.type=hidden?'text':'password'; button.textContent=hidden?'Ẩn':'Hiện'; });
  $$('[data-test-api-key]').forEach(button=>button.onclick=()=>testGeminiApiKey(button));
  $$('[data-remove-api-key]').forEach((button,index)=>button.onclick=()=>{ syncGeminiApiKeyDraft(); geminiApiKeys.splice(index,1); renderGeminiApiKeys(); });
}

function syncGeminiApiKeyDraft() {
  geminiApiKeys=$$('[data-gemini-api-key]').map(input=>input.value);
}

async function loadGeminiApiKeys() {
  try { const data=await api('/api/gemini-api-keys'); geminiApiKeys=data.keys; geminiActiveKeyIndex=Number(data.active_index)||0; renderGeminiApiKeys(); }
  catch(error) { toast(error.message); }
}

async function selectActiveGeminiApiKey() {
  const select=$('#geminiStartKey'), previous=geminiActiveKeyIndex;
  select.disabled=true;
  try {
    const data=await api('/api/gemini-api-keys/active',{method:'POST',body:JSON.stringify({active_index:Number(select.value)})});
    geminiActiveKeyIndex=Number(data.active_index)||0; renderGeminiApiKeys();
    toast(`Lần chạy sau sẽ bắt đầu từ key #${geminiActiveKeyIndex+1}`);
  } catch(error) {
    geminiActiveKeyIndex=previous; renderGeminiApiKeys(); toast(error.message);
  } finally { select.disabled=!geminiApiKeys.length; }
}

function ensureR19Config() {
  if($('#r19Model'))return;
  const card=document.createElement('section');
  card.className='r19-config-card';
  card.innerHTML='<div class="r19-config-actions"><strong>Cấu hình R19</strong><button class="secondary" id="resetR19Defaults" type="button">Khôi phục mặc định</button></div><label><span>Model dịch từ R19 trong khung bên dưới</span><input id="r19Model" type="text" spellcheck="false" placeholder="gemini-3.5-flash-lite"></label><label><span>Số chương ngữ cảnh R19</span><input id="r19ContextChapters" type="number" min="0" max="20" step="1" inputmode="numeric"><small>Chỉ ghi đè cài đặt chung khi R19 bật.</small></label><label class="r19-prompt-field"><span>Dòng mở đầu prompt</span><textarea id="r19PromptPrefix" rows="2" spellcheck="false"></textarea><small>Dòng này được đặt trước prompt dịch; hệ thống tự thêm <code>"""</code> đóng ở cuối.</small></label>';
  $('.r19-editor-card').before(card);
  ['#r19Model','#r19ContextChapters','#r19PromptPrefix'].forEach(selector=>$(selector).oninput=updateR19Draft);
  $('#resetR19Defaults').onclick=resetR19Defaults;
}

function resetR19Defaults() {
  $('#r19Model').value=r19Defaults.model;
  $('#r19ContextChapters').value=r19Defaults.context_chapters;
  $('#r19PromptPrefix').value=r19Defaults.prompt_prefix;
  $('#r19Words').value=r19Defaults.words;
  updateR19Draft();
  toast('Đã đưa cấu hình R19 về mặc định. Bấm Lưu cấu hình để áp dụng.');
}

function r19DraftPayload() {
  return {enabled:$('#r19Enabled').checked,words:$('#r19Words').value,model:$('#r19Model').value,context_chapters:$('#r19ContextChapters').value,prompt_prefix:$('#r19PromptPrefix').value};
}

function ensureR19StatusBadge() {
  let badge=$('#r19StatusBadge');
  if(badge)return badge;
  badge=document.createElement('span');
  badge.id='r19StatusBadge'; badge.className='r19-status-badge';
  badge.textContent='R19'; badge.setAttribute('aria-label','Chế độ R19 đang bật');
  $('#saveState').after(badge);
  return badge;
}

function renderR19(data) {
  ensureR19Config();
  r19Defaults={...r19Defaults,...(data.defaults||{})};
  $('#r19Enabled').checked=Boolean(data.enabled);
  $('#r19Words').value=String(data.words||'');
  $('#r19Model').value=String(data.model||'');
  $('#r19ContextChapters').value=Number(data.context_chapters)||0;
  $('#r19PromptPrefix').value=String(data.prompt_prefix||'');
  $('#r19Count').textContent=`${Number(data.count)||0} cụm từ`;
  $('#r19ModeLabel').textContent=data.enabled?'Đang bật':'Đang tắt';
  ensureR19StatusBadge().classList.toggle('active',Boolean(data.enabled));
  $('#r19SaveState').textContent='Đã đồng bộ';
}

function ensureR19ShortcutHelp() {
  const section=$('#help-translate');
  if(!section||$('#r19ShortcutHelp'))return;
  const note=document.createElement('p');
  note.id='r19ShortcutHelp'; note.className='help-note help-shortcut-note';
  note.innerHTML='<strong>Dịch R19:</strong> nhấn <kbd>F9</kbd> hoặc <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>9</kbd> để mở trang quản lý ẩn.';
  section.querySelector('.help-actions')?.before(note);
}

async function loadR19() {
  if(!state.project)return;
  try { renderR19(await api('/api/r19?project='+encodeURIComponent(state.project))); }
  catch(error) { $('#r19SaveState').textContent='Không thể tải'; toast(error.message); }
}

function updateR19Draft() {
  const enabled=$('#r19Enabled').checked;
  const terms=$('#r19Words').value.split(/\r?\n/).map(line=>line.split('=',1)[0].trim()).filter(line=>line&&!line.startsWith('#'));
  $('#r19ModeLabel').textContent=enabled?'Sẽ bật sau khi lưu':'Sẽ tắt sau khi lưu';
  $('#r19Count').textContent=`${new Set(terms.map(term=>term.toLocaleLowerCase())).size} cụm từ`;
  $('#r19SaveState').textContent='Có thay đổi chưa lưu';
}

async function saveR19() {
  if(!state.project)return toast('Hãy chọn một truyện trước khi bật hoặc tắt R19');
  const button=$('#saveR19'); button.disabled=true; button.textContent='Đang lưu…';
  try {
    const data=await api('/api/r19?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify(r19DraftPayload())});
    renderR19(data); toast(data.enabled?'Đã bật Dịch R19':'Đã lưu và tắt Dịch R19');
  } catch(error) { $('#r19SaveState').textContent='Lưu thất bại'; toast(error.message); }
  finally { button.disabled=false; button.textContent='Lưu cấu hình'; }
}

function untranslatedR19Words(text) {
  const seen=new Set();
  return String(text||'').split(/\r?\n/).map(line=>line.trim()).filter(line=>{
    if(!line||line.startsWith('#')||line.includes('='))return false;
    const key=line.toLocaleLowerCase();
    if(seen.has(key))return false;
    seen.add(key); return true;
  });
}

async function translateR19Words() {
  if(!state.project)return toast('Hãy chọn một truyện để lưu log request R19');
  const button=$('#translateR19Words'), saveButton=$('#saveR19');
  button.disabled=true; saveButton.disabled=true;
  try {
    let data=await api('/api/r19?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify(r19DraftPayload())});
    renderR19(data);
    const pending=untranslatedR19Words(data.words);
    if(!pending.length)return toast('Tất cả dòng R19 đã có bản dịch');
    for(let index=0;index<pending.length;index++){
      button.textContent=`Đang dịch ${index+1}/${pending.length}…`;
      $('#r19SaveState').textContent=`Đang dịch: ${pending[index]}`;
      data=await api('/api/r19/translate-word?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({source:pending[index]})});
      renderR19(data);
    }
    toast(`Đã dịch ${pending.length} dòng R19`);
  } catch(error) { $('#r19SaveState').textContent='Dừng do lỗi'; toast(error.message); }
  finally { button.disabled=false; saveButton.disabled=false; button.textContent='Dịch các dòng chưa có'; }
}

async function saveGeminiApiKeys() {
  syncGeminiApiKeyDraft();
  const button=$('#saveGeminiApiKeys'); button.disabled=true;
  try { const data=await api('/api/gemini-api-keys',{method:'POST',body:JSON.stringify({keys:geminiApiKeys})}); geminiApiKeys=data.keys; geminiActiveKeyIndex=Number(data.active_index)||0; renderGeminiApiKeys(); toast(`Đã lưu ${data.count} Gemini API key`); }
  catch(error) { toast(error.message); }
  finally { button.disabled=false; }
}

async function testGeminiApiKey(button) {
  const key=button.parentElement.querySelector('[data-gemini-api-key]').value.trim();
  const status=button.parentElement.querySelector('[data-api-key-test-status]');
  if(!key){status.className='api-key-test-status error';status.textContent='LỖI · Key đang trống';return false;}
  button.disabled=true; button.textContent='Đang kiểm tra…';
  try {
    const data=await api('/api/gemini-api-keys/test',{method:'POST',body:JSON.stringify({key})});
    status.className=`api-key-test-status ${data.ok?'success':'error'}`;
    status.textContent=`${data.code} · ${data.message} · ${data.model}`;
    return data.ok;
  } catch(error) {
    status.className='api-key-test-status error'; status.textContent=`LỖI · ${error.message}`;
    return false;
  }
  finally { button.disabled=false; button.textContent='Kiểm tra'; }
}

async function testAllGeminiApiKeys() {
  const buttons=$$('[data-test-api-key]'), batchButton=$('#testAllGeminiApiKeys');
  if(!buttons.length)return toast('Chưa có API key để kiểm tra');
  batchButton.disabled=true; batchButton.textContent=`Đang kiểm tra 0/${buttons.length}…`;
  let passed=0;
  try {
    for(let index=0;index<buttons.length;index++){
      batchButton.textContent=`Đang kiểm tra ${index+1}/${buttons.length}…`;
      if(await testGeminiApiKey(buttons[index]))passed++;
    }
    toast(`Kiểm tra xong: ${passed} hoạt động, ${buttons.length-passed} lỗi`);
  } finally { batchButton.disabled=false; batchButton.textContent='Kiểm tra tất cả'; }
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

async function autoCheckForUpdate() {
  const key='aiko-last-update-check';
  try {
    const lastCheck=Number(localStorage.getItem(key)||0);
    if(Date.now()-lastCheck<24*60*60*1000)return;
    localStorage.setItem(key,String(Date.now()));
  } catch(error) {}
  try {
    const data=await api('/api/update?check=1');
    renderUpdateStatus(data);
    if(data.update_available)toast(`Có bản cập nhật ${data.latest_version}`);
  } catch(error) {}
}

function renderWhatsNew(entry) {
  $('#whatsNewVersion').textContent=`v${entry.version}${entry.date?` · ${entry.date}`:''}`;
  $('#whatsNewTitle').textContent=entry.title||'Có gì mới?';
  $('#whatsNewSummary').textContent=entry.summary||'Ứng dụng đã được cập nhật lên phiên bản mới.';
  const highlights=Array.isArray(entry.highlights)?entry.highlights.filter(Boolean):[];
  $('#whatsNewList').innerHTML=highlights.length
    ?highlights.map(item=>`<div class="whats-new-item"><span>✓</span><p>${escapeHtml(item)}</p></div>`).join('')
    :'<div class="whats-new-empty">Chưa có ghi chú chi tiết cho phiên bản này.</div>';
}

async function loadWhatsNew(force=false) {
  try {
    const [update,notes]=await Promise.all([api('/api/update'),api('/release-notes.json')]);
    const versions=Array.isArray(notes.versions)?notes.versions:[];
    const entry=versions.find(item=>String(item.version)===String(update.current_version))||{
      version:update.current_version,
      title:`Aiko App Translator ${update.current_version}`,
      summary:'Ứng dụng đã được cập nhật lên phiên bản mới.',
      highlights:[],
    };
    whatsNewData=entry;
    renderWhatsNew(entry);
    const seen=localStorage.getItem('novel-whats-new-version');
    if(force||seen!==String(entry.version)){
      $('#whatsNewModal').classList.add('open');
      requestAnimationFrame(()=>$('#closeWhatsNew').focus());
    }
  } catch(error) {
    if(force)toast(error.message);
  }
}

function closeWhatsNew() {
  if(whatsNewData?.version)localStorage.setItem('novel-whats-new-version',String(whatsNewData.version));
  $('#whatsNewModal').classList.remove('open');
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
    navigationCounts.chapters=data.total; if($('#chapterBadge'))$('#chapterBadge').textContent=data.total;
    renderChapterList(); renderPopover();
    renderShares();
    updateChapterNavigation();
    if (!state.current && state.chapters.length) openChapter(state.chapters.find(x => !x.translated)?.name || state.chapters[0].name,project,revision);
  } catch (error) { if(state.project===project&&state.projectRevision===revision)toast(error.message); }
}

async function loadProjects(preferredProject='') {
  try {
    const data = await api('/api/projects');
    state.projects = data.items;
    $('#projectItems').innerHTML = state.projects.length
      ? state.projects.map(name => `<button class="pop-item" data-project="${name}"><span>${name}</span></button>`).join('')
      : '<div class="empty-state"><p>Chưa tìm thấy truyện.</p></div>';
    const remembered = localStorage.getItem('novel-project');
    const first = state.projects.includes(preferredProject) ? preferredProject : (state.projects.includes(remembered) ? remembered : state.projects[0]);
    if (first) await selectProject(first); else toast('Chưa có truyện nào trong thư mục truyen');
  } catch (error) { toast(error.message); }
}

async function selectProject(name) {
  if (state.dirty) await saveChapter();
  if (state.characterDirty) {
    await saveCharacters();
    if (state.characterDirty) return;
  }
  if(state.glossaryDirty){
    await saveGlossaryChanges();
    if(state.glossaryDirty)return;
  }
  state.projectRevision+=1;
  state.project = name; state.current = null; state.chapters = [];
  localStorage.setItem('novel-project', name);
  $('#currentProject').textContent = name; $('#activeProjectLabel').textContent = name;
  $('#currentChapter').textContent = 'Chọn một chương';
  updateChapterNavigation();
  setEditorValue('source',''); setEditorValue('target','');
  updateLineNumbers('source'); updateLineNumbers('target');
  state.reviews=[]; state.context={index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_yaml:''};
  projectShares=[];renderShares();
  renderContext();
  state.currentImages=[]; renderMarkdownEditors();
  $('#projectPopover').classList.remove('open');
  await Promise.all([loadChapters(), loadReviews(), loadContext(), loadCharacters(), loadPronouns(), loadPublishingBooks(), loadShares(), loadR19()]); toast('Đã mở ' + name);
  if($('#aiLogDrawer').classList.contains('open'))loadAiLogs(true);
  hakoRemoteChapters=[];
  $('#hakoPublicUrl').value=localStorage.getItem(`hako-public-url:${name}`)||'';
  resetHakoEdit();
}

async function loadContext() {
  if (!state.project) return;
  const project=state.project, revision=state.projectRevision;
  try {
    const context=await api('/api/context?project='+encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.context=context;
    state.glossaryDirty=false;
  } catch(error) {
    if(state.project!==project||state.projectRevision!==revision)return;
    state.context={index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_yaml:''}; toast(error.message);
  }
  state.glossaryDirty=false;
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
  navigationCounts.characters=count;if($('#characterBadge'))$('#characterBadge').textContent=count;
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
  navigationCounts.pronouns=data.count||0;if($('#pronounBadge'))$('#pronounBadge').textContent=data.count||0;
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
  $('#pronounDetail').querySelectorAll('.pronoun-history-item').forEach((row,index)=>row.querySelector('div').insertAdjacentHTML('beforeend',`<button class="secondary pronoun-history-edit" data-pronoun-history-index="${escapeHtml(history[index].record_index)}">Sửa mốc này</button>`));
  $('#editPronounPair').onclick=()=>openPronounEditor();
  $('#deletePronounPair').onclick=deletePronounPair;
}

function openPronounEditor(recordIndex=null) {
  const pair=(state.pronouns.pairs||[]).find(item=>item.key===state.pronounCurrent);
  if(!pair)return;
  const latest=recordIndex===null?(pair.latest||{}):(pair.timeline||[]).find(item=>item.record_index===Number(recordIndex));
  if(!latest)return toast('Không tìm thấy mốc lịch sử xưng hô');
  pronounEditIndex=latest.record_index;
  $('#pronounModalTitle').textContent=`${pronounPairLabel(pair)} · Chương ${latest.chapter_number??'—'}`;
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
    state.pronouns=await api('/api/pronouns?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({key:state.pronounCurrent,timeline_index:pronounEditIndex,expected_speaker:$('#pronounSpeaker').value,expected_listener:$('#pronounListener').value,speaker_self:$('#pronounSelf').value,speaker_to_listener:$('#pronounToListener').value,relationship_status:$('#pronounRelationship').value,emotional_tone:$('#pronounTone').value,locked:$('#pronounLocked').checked})});
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
  const items=(context.glossary||[]).map((item,index)=>({...item,index})).filter(item=>!query||item.source.toLowerCase().includes(query)||item.target.toLowerCase().includes(query));
  $('#contextSummary').textContent=state.project?`${state.project} · context đến chương ${context.index||0}`:'Chưa chọn truyện.';
  $('#glossaryCount').textContent=`${items.length}/${(context.glossary||[]).length} thuật ngữ`;
  $('#glossaryList').innerHTML=items.length?items.map(item=>`<div class="glossary-row" data-glossary-index="${item.index}"><input data-glossary-field="source" value="${escapeHtml(item.source)}" placeholder="Nguyên văn" aria-label="Nguyên văn thuật ngữ"><i>→</i><input data-glossary-field="target" value="${escapeHtml(item.target)}" placeholder="Bản dịch" aria-label="Bản dịch thuật ngữ"><button type="button" data-delete-glossary aria-label="Xóa ${escapeHtml(item.source||'thuật ngữ')}">Xóa</button></div>`).join(''):'<div class="memory-empty">Không có thuật ngữ phù hợp.</div>';
  $('#saveGlossaryButton').disabled=!state.glossaryDirty;
  $('#glossarySaveState').textContent=state.glossaryDirty?'Có thay đổi chưa lưu':'Đã đồng bộ';
  $('#styleNotes').textContent=context.style_notes||'Chưa có style note cho truyện này.';
}

function markGlossaryDirty() {
  state.glossaryDirty=true;
  $('#saveGlossaryButton').disabled=false;
  $('#glossarySaveState').textContent='Có thay đổi chưa lưu';
}

function addGlossaryItem() {
  if(!requireProject())return;
  state.context.glossary.push({source:'',target:''});
  markGlossaryDirty();
  $('#glossarySearch').value='';
  renderContext();
  $('#glossaryList [data-glossary-index]:last-child input')?.focus();
}

async function saveGlossaryChanges() {
  if(!requireProject())return;
  const items=(state.context.glossary||[]).map(item=>({source:String(item.source||'').trim(),target:String(item.target||'').trim()}));
  const invalid=items.findIndex(item=>!item.source||!item.target||item.source.includes('='));
  if(invalid>=0)return toast(`Thuật ngữ dòng ${invalid+1} cần đủ nguyên văn và bản dịch; nguyên văn không được chứa dấu =`);
  const button=$('#saveGlossaryButton');button.disabled=true;button.textContent='Đang lưu…';
  try {
    state.context=await api('/api/context?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({glossary_items:items})});
    state.glossaryDirty=false;renderContext($('#glossarySearch').value);toast('Đã lưu glossary · Có bản sao .bak');
  } catch(error) { toast(error.message); }
  finally { button.textContent='Lưu thay đổi';button.disabled=!state.glossaryDirty; }
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
  renderPromptPresets();
  $('#contextPromptRole').value=state.context.prompt_role||'';
  $('#contextPromptTask').value=state.context.prompt_task||'';
  syncPromptPreset();
  renderPolishPromptPresets();
  $('#contextPolishPromptRole').value=state.context.polish_prompt_role||'';
  $('#contextPolishPromptTask').value=state.context.polish_prompt_task||'';
  syncPolishPromptPreset();
  setContextTab('writing');
  updateContextEditorStatus();
  $('#contextModal').classList.add('open');
}

function renderPromptPresets() {
  const presets=state.context.prompt_presets||[];
  const selected=state.context.prompt_preset||'default';
  $('#contextPromptPreset').innerHTML=presets.map(item=>`<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`).join('')+'<option value="custom">Tự viết</option>';
  $('#contextPromptPreset').value=presets.some(item=>item.key===selected)?selected:'custom';
}

function selectedPromptPreset() {
  const key=$('#contextPromptPreset').value;
  return (state.context.prompt_presets||[]).find(item=>item.key===key);
}

function applyPromptPreset() {
  const preset=selectedPromptPreset();
  if(preset){
    $('#contextPromptRole').value=preset.role;
    $('#contextPromptTask').value=preset.task;
  }
  syncPromptPreset();
  updateContextEditorStatus();
}

function syncPromptPreset() {
  const preset=selectedPromptPreset();
  if(preset&&($('#contextPromptRole').value!==preset.role||$('#contextPromptTask').value!==preset.task)){
    $('#contextPromptPreset').value='custom';
  }
  const current=selectedPromptPreset();
  $('#contextPromptPresetHint').textContent=current?current.description:'Nội dung tự viết được lưu riêng cho truyện này.';
}

function renderPolishPromptPresets() {
  const presets=state.context.polish_prompt_presets||[];
  const selected=state.context.polish_prompt_preset||'default';
  $('#contextPolishPromptPreset').innerHTML=presets.map(item=>`<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`).join('')+'<option value="custom">Tự viết</option>';
  $('#contextPolishPromptPreset').value=presets.some(item=>item.key===selected)?selected:'custom';
}

function selectedPolishPromptPreset() {
  const key=$('#contextPolishPromptPreset').value;
  return (state.context.polish_prompt_presets||[]).find(item=>item.key===key);
}

function applyPolishPromptPreset() {
  const preset=selectedPolishPromptPreset();
  if(preset){
    $('#contextPolishPromptRole').value=preset.role;
    $('#contextPolishPromptTask').value=preset.task;
  }
  syncPolishPromptPreset();
  updateContextEditorStatus();
}

function syncPolishPromptPreset() {
  const preset=selectedPolishPromptPreset();
  if(preset&&($('#contextPolishPromptRole').value!==preset.role||$('#contextPolishPromptTask').value!==preset.task)){
    $('#contextPolishPromptPreset').value='custom';
  }
  const current=selectedPolishPromptPreset();
  $('#contextPolishPromptPresetHint').textContent=current?current.description:'Nội dung tự viết được lưu riêng cho truyện này.';
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
  const promptMissing=!$('#contextPromptRole').value.trim()||!$('#contextPromptTask').value.trim()||!$('#contextPolishPromptRole').value.trim()||!$('#contextPolishPromptTask').value.trim();
  status.classList.toggle('invalid',invalid.length>0||promptMissing);
  status.querySelector('span').textContent=invalid.length?`${invalid.length} dòng glossary chưa hợp lệ`:promptMissing?'Vai trò và nhiệm vụ không được để trống':'Sẵn sàng kiểm tra và lưu';
  status.querySelector('small').textContent=invalid.length?'Mỗi dòng cần có dạng Raw = Dịch.':promptMissing?'Chọn một preset hoặc tự nhập đầy đủ hai phần prompt.':'Bản cũ sẽ được sao lưu tự động trước khi thay thế.';
}

async function saveContextYaml() {
  const button=$('#saveContextEdit'); button.disabled=true; button.textContent='Đang lưu…';
  try {
    const nextIndex=Number($('#contextIndexEditor').value);
    if(nextIndex<(state.context.index||0)&&!confirm(`Bạn đang lùi tiến độ từ chương ${state.context.index||0} về ${nextIndex}. Tiếp tục?`))return;
    const context_fields={index:nextIndex,style_notes:$('#contextStyleEditor').value,glossary:$('#contextGlossaryEditor').value,prompt_preset:$('#contextPromptPreset').value,prompt_role:$('#contextPromptRole').value,prompt_task:$('#contextPromptTask').value,polish_prompt_preset:$('#contextPolishPromptPreset').value,polish_prompt_role:$('#contextPolishPromptRole').value,polish_prompt_task:$('#contextPolishPromptTask').value};
    state.context=await api('/api/context?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({context_fields})});
    state.glossaryDirty=false;
    renderContext($('#glossarySearch').value); $('#contextModal').classList.remove('open'); toast('Đã lưu an toàn · Có bản sao lưu .bak');
  } catch(error) { toast(error.message); }
  finally { button.disabled=false; button.textContent='Kiểm tra và lưu an toàn'; }
}

async function importGlossary() {
  const button=$('#confirmGlossaryImport'); button.disabled=true; button.textContent='Đang nạp…';
  try {
    const context=await api('/api/context?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({glossary_text:$('#glossaryImportText').value})});
    state.context=context; state.glossaryDirty=false; renderContext($('#glossarySearch').value); $('#glossaryModal').classList.remove('open');
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

const aiLogStepLabels={translate:'Dịch',polish:'Hiệu đính',review:'Review',pronouns:'Xưng hô',r19_word:'Dịch R19',fix:'Sửa bản dịch'};
function aiLogLabel(step){return aiLogStepLabels[step]||String(step||'Tác vụ AI');}
function formatAiLogTime(value){
  const date=new Date(value);
  return Number.isNaN(date.getTime())?String(value||'') : date.toLocaleString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'2-digit'});
}
function renderAiLogList(){
  $('#aiLogCount').textContent=`${aiLogs.length} lượt gọi gần nhất`;
  $('#aiLogList').innerHTML=aiLogs.length?aiLogs.map((item,index)=>`<button class="ai-log-item ${index===activeAiLog?'active':''}" type="button" data-ai-log-index="${index}"><span class="ai-log-item-top"><strong>${escapeHtml(aiLogLabel(item.step))}</strong><i class="ai-log-status ${item.ok?'ok':''}" title="${item.ok?'Thành công':'Có lỗi'}"></i></span><small>${escapeHtml(item.chapter_id||'Không rõ chương')} · ${escapeHtml(item.model||'Không rõ model')}</small><time>${escapeHtml(formatAiLogTime(item.ts))}</time></button>`).join(''):'<div class="ai-log-loading">Chưa có nhật ký API trong truyện này.</div>';
  $$('[data-ai-log-index]').forEach(button=>button.onclick=()=>{activeAiLog=Number(button.dataset.aiLogIndex)||0;activeAiLogTab='prompt';renderAiLogList();renderAiLogDetail();});
}
function aiLogTabContent(item,tab){
  if(tab==='prompt')return item.prompt||'';
  if(tab==='response')return item.response||'';
  const attachment=(item.attachments||[])[Number(tab.replace('attachment-',''))];
  return attachment?.content||'';
}
function renderAiLogDetail(){
  const item=aiLogs[activeAiLog];
  if(!item){$('#aiLogDetail').innerHTML='<div class="ai-log-empty"><strong>Chưa có lượt gọi nào</strong><span>Prompt và phản hồi từ các tác vụ API sẽ xuất hiện tại đây.</span></div>';return;}
  const tabs=[['prompt','Prompt'],['response','Response'],...(item.attachments||[]).map((file,index)=>[`attachment-${index}`,file.name||`Tệp ${index+1}`])];
  $('#aiLogDetail').innerHTML=`<div class="ai-log-meta"><span>${escapeHtml(formatAiLogTime(item.ts))}</span><span>${escapeHtml(item.chapter_id||'Không rõ chương')}</span><span>${escapeHtml(item.model||'Không rõ model')}</span><span>${item.ok?'Thành công':'Có lỗi'}</span></div><div class="ai-log-tabs">${tabs.map(([key,label])=>`<button class="${key===activeAiLogTab?'active':''}" type="button" data-ai-log-tab="${escapeHtml(key)}">${escapeHtml(label)}</button>`).join('')}</div><button class="ai-log-copy" id="copyAiLog" type="button">Sao chép</button><pre class="ai-log-content" id="aiLogContent">${escapeHtml(aiLogTabContent(item,activeAiLogTab))}</pre>`;
  $$('[data-ai-log-tab]').forEach(button=>button.onclick=()=>{activeAiLogTab=button.dataset.aiLogTab;renderAiLogDetail();});
  $('#copyAiLog').onclick=()=>copyPlainText(aiLogTabContent(item,activeAiLogTab));
}
async function loadAiLogs(silent=false){
  if(!state.project){aiLogs=[];renderAiLogList();renderAiLogDetail();return;}
  try{
    const data=await api(`/api/ai-logs?project=${encodeURIComponent(state.project)}&limit=200`);
    const selected=aiLogs[activeAiLog];
    aiLogs=data.items||[];
    activeAiLog=Math.max(0,selected?aiLogs.findIndex(item=>item.ts===selected.ts&&item.chapter_id===selected.chapter_id):0);
    renderAiLogList();renderAiLogDetail();
  }catch(error){if(!silent)toast(error.message);}
}
function openAiLog(){
  $('#aiLogDrawer').classList.add('open');$('#aiLogScrim').classList.add('open');
  $('#aiLogDrawer').setAttribute('aria-hidden','false');$('#aiLogToggle').setAttribute('aria-expanded','true');
  loadAiLogs();clearInterval(aiLogRefreshTimer);aiLogRefreshTimer=setInterval(()=>loadAiLogs(true),3000);
}
function closeAiLog(){
  $('#aiLogDrawer').classList.remove('open');$('#aiLogScrim').classList.remove('open');
  $('#aiLogDrawer').setAttribute('aria-hidden','true');$('#aiLogToggle').setAttribute('aria-expanded','false');
  clearInterval(aiLogRefreshTimer);aiLogRefreshTimer=null;
}
async function clearAiLogs(){
  if(!state.project||!confirm('Xóa toàn bộ nhật ký AI của truyện đang mở?'))return;
  try{await api(`/api/ai-logs/clear?project=${encodeURIComponent(state.project)}`,{method:'POST',body:'{}'});aiLogs=[];activeAiLog=0;renderAiLogList();renderAiLogDetail();toast('Đã xóa nhật ký AI');}catch(error){toast(error.message);}
}
function downloadAiLogs(){
  if(!aiLogs.length)return toast('Chưa có nhật ký để tải');
  const blob=new Blob([JSON.stringify(aiLogs,null,2)],{type:'application/json;charset=utf-8'});
  const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`ai-logs-${state.project||'project'}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);
}

function exportScopeChapters(){
  const scope=$('#bookExportScope').value;
  if(scope==='volume'){
    const volume=$('#bookExportVolume')?.value;
    return state.chapters.filter(item=>new RegExp(`^v${volume}_`,'i').test(item.name));
  }
  if(scope==='range'){
    const names=state.chapters.map(item=>item.name);
    let from=names.indexOf($('#bookExportFrom')?.value),to=names.indexOf($('#bookExportTo')?.value);
    if(from<0||to<0)return [];
    if(from>to)[from,to]=[to,from];
    return state.chapters.slice(from,to+1);
  }
  return state.chapters;
}

function renderBookExportScope(){
  const scope=$('#bookExportScope').value;
  if(scope==='volume'){
    const volumes=[...new Set(state.chapters.map(item=>item.name.match(/^v(\d+)_/i)?.[1]).filter(Boolean))].sort((a,b)=>Number(a)-Number(b));
    $('#bookExportScopeFields').innerHTML=`<label><span>Volume</span><select id="bookExportVolume">${volumes.map(value=>`<option value="${value}">Volume ${value}</option>`).join('')}</select></label>`;
  }else if(scope==='range'){
    const options=state.chapters.map(item=>`<option value="${escapeHtml(item.name)}">${escapeHtml(item.title||item.id)}</option>`).join('');
    $('#bookExportScopeFields').innerHTML=`<div class="export-range-grid"><label><span>Từ chương</span><select id="bookExportFrom">${options}</select></label><label><span>Đến chương</span><select id="bookExportTo">${options}</select></label></div>`;
    if(state.chapters.length)$('#bookExportTo').value=state.chapters[state.chapters.length-1].name;
  }else $('#bookExportScopeFields').innerHTML='';
  updateBookExportSummary();
}

function updateBookExportSummary(){
  const selected=exportScopeChapters();
  const source=$('#bookExportSource').value;
  const usable=source==='translated'?selected.filter(item=>item.translated):source==='raw'?selected.filter(item=>item.raw):selected;
  const skipped=selected.length-usable.length;
  $('#bookExportSummary').textContent=`Sẽ xuất ${usable.length.toLocaleString('vi-VN')} chương${skipped?` · Bỏ qua ${skipped} chương chưa có nội dung đã chọn`:''}.`;
  $('#confirmBookExport').disabled=!usable.length;
}

function openBookExport(){
  if(!state.project)return toast('Hãy chọn một truyện trước');
  if(!state.chapters.length)return toast('Truyện chưa có chương để xuất');
  $('#bookExportScope').value='all';$('#bookExportSource').value='translated';
  $('input[name="bookExportFormat"][value="epub"]').checked=true;
  renderBookExportScope();$('#bookExportModal').classList.add('open');
}

function closeBookExport(){$('#bookExportModal').classList.remove('open');}

async function exportBook(){
  const button=$('#confirmBookExport');button.disabled=true;button.textContent='Đang tạo file…';
  try{
    const scope=$('#bookExportScope').value;
    const payload={format:$('input[name="bookExportFormat"]:checked').value,source:$('#bookExportSource').value,scope};
    if(scope==='volume')payload.volume=$('#bookExportVolume').value;
    if(scope==='range'){payload.from=$('#bookExportFrom').value;payload.to=$('#bookExportTo').value;}
    const response=await fetch('/api/export-book?project='+encodeURIComponent(state.project),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'Không thể xuất truyện');}
    const blob=await response.blob();
    const disposition=response.headers.get('Content-Disposition')||'';
    const match=disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=match?decodeURIComponent(match[1]):`export.${payload.format==='markdown'?'md':payload.format}`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    closeBookExport();toast('Đã tạo file xuất truyện');
  }catch(error){toast(error.message);}
  finally{button.textContent='Xuất file';updateBookExportSummary();}
}

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

function findPattern(kind) {
  const current=findState[kind], query=$(`#${kind}Find`).value;
  if(!query)return null;
  const source=current.regex?query:query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return new RegExp(source,`gu${current.case?'':'i'}`);
}

function isWordCharacter(value) {
  return Boolean(value&&/[\p{L}\p{N}_]/u.test(value));
}

function refreshFind(kind) {
  const current=findState[kind], input=$(`#${kind}Find`), count=$(`#${kind}FindCount`), text=editorValue(kind), matches=[];
  current.error='';
  try {
    const pattern=findPattern(kind);
    if(pattern){
      let match;
      while((match=pattern.exec(text))!==null){
        const end=match.index+match[0].length;
        if(!current.word||(!isWordCharacter(text[match.index-1])&&!isWordCharacter(text[end])))matches.push({index:match.index,length:match[0].length,text:match[0],captures:match.slice(1)});
        if(!match[0].length)pattern.lastIndex+=text.codePointAt(pattern.lastIndex)>0xFFFF?2:1;
      }
    }
  } catch(error) {
    current.error=error.message;
  }
  current.matches=matches;
  if(!matches.length)current.index=-1;
  else if(current.index>=matches.length)current.index=0;
  input.classList.toggle('invalid',Boolean(current.error));
  input.title=current.error||'';
  count.classList.toggle('invalid',Boolean(current.error));
  updateFindCount(kind);
}

function updateFindCount(kind) {
  const current=findState[kind];
  $(`#${kind}FindCount`).textContent=current.error?'Regex lỗi':current.matches.length?`${current.index+1}/${current.matches.length}`:'0/0';
}

function selectFind(kind,direction=1) {
  refreshFind(kind);
  const current=findState[kind];
  if(!current.matches.length)return;
  current.index=current.index<0?(direction<0?current.matches.length-1:0):(current.index+direction+current.matches.length)%current.matches.length;
  const editor=editorViews[kind], match=current.matches[current.index], start=match.index;
  editor.setSelection(editor.posFromIndex(start),editor.posFromIndex(start+match.length));
  editor.focus(); editor.scrollIntoView(editor.posFromIndex(start),90); updateFindCount(kind);
}

function markTargetChanged() {
  state.dirty=true; updateCounts(); updateLineNumbers('target'); renderMarkdownEditors(); refreshFind('target'); setSaveState('Chưa lưu');
  clearTimeout(state.timer); if($('#autosave').checked)state.timer=setTimeout(saveChapter,1200);
}

function expandFindReplacement(replacement,match) {
  return replacement.replace(/\$(\$|&|\d{1,2})/g,(token,key)=>{
    if(key==='$')return '$';
    if(key==='&')return match.text;
    const capture=match.captures[Number(key)-1];
    return capture===undefined?token:capture;
  });
}

function replaceCurrent(all=false) {
  const editor=editorViews.target, query=$('#targetFind').value, replacement=$('#targetReplace').value;
  if(!query)return;
  refreshFind('target');
  if(findState.target.error)return toast('Regex không hợp lệ');
  if(all){
    const matches=[...findState.target.matches];
    if(!matches.length)return;
    editor.operation(()=>[...matches].reverse().forEach(match=>editor.replaceRange(expandFindReplacement(replacement,match),editor.posFromIndex(match.index),editor.posFromIndex(match.index+match.length))));
    toast(`Đã thay ${matches.length} kết quả`); return;
  }
  const current=findState.target;
  if(!current.matches.length)return;
  const match=current.matches[Math.max(current.index,0)], start=match.index;
  editor.replaceRange(expandFindReplacement(replacement,match),editor.posFromIndex(start),editor.posFromIndex(start+match.length));
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

function openChapterImport() {
  if(!state.project)return toast('Hãy chọn truyện trước');
  chapterImportPreview=null;
  $('#chapterImportFile').value='';
  $('#chapterImportPreview').classList.remove('open');
  $('#analyzeChapterImport').style.display='';
  $('#confirmChapterImport').style.display='none';
  $('#chapterImportModal').classList.add('open');
}

function renderChapterImportPreview() {
  if(!chapterImportPreview)return;
  const sourceFrom=Number($('#chapterImportFrom').value);
  const sourceTo=Number($('#chapterImportTo').value);
  const volume=Number($('#chapterImportVolume').value);
  const targetStart=Number($('#chapterImportStart').value);
  const confidence={high:'Cao',medium:'Khá',manual:'Cần kiểm tra'}[chapterImportPreview.confidence]||'Cần kiểm tra';
  $('#chapterImportSuggestion').innerHTML=chapterImportPreview.no_new
    ? `<strong>Chưa thấy chương mới rõ ràng</strong><span>Đã tìm thấy ${chapterImportPreview.anchors} điểm neo. Hãy chọn range thủ công nếu EPUB có cấu trúc khác.</span>`
    : `<strong>Đề xuất · độ tin cậy ${confidence}</strong><span>${chapterImportPreview.anchors} chương trùng dùng làm điểm neo · nguồn ${sourceFrom}–${sourceTo} → v${volume}_c${targetStart}…</span>`;
  $('#chapterImportRows').innerHTML=chapterImportPreview.chapters.map(chapter=>{
    const inRange=chapter.source_index>=sourceFrom&&chapter.source_index<=sourceTo;
    const target=targetStart+chapter.source_index-sourceFrom;
    const checked=inRange&&chapter.selected?'checked':'';
    return `<tr class="${inRange?'':'outside-range'}"><td><input type="checkbox" data-import-source="${chapter.source_index}" ${checked} ${inRange?'':'disabled'}></td><td><strong>${chapter.source_index}</strong><span>${escapeHtml(chapter.title)}</span></td><td><code>v${volume}_c${target}_s*.md</code></td><td>${chapter.match?`<b>${chapter.match}</b><small>${Math.round(chapter.match_score*100)}%</small>`:'—'}</td></tr>`;
  }).join('');
  $$('[data-import-source]').forEach(input=>input.onchange=()=>{
    const chapter=chapterImportPreview.chapters.find(item=>item.source_index===Number(input.dataset.importSource));
    if(chapter)chapter.selected=input.checked;
  });
}

function updateChapterImportRange() {
  if(!chapterImportPreview)return;
  const sourceFrom=Number($('#chapterImportFrom').value), sourceTo=Number($('#chapterImportTo').value);
  chapterImportPreview.chapters.forEach(chapter=>{chapter.selected=chapter.source_index>=sourceFrom&&chapter.source_index<=sourceTo;});
  renderChapterImportPreview();
}

async function analyzeChapterImport() {
  const file=$('#chapterImportFile').files[0], limit=Number($('#chapterImportSegmentLimit').value), button=$('#analyzeChapterImport');
  if(!file)return toast('Hãy chọn file EPUB hoặc TXT');
  const format=file.name.toLowerCase().endsWith('.epub')?'epub':file.name.toLowerCase().endsWith('.txt')?'txt':'';
  if(!format)return toast('File phải có định dạng EPUB hoặc TXT');
  if(!Number.isInteger(limit)||limit<500||limit>50000)return toast('Giới hạn segment phải từ 500 đến 50.000');
  button.disabled=true;button.textContent='Đang tìm điểm neo…';
  try {
    const query=new URLSearchParams({project:state.project,format,segment_limit:String(limit)});
    chapterImportPreview=await api('/api/chapters/import-preview?'+query,{method:'POST',headers:{'Content-Type':format==='epub'?'application/epub+zip':'text/plain;charset=utf-8'},body:file});
    $('#chapterImportFrom').value=chapterImportPreview.source_from;
    $('#chapterImportTo').value=chapterImportPreview.source_to;
    $('#chapterImportVolume').value=chapterImportPreview.target_volume;
    $('#chapterImportStart').value=chapterImportPreview.target_start;
    $('#chapterImportPreview').classList.add('open');
    button.style.display='none';
    $('#confirmChapterImport').style.display='';
    renderChapterImportPreview();
  } catch(error){toast(error.message);} finally {button.disabled=false;button.textContent='Phân tích file';}
}

async function confirmChapterImport() {
  if(!chapterImportPreview)return;
  const button=$('#confirmChapterImport');
  const sourceFrom=Number($('#chapterImportFrom').value), sourceTo=Number($('#chapterImportTo').value);
  const targetVolume=Number($('#chapterImportVolume').value), targetStart=Number($('#chapterImportStart').value);
  const selected=$$('[data-import-source]:checked').map(input=>Number(input.dataset.importSource));
  if(!Number.isInteger(sourceFrom)||!Number.isInteger(sourceTo)||sourceTo<sourceFrom||targetVolume<0||targetStart<0)return toast('Range hoặc chương đích không hợp lệ');
  if(!selected.length)return toast('Hãy chọn ít nhất một chương để nhập');
  button.disabled=true;button.textContent='Đang nhập…';
  try {
    const result=await api('/api/chapters/import-confirm?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({token:chapterImportPreview.token,source_from:sourceFrom,source_to:sourceTo,target_volume:targetVolume,target_start:targetStart,selected,conflict:$('#chapterImportConflict').value})});
    $('#chapterImportModal').classList.remove('open');
    chapterImportPreview=null;
    await loadChapters();
    if(result.first_file)await openChapter(result.first_file);
    toast(`Đã thêm ${result.imported} chương${result.skipped?` · bỏ qua ${result.skipped} chương trùng`:''}${result.overwritten?` · ghi đè ${result.overwritten}`:''}`);
  } catch(error){toast(error.message);} finally {button.disabled=false;button.textContent='Nhập các chương đã chọn';}
}

async function cancelChapterImport() {
  const preview=chapterImportPreview;
  chapterImportPreview=null;
  $('#chapterImportModal').classList.remove('open');
  if(preview)try { await api('/api/chapters/import-cancel',{method:'POST',body:JSON.stringify({token:preview.token})}); } catch(_error) {}
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
  const compact=[...clean].filter(char=>!(/\s/u.test(char)));
  const cjk=compact.filter(char=>/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(char));
  if(compact.length&&cjk.length/compact.length>0.5){
    return {count:(clean.match(/[\p{L}\p{N}]/gu)||[]).length,unit:'ký tự'};
  }
  if(Intl?.Segmenter){
    const segments=new Intl.Segmenter('vi',{granularity:'word'}).segment(clean);
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

function lookupLanguageLabel(code) {
  return ({en:'Tiếng Anh',zh:'Tiếng Trung','zh-CN':'Tiếng Trung',ja:'Tiếng Nhật',ko:'Tiếng Hàn',vi:'Tiếng Việt'})[code]||code||'Tự nhận diện';
}

function renderSelectionLookup(result) {
  $('#selectionTranslationText').textContent=result.translated;
  $('#selectionDetectedLanguage').textContent=`Google Translate · ${lookupLanguageLabel(result.detected_language)} → Tiếng Việt`;
}

async function translateRawSelection(event) {
  const fromEditor=event.currentTarget===editorViews.source?.getWrapperElement();
  const text=(fromEditor?editorViews.source.getSelection():String(getSelection()||'')).trim();
  if(!text)return closeSelectionTranslation();
  const popup=$('#selectionTranslation'), output=$('#selectionTranslationText'), requestId=++selectionTranslationRequest;
  output.textContent='Đang dịch…';$('#selectionDetectedLanguage').textContent='';popup.classList.add('open');
  const width=popup.offsetWidth, provisionalLeft=Math.max(12,Math.min(event.clientX-width/2,innerWidth-width-12));
  popup.style.left=provisionalLeft+'px';
  popup.style.top=Math.max(12,event.clientY-popup.offsetHeight-12)+'px';
  try {
    const result=await api('/api/translate-selection',{method:'POST',body:JSON.stringify({text})});
    if(requestId!==selectionTranslationRequest)return;
    renderSelectionLookup(result);
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
    unique.set(key,{...parsed,local_name:item.name,title:item.title||item.id,label:`v${parsed.volume}_c${parsed.chapter} · ${item.title||item.id}`});
  });
  return [...unique.values()].sort((a,b)=>a.key.localeCompare(b.key));
}

function resetHakoEdit() {
  hakoEditMapping=[];
  $('#confirmHakoMapping').checked=false;
  $('#runHakoEdit').disabled=true;
  const targets=publishingChapterTargets();
  const options=targets.map((item,index)=>`<option value="${index}">${escapeHtml(item.label)}</option>`).join('');
  $('#hakoLocalFrom').innerHTML=options;
  $('#hakoLocalTo').innerHTML=options;
  if(targets.length)$('#hakoLocalTo').value=String(targets.length-1);
  $('#hakoRemoteFrom').innerHTML=hakoRemoteChapters.map((item,index)=>`<option value="${index}">${escapeHtml(item.title)}</option>`).join('');
  $('#hakoMapping').innerHTML='<div class="memory-empty">Chưa có bảng đối chiếu.</div>';
}

async function loadHakoChapterList() {
  const button=$('#loadHakoChapters'),url=$('#hakoPublicUrl').value.trim();
  if(!url)return toast('Hãy dán URL trang truyện Hako');
  button.disabled=true;$('#hakoScanStatus').textContent='Đang tải danh sách chương Hako…';
  try{
    const data=await api('/api/hako/chapters?url='+encodeURIComponent(url));
    hakoRemoteChapters=data.items||[];
    localStorage.setItem(`hako-public-url:${state.project||''}`,data.url);
    resetHakoEdit();
    $('#hakoScanStatus').textContent=`Đã tải ${data.total} chương Hako. Chọn điểm bắt đầu tương ứng để đối chiếu.`;
  }catch(error){hakoRemoteChapters=[];resetHakoEdit();$('#hakoScanStatus').textContent=error.message;toast(error.message);}
  finally{button.disabled=false;}
}

function buildHakoEditMapping() {
  const local=publishingChapterTargets();
  const from=Number($('#hakoLocalFrom').value),to=Number($('#hakoLocalTo').value),remoteFrom=Number($('#hakoRemoteFrom').value);
  if(!local.length||!hakoRemoteChapters.length)return toast('Hãy tải danh sách Hako trước');
  if(!Number.isInteger(from)||!Number.isInteger(to)||from>to)return toast('Range local không hợp lệ');
  if(to-from+1>50)return toast('Mỗi lượt chỉ cập nhật tối đa 50 chương');
  if(remoteFrom+to-from>=hakoRemoteChapters.length)return toast('Range Hako không đủ chương để ghép');
  hakoEditMapping=local.slice(from,to+1).map((item,index)=>({local:item,remoteIndex:remoteFrom+index,selected:true}));
  renderHakoEditMapping();
}

function renderHakoEditMapping() {
  $('#confirmHakoMapping').checked=false;$('#runHakoEdit').disabled=true;
  $('#hakoMapping').innerHTML=hakoEditMapping.length?`<table><thead><tr><th>Cập nhật</th><th>Chương local</th><th>Chương trên Hako</th><th>Trạng thái</th></tr></thead><tbody>${hakoEditMapping.map((row,index)=>{
    const remote=hakoRemoteChapters[row.remoteIndex],match=normalizeTitle(row.local.title)===normalizeTitle(remote?.title);
    return `<tr class="${match?'matched':'warning'}"><td><input type="checkbox" data-hako-selected="${index}" ${row.selected?'checked':''}></td><td><strong>${escapeHtml(row.local.label)}</strong></td><td><select data-hako-remote="${index}">${hakoRemoteChapters.map((item,remoteIndex)=>`<option value="${remoteIndex}" ${remoteIndex===row.remoteIndex?'selected':''}>${escapeHtml(item.title)}</option>`).join('')}</select></td><td><span>${match?'Khớp tiêu đề':'Cần kiểm tra'}</span></td></tr>`;
  }).join('')}</tbody></table>`:'<div class="memory-empty">Chưa có bảng đối chiếu.</div>';
  $$('[data-hako-selected]').forEach(input=>input.onchange=()=>{hakoEditMapping[Number(input.dataset.hakoSelected)].selected=input.checked;$('#confirmHakoMapping').checked=false;$('#runHakoEdit').disabled=true;});
  $$('[data-hako-remote]').forEach(select=>select.onchange=()=>{hakoEditMapping[Number(select.dataset.hakoRemote)].remoteIndex=Number(select.value);renderHakoEditMapping();});
}

function normalizeTitle(value){return String(value||'').trim().replace(/\s+/g,' ').toLocaleLowerCase('vi');}

async function runHakoEdit() {
  const chosen=hakoEditMapping.filter(row=>row.selected);
  if(!chosen.length)return toast('Chưa chọn chương nào để cập nhật');
  const ids=chosen.map(row=>hakoRemoteChapters[row.remoteIndex]?.chapter_id);
  if(new Set(ids).size!==ids.length)return toast('Một chương Hako đang bị chọn nhiều lần');
  if(!$('#confirmHakoMapping').checked)return toast('Hãy xác nhận bảng đối chiếu');
  const targets=chosen.map(row=>({local_name:row.local.local_name,chapter_id:hakoRemoteChapters[row.remoteIndex].chapter_id,remote_title:hakoRemoteChapters[row.remoteIndex].title}));
  if(!confirm(`Sắp ghi đè tiêu đề và nội dung của ${targets.length} chương Hako. Tiếp tục?`))return;
  await executePipeline('hako-edit',{hako_edit_targets:targets});
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
  if(multiChapterTasks.has(kind))fields=`<label class="task-field"><span>Số chương muốn chạy</span><input data-task-field="max_chapters" type="number" min="1" step="1" value="1" placeholder="Tất cả"><small>Để trống để chạy đến hết.</small></label>${fields}`;
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
  if('max_chapters' in config&&config.max_chapters!==''&&(!/^\d+$/.test(config.max_chapters)||Number(config.max_chapters)<1))return toast('Số chương muốn chạy phải là số nguyên từ 1 trở lên');
  if('batch_runs' in config&&!/^\d+$/.test(config.batch_runs))return toast('Số lần chạy batch phải là số nguyên từ 0 trở lên');
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
  if(!confirmGlossaryCoverage(pendingTask,config))return;
  $('#taskModal').classList.remove('open'); executePipeline(pendingTask,config);
}

function confirmGlossaryCoverage(kind,config={}) {
  if(!['v1','v1-interactions','v2','v3','gpt','gpt-api','manual','retranslate'].includes(kind))return true;
  const glossaryIndex=Number(state.context?.index)||0;
  let startIndex=kind==='retranslate'
    ? state.chapters.findIndex(item=>item.name===state.current)
    : state.chapters.findIndex(item=>!item.translated);
  if(startIndex<0)return true;
  let endChapter=startIndex+1;
  if(kind!=='retranslate'){
    if(['v3','gpt'].includes(kind)){
      const batchRuns=Number(config.batch_runs);
      endChapter=batchRuns===0?state.chapters.length:Math.min(state.chapters.length,startIndex+Math.max(1,Number(config.batch_size)||1)*Math.max(1,batchRuns||1));
    }
    else endChapter=config.max_chapters===''?state.chapters.length:Math.min(state.chapters.length,startIndex+Math.max(1,Number(config.max_chapters)||1));
  }
  if(endChapter<=glossaryIndex)return true;
  const range=endChapter===startIndex+1?`chương ${endChapter}`:`chương ${startIndex+1}–${endChapter}`;
  return confirm(`Glossary mới được duyệt đến chương ${glossaryIndex}, nhưng tác vụ có thể dịch ${range}.\n\nNhấn OK để vẫn dịch hoặc Cancel để hủy.`);
}

function setTaskStopControls(translation,running) {
  const after=$('#stopAfterCurrent'), immediate=$('#stopImmediately'), current=$('#stopCurrentTask');
  after.style.display=translation&&running?'':'none';
  immediate.style.display=translation&&running?'':'none';
  current.style.display=!translation&&running?'':'none';
  after.disabled=false; immediate.disabled=false; current.disabled=false;
}

async function executePipeline(kind,config) {
  activeJobKind=kind;
  novelStreamSequence=0;
  const pipelineItem=pipelineItems.find(item=>item.id===kind);
  if(pipelineItem)selectPipelineGroup(pipelineItem.group);
  const button = $(`[data-run="${kind}"]`)||(kind==='hako-edit'?$('#runHakoEdit'):null); button.disabled=true; button.textContent='Đang chạy…'; $('#console').classList.add('open'); updateConsoleOutput('Đang khởi động tác vụ…');
  const translation=['v1','v1-interactions','v2','v3','gpt','gpt-api','manual'].includes(kind);
  setTaskStopControls(translation,true);
  if (!state.project) { button.disabled=false; button.textContent='Chạy tác vụ'; return toast('Hãy chọn truyện trước'); }
  showView('pipeline');
  try { await api('/api/run/'+kind+'?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({config:{skip_login_prompt:true,...config}})}); if(kind==='v1-interactions')openNovelEventStream(kind); pollJob(kind,button); } catch(error){ button.disabled=false; button.textContent='Chạy lại'; toast(error.message); }
}
async function pollJob(kind, button) {
  try { const job=await api('/api/job/'+kind); if(!novelStreamSource)await applyNovelStreamEvents(job); updateConsoleOutput(job.output || 'Đang xử lý…'); if(job.status==='running') return setTimeout(()=>pollJob(kind,button),500); activeJobKind=null; button.disabled=false; button.textContent=job.status==='done'?'Chạy lại':'Thử lại'; toast(job.status==='done'?'Tác vụ đã hoàn tất':job.status==='cancelled'?'Đã dừng tác vụ':'Tác vụ gặp lỗi'); await loadChapters(); if(['review','split-review'].includes(kind))await loadReviews(); if(['context-api','context-v1','context-gpt','glossary'].includes(kind))await loadContext(); if(kind==='characters')await loadCharacters(); } catch(error){ button.disabled=false; toast(error.message); }
}

async function restoreActiveJob(job) {
  if(!job)return;
  if(job.project&&state.project!==job.project&&state.projects.includes(job.project))await selectProject(job.project);
  novelStreamSequence=0;
  $('#console').classList.add('open');
  updateConsoleOutput(job.output||'Đang xử lý…');
  showView('pipeline');
  const translation=['v1','v1-interactions','v2','v3','gpt','gpt-api','manual','retranslate'].includes(job.kind);
  $('#stopAfterCurrent').style.display=translation?'':'none';
  $('#stopImmediately').style.display=translation?'':'none';
  $('#stopCurrentTask').style.display=translation?'none':'';
  if(job.kind==='retranslate'){
    activeJobKind='retranslate';
    if(job.streaming)openNovelEventStream('retranslate');
    pollRetranslate();
    return;
  }
  const pipelineItem=pipelineItems.find(item=>item.id===job.kind);
  if(pipelineItem)selectPipelineGroup(pipelineItem.group);
  const button=$(`[data-run="${job.kind}"]`);
  if(!button)return;
  activeJobKind=job.kind;
  button.disabled=true;
  button.textContent='Đang chạy…';
  if(job.streaming)openNovelEventStream(job.kind);
  pollJob(job.kind,button);
}

async function bootstrapWorkspace() {
  let activeJob=null;
  try {
    const data=await api('/api/jobs/active');
    activeJob=(data.items||[])[0]||null;
  } catch(_error) {}
  await loadProjects(activeJob?.project||'');
  await restoreActiveJob(activeJob);
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
  if(!confirmGlossaryCoverage('retranslate'))return;
  if (state.dirty) await saveChapter();
  const engine = $('input[name="engine"]:checked').value;
  novelStreamSequence=0;
  $('#retranslateModal').classList.remove('open');
  $('#console').classList.add('open');
  showView('pipeline');
  updateConsoleOutput(`Đang dịch lại ${state.current} bằng ${engine.toUpperCase()}…`);
  try {
    await api('/api/retranslate?project='+encodeURIComponent(state.project), {method:'POST', body:JSON.stringify({engine,chapter:state.current})});
    if(engine==='v1-interactions')openNovelEventStream('retranslate');
    pollRetranslate();
  } catch(error) { toast(error.message); }
}

async function pollRetranslate() {
  try {
    const job=await api('/api/job/retranslate');
    if(!novelStreamSource)await applyNovelStreamEvents(job);
    updateConsoleOutput(job.output || 'Đang xử lý…');
    if(job.status==='running') return setTimeout(pollRetranslate,500);
    if(job.status==='done') { toast('Đã dịch lại chương'); await openChapter(state.current); }
    else toast('Dịch lại thất bại, bản cũ đã được khôi phục');
    await loadChapters();
  } catch(error) { toast(error.message); }
}

document.addEventListener('click', (event) => {
  const featureAction=event.target.closest('[data-feature-action]');if(featureAction?.dataset.featureAction==='ai-log')openAiLog();
  const view=event.target.closest('[data-view]'); if(view) showView(view.dataset.view);
  const helpView=event.target.closest('[data-help-view]'); if(helpView) showView(helpView.dataset.helpView);
  const helpAction=event.target.closest('[data-help-action]'); if(helpAction) handleHelpAction(helpAction.dataset.helpAction);
  const chapter=event.target.closest('[data-chapter]'); if(chapter) openChapter(chapter.dataset.chapter);
  const project=event.target.closest('[data-project]'); if(project) selectProject(project.dataset.project);
  const run=event.target.closest('[data-run]'); if(run) configureTask(run.dataset.run);
  const historyEdit=event.target.closest('[data-pronoun-history-index]'); if(historyEdit)return openPronounEditor(historyEdit.dataset.pronounHistoryIndex);
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
$('#addChaptersButton').onclick=openChapterImport;
$('#cancelChapterImport').onclick=cancelChapterImport;
$('#analyzeChapterImport').onclick=analyzeChapterImport;
$('#confirmChapterImport').onclick=confirmChapterImport;
['chapterImportFrom','chapterImportTo'].forEach(id=>$(`#${id}`).oninput=updateChapterImportRange);
['chapterImportVolume','chapterImportStart'].forEach(id=>$(`#${id}`).oninput=renderChapterImportPreview);
$('#helpSearch').oninput=event=>filterHelp(event.target.value);
$$('[data-help-topic-button]').forEach(button=>button.onclick=()=>openHelpTopic(button.dataset.helpTopicButton));
$('#chapterSearch').oninput = e => renderChapterList(e.target.value);
$('#exportBookButton').onclick=openBookExport;
$('#closeBookExport').onclick=closeBookExport;
$('#cancelBookExport').onclick=closeBookExport;
$('#confirmBookExport').onclick=exportBook;
$('#bookExportScope').onchange=renderBookExportScope;
$('#bookExportSource').onchange=updateBookExportSummary;
$('#bookExportScopeFields').onchange=updateBookExportSummary;
$('#createShare').onclick=()=>writeShare($('#createShare').dataset.matchedShare||'');
['shareTitle','shareRecipient'].forEach(id=>$(`#${id}`).addEventListener('input',updateSharePrimaryAction));
$('#toggleShareChapters').onclick=()=>{const boxes=$$('[data-share-chapter]');const select=boxes.some(box=>!box.checked);boxes.forEach(box=>box.checked=select);$('#toggleShareChapters').textContent=select?'Bỏ chọn tất cả':'Chọn tất cả';};
$('#shareList').onclick=event=>{const update=event.target.closest('[data-update-share]');if(update)writeShare(update.dataset.updateShare);const copy=event.target.closest('[data-copy-share]');if(copy&&copy.dataset.copyShare)copyPlainText(copy.dataset.copyShare);};
$('#sharedChapterCatalog').onclick=event=>{const close=event.target.closest('[data-close-share]');if(close)return changeShare('close',close.dataset.closeShare);const remove=event.target.closest('[data-remove-shared-chapter]');if(remove)changeShare('remove_chapter',remove.dataset.shareId,remove.dataset.removeSharedChapter);};
$('#openShareSettings').onclick=()=>{activeSettingsGroup='sharing';renderPythonSettings(settingsItems);showView('settings');};
$('#reviewSource').onchange=e=>loadReviews(e.target.value);
$('#reviewToggle').onclick=()=>$('#workspaceReview').classList.toggle('open');
$('#reviewCurrentChapter').onclick=reviewCurrentChapter;
$('#copyTargetPreview').onclick=copyTargetPreview;
$('#closeWorkspaceReview').onclick=()=>$('#workspaceReview').classList.remove('open');
$('#cancelTask').onclick=()=>{manualPromptRequest++;$('#taskModal').classList.remove('open');};
$('#confirmTask').onclick=confirmTask;
$('#popoverSearch').oninput = e => renderPopover(e.target.value);
$('#glossarySearch').oninput = e => renderContext(e.target.value);
$('#addGlossaryButton').onclick=addGlossaryItem;
$('#saveGlossaryButton').onclick=saveGlossaryChanges;
$('#glossaryList').oninput=event=>{
  const input=event.target.closest('[data-glossary-field]');
  const row=input?.closest('[data-glossary-index]');
  if(!input||!row)return;
  const item=state.context.glossary[Number(row.dataset.glossaryIndex)];
  if(!item)return;
  item[input.dataset.glossaryField]=input.value;
  markGlossaryDirty();
};
$('#glossaryList').onclick=event=>{
  const button=event.target.closest('[data-delete-glossary]');
  const row=button?.closest('[data-glossary-index]');
  if(!button||!row)return;
  state.context.glossary.splice(Number(row.dataset.glossaryIndex),1);
  markGlossaryDirty();renderContext($('#glossarySearch').value);
};
$('#pronounSearch').oninput=renderPronouns;
$('#pronounFilter').onchange=renderPronouns;
$('#cancelPronounEdit').onclick=()=>$('#pronounModal').classList.remove('open');
$('#savePronounEdit').onclick=savePronounEdit;
$('#editContextButton').onclick=openContextEditor;
$('#cancelContextEdit').onclick=()=>$('#contextModal').classList.remove('open');
$('#saveContextEdit').onclick=saveContextYaml;
['contextIndexEditor','contextStyleEditor','contextGlossaryEditor'].forEach(id=>$(`#${id}`).oninput=updateContextEditorStatus);
['contextPromptRole','contextPromptTask'].forEach(id=>$(`#${id}`).oninput=()=>{syncPromptPreset();updateContextEditorStatus();});
$('#contextPromptPreset').onchange=applyPromptPreset;
['contextPolishPromptRole','contextPolishPromptTask'].forEach(id=>$(`#${id}`).oninput=()=>{syncPolishPromptPreset();updateContextEditorStatus();});
$('#contextPolishPromptPreset').onchange=applyPolishPromptPreset;
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
$$('[data-find-option]').forEach(button=>button.onclick=()=>{
  const kind=button.dataset.findEditor, option=button.dataset.findOption, current=findState[kind];
  current[option]=!current[option]; current.index=-1;
  button.classList.toggle('active',current[option]);
  button.setAttribute('aria-pressed',String(current[option]));
  refreshFind(kind);
});
$$('[data-find-action]').forEach(button=>button.onclick=()=>{
  const kind=button.dataset.findEditor, action=button.dataset.findAction;
  if(action==='next')selectFind(kind,1);
  if(action==='previous')selectFind(kind,-1);
  if(action==='close')$(`#${kind}FindBar`).classList.remove('open');
  if(action==='replace')replaceCurrent(false);
  if(action==='replace-all')replaceCurrent(true);
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){
    closeSelectionTranslation();
    closeAiLog();
    if($('#whatsNewModal').classList.contains('open'))closeWhatsNew();
  }
  const typing=event.target instanceof HTMLElement&&(event.target.matches('input,textarea,select')||event.target.isContentEditable);
  const openR19=(!event.altKey&&!event.ctrlKey&&!event.metaKey&&event.key==='F9')||(event.ctrlKey&&event.altKey&&!event.metaKey&&event.key==='9');
  if(openR19&&!typing){
    event.preventDefault(); showView('r19');
    return;
  }
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
$('#allFeaturesButton').onclick=openFeatureMenu;
$('#closeFeatureMenu').onclick=closeFeatureMenu;
$('#featureSearch').oninput=event=>renderFeatureCatalog(event.target.value);
$('#featureMenuTabs').onclick=event=>{const tab=event.target.closest('[data-feature-tab]');if(!tab)return;activeFeatureTab=tab.dataset.featureTab;renderFeatureCatalog($('#featureSearch').value);};
$('#featureCatalog').onclick=async event=>{
  const open=event.target.closest('[data-feature-open]');
  if(open){const id=open.dataset.featureOpen;closeFeatureMenu();if(id==='ai-log')openAiLog();else showView(id);return;}
  const pin=event.target.closest('[data-feature-pin]');
  if(pin){const id=pin.dataset.featurePin;const index=pinnedFeatures.indexOf(id);if(index>=0)pinnedFeatures.splice(index,1);else pinnedFeatures.push(id);await saveUiPreferences();renderFeatureCatalog($('#featureSearch').value);return;}
  const move=event.target.closest('[data-feature-move]');
  if(move){const index=pinnedFeatures.indexOf(move.dataset.featureId);const target=move.dataset.featureMove==='up'?index-1:index+1;if(index>=0&&target>=0&&target<pinnedFeatures.length){[pinnedFeatures[index],pinnedFeatures[target]]=[pinnedFeatures[target],pinnedFeatures[index]];await saveUiPreferences();renderFeatureCatalog($('#featureSearch').value);}}
};
$('#featureCatalog').ondragstart=event=>{const row=event.target.closest('[data-feature-drag]');if(!row)return;draggedFeatureId=row.dataset.featureDrag;row.classList.add('dragging');event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',draggedFeatureId);};
$('#featureCatalog').ondragover=event=>{const row=event.target.closest('[data-feature-drag]');if(!row||row.dataset.featureDrag===draggedFeatureId)return;event.preventDefault();event.dataTransfer.dropEffect='move';$$('#featureCatalog .drag-over').forEach(item=>item.classList.remove('drag-over'));row.classList.add('drag-over');};
$('#featureCatalog').ondrop=async event=>{const row=event.target.closest('[data-feature-drag]');if(!row||!draggedFeatureId)return;event.preventDefault();const from=pinnedFeatures.indexOf(draggedFeatureId);let to=pinnedFeatures.indexOf(row.dataset.featureDrag);if(from<0||to<0||from===to)return;const rect=row.getBoundingClientRect();if(event.clientY>rect.top+rect.height/2)to+=1;pinnedFeatures.splice(from,1);if(from<to)to-=1;pinnedFeatures.splice(to,0,draggedFeatureId);draggedFeatureId='';await saveUiPreferences();renderFeatureCatalog($('#featureSearch').value);};
$('#featureCatalog').ondragend=()=>{draggedFeatureId='';$$('#featureCatalog .dragging, #featureCatalog .drag-over').forEach(item=>item.classList.remove('dragging','drag-over'));};
$('#aiLogToggle').onclick=openAiLog;
$('#closeAiLog').onclick=closeAiLog;
$('#aiLogScrim').onclick=closeAiLog;
$('#clearAiLogs').onclick=clearAiLogs;
$('#downloadAiLogs').onclick=downloadAiLogs;
$('#r19Enabled').onchange=updateR19Draft;
$('#r19Words').oninput=updateR19Draft;
$('#saveR19').onclick=saveR19;
$('#translateR19Words').onclick=translateR19Words;
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
$('#showWhatsNew').onclick=()=>loadWhatsNew(true);
$('#closeWhatsNew').onclick=closeWhatsNew;
$('#addGeminiApiKey').onclick=()=>{ syncGeminiApiKeyDraft(); geminiApiKeys.push(''); renderGeminiApiKeys(); const inputs=$$('[data-gemini-api-key]'); inputs[inputs.length-1]?.focus(); };
$('#addGeminiApiKey').insertAdjacentHTML('afterend','<label class="api-key-start"><span>Bắt đầu từ</span><select id="geminiStartKey" aria-label="Chọn API key bắt đầu"></select></label>');
$('#geminiStartKey').onchange=selectActiveGeminiApiKey;
$('#saveGeminiApiKeys').insertAdjacentHTML('beforebegin','<button class="secondary" id="testAllGeminiApiKeys" type="button">Kiểm tra tất cả</button>');
$('#testAllGeminiApiKeys').onclick=testAllGeminiApiKeys;
$('#saveGeminiApiKeys').onclick=saveGeminiApiKeys;
$('#addPublishingBook').onclick=()=>{syncPublishingBookDraft();const used=publishingBooks.map(book=>Number(book.volume)).filter(Number.isFinite);publishingBooks.push({book_id:'',volume:used.length?Math.max(...used)+1:1});renderPublishingBooks();};
$('#savePublishingBooks').onclick=savePublishingBooks;
$('#loadHakoChapters').onclick=loadHakoChapterList;
$('#buildHakoMapping').onclick=buildHakoEditMapping;
$('#confirmHakoMapping').onchange=()=>{$('#runHakoEdit').disabled=!$('#confirmHakoMapping').checked||!hakoEditMapping.some(row=>row.selected);};
$('#runHakoEdit').onclick=runHakoEdit;
$('#openHakoSettings').onclick=()=>{activeSettingsGroup='publishing';renderPythonSettings(settingsItems);showView('settings');};
window.addEventListener('beforeunload', e=>{if(state.dirty||state.characterDirty){e.preventDefault();e.returnValue='';}});
window.addEventListener('resize',()=>{repositionPopovers();updateLineNumbers('source');updateLineNumbers('target');});
window.addEventListener('scroll',repositionPopovers,true);
setEditorMode('source-text');
updateLineNumbers('source'); updateLineNumbers('target');
initCodeEditors();
setWorkspaceMode(window.matchMedia('(max-width:560px)').matches?(localStorage.getItem('mobileWorkspaceMode')||'target'):'split',false);
loadUiPreferences();renderThemeOptions(); initPunctuationOptions(); initPipeline(); ensureR19ShortcutHelp(); bootstrapWorkspace(); loadPythonSettings(); loadGeminiApiKeys(); loadUpdateStatus().then(autoCheckForUpdate); loadWhatsNew(); loadLanStatus();
const apiKeyPathHint=document.querySelector('#geminiApiKeyManager .api-key-head small');if(apiKeyPathHint)apiKeyPathHint.textContent='Mỗi key được lưu trên một dòng trong data/apikeys.txt.';
