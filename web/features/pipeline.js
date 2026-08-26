const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

export function createPipelineFeature({aiLogFeature,api,editorRuntime,editorViews,escapeHtml,loadChapters,loadProjects,openChapter,projectMemoryFeature,publishingBooksFeature,saveChapter,selectProject,settingsFeature,showView,state,toast,updateCounts}) {
  let activeJobKind=null;
  let novelStreamSequence=0;
  let novelStreamLine=null;
  let novelStreamCursor=null;
  let novelStreamSource=null;
  let novelStreamPending=[];
  let novelStreamFrame=null;
  let novelStreamApplying=false;
  let manualPromptRequest=0;
  let lastLiveDataRefresh=0;
  let consoleFollowOutput=true;
  const {loadCharacters,loadContext,loadReviews,requireProject}=projectMemoryFeature;

  const consoleOutput=$('#consoleOutput');
  consoleOutput?.addEventListener('scroll',()=>{
    const distanceFromBottom=consoleOutput.scrollHeight-consoleOutput.clientHeight-consoleOutput.scrollTop;
    consoleFollowOutput=distanceFromBottom<=24;
  });

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
    editorRuntime.syncing=true;
    editor.operation(()=>editor.replaceRange(
      next.slice(prefix,next.length-suffix),
      editor.posFromIndex(prefix),
      editor.posFromIndex(current.length-suffix),
      '+ai-stream'
    ));
    $('#targetEditor').value=next;
    editorRuntime.syncing=false;
  }
  
  function replaceStreamLine(line,text) {
    const editor=editorViews.target;
    if(!editor)return;
    const safeLine=Math.max(0,Number(line)||0);
    editorRuntime.syncing=true;
    editor.operation(()=>{
      while(editor.lineCount()<=safeLine){
        const last=editor.lineCount()-1;
        editor.replaceRange('\n',{line:last,ch:editor.getLine(last).length},null,'+ai-stream');
      }
      editor.replaceRange(text||'',{line:safeLine,ch:0},{line:safeLine,ch:editor.getLine(safeLine).length},'+ai-stream');
    });
    $('#targetEditor').value=editor.getValue();
    editorRuntime.syncing=false;
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
    let reviewsChanged=false;
    let aiLogsChanged=false;
    let workspaceShown=novelStreamSequence>0;
    for(const event of events){
      novelStreamSequence=Math.max(novelStreamSequence,Number(event.sequence)||0);
      if(event.type==='review_saved'){reviewsChanged=true;continue;}
      if(event.type==='ai_log_updated'){aiLogsChanged=true;continue;}
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
    if(reviewsChanged)await loadReviews($('#reviewSource').value||'');
    if(aiLogsChanged&&$('#aiLogDrawer').classList.contains('open'))await aiLogFeature.load(true);
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
    {id:'pipeline',code:'AI',group:'translation',title:'Dịch truyện',desc:'Chọn cách chạy, app tự cấu hình các công đoạn còn lại.'},
    {id:'manual',code:'MN',group:'translation',title:'Dịch thủ công',desc:'Xuất prompt và nhận kết quả AI trực tiếp.'},
    {id:'context',code:'CT',group:'memory',title:'Tạo Context',desc:'Sinh glossary bằng engine đã chọn trong Cài đặt.'},
    {id:'characters',code:'CH',group:'memory',title:'Hồ sơ nhân vật',desc:'Phân tích và cập nhật thông tin nhân vật.'},
    {id:'review',code:'RV',group:'quality',title:'Review toàn bộ',desc:'Đối chiếu raw và bản dịch để tìm lỗi nội dung.'},
    {id:'hako',code:'UP',group:'publishing',title:'Đăng lên Hako',desc:'Đăng chương Markdown và tải ảnh lên R2 khi cần.'},
  ];
  const taskSchemas = {
    pipeline:{title:'Dịch truyện',description:'Chọn một cách chạy. App sẽ tự dùng thiết lập phù hợp cho các công đoạn.',fields:[]},
    review: {title:'Review đối chiếu toàn bộ',description:'So sánh từng chương ở ngôn ngữ nguồn với bản dịch Việt. Chọn phạm vi và mức song song trước khi gửi API.',fields:[['start','Bắt đầu từ chương','number','1'],['end','Kết thúc tại chương','number',''],['force','Review lại chương đã có','checkbox',false],['batch_size','Số chương mỗi batch','number','10'],['workers','Số luồng song song','number','10'],['sleep','Giây nghỉ giữa batch','number','4']]},
    hako:{title:'Đăng chương lên Hako',description:'Chọn chương đầu và chương cuối. App tự xác định volume, Book ID và ảnh cần tải lên.',fields:[['set_as_incomplete','Đánh dấu chương chưa hoàn thành','checkbox',false]]},
    characters:{title:'Tạo hồ sơ nhân vật',description:'Phân tích raw bằng engine đã chọn trong Cài đặt. Chỉ tăng tiến độ khi AI trả về hồ sơ hợp lệ.',fields:[['character_batch_size','Số segment mỗi batch','number','10'],['character_start','Bắt đầu từ segment','number','1'],['character_end','Kết thúc tại segment (để trống = hết)','number',''],['character_retries','Số lần thử mỗi batch','number','3'],['open_browser_setup','Mở trình duyệt để kiểm tra đăng nhập khi dùng Web','checkbox',true],['character_force','Chạy lại phạm vi đã xử lý','checkbox',false]]},
    manual:{title:'Dịch thủ công',description:'Sao chép prompt đầy đủ, gửi cho AI rồi dán kết quả để lưu và hậu xử lý.',fields:[]},
    context:{title:'Tạo Context',description:'Tạo glossary theo từng batch bằng engine và model đã chọn trong Cài đặt.',fields:[['batch_size','Số chương mỗi batch','number','30'],['context_retries','Số lần thử mỗi batch','number','3'],['open_browser_setup','Mở trình duyệt để kiểm tra đăng nhập khi dùng Web','checkbox',true]]},
  };
  const multiChapterTasks=new Set(['pipeline','interactions']);
  let pendingTask=null;
  
  
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
    const previousTop=output.scrollTop;
    const distanceFromBottom=output.scrollHeight-output.clientHeight-previousTop;
    const shouldFollow=consoleFollowOutput&&distanceFromBottom<=24;
    output.textContent=text;
    requestAnimationFrame(()=>{
      if(shouldFollow)output.scrollTop=output.scrollHeight;
      else output.scrollTop=previousTop;
    });
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
    const reviewProvider=kind==='review'?(settingsFeature.getValue('pipeline_review_provider')||'gemini-api'):'';
    const webReview=reviewProvider==='gemini-web'||reviewProvider==='chatgpt-web';
    const taskFields=webReview?(schema.fields||[]).filter(([id])=>id!=='workers'):(schema.fields||[]);
    let fields=taskFields.map(([id,label,type,value,options])=>type==='checkbox'
      ? `<label class="task-check"><input data-task-field="${id}" type="checkbox" ${value?'checked':''}><span>${label}</span></label>`
      : type==='select'?`<label class="task-field"><span>${label}</span><select data-task-field="${id}">${options.map(([key,text])=>`<option value="${key}" ${key===value?'selected':''}>${text}</option>`).join('')}</select></label>`
      : `<label class="task-field"><span>${label}</span>${type==='textarea'?`<textarea data-task-field="${id}" rows="9">${escapeHtml(value)}</textarea>`:`<input data-task-field="${id}" type="${type}" value="${value}" ${type==='number'?'min="0"':''}>`}</label>`).join('');
    if(webReview)fields+=`<small class="pipeline-settings-hint">${reviewProvider==='gemini-web'?'Gemini Web':'ChatGPT Web'} xử lý tuần tự từng chương nên không dùng số luồng song song.</small>`;
    if(kind==='pipeline'){
      fields=`<label class="task-field"><span>Số chương muốn chạy</span><input data-task-field="max_chapters" type="number" min="1" step="1" value="1" placeholder="Tất cả"><small>Để trống để chạy đến hết.</small></label><div class="pipeline-options"><label class="task-check"><input data-task-field="enable_polish" type="checkbox" checked><span>Hiệu đính bản dịch</span></label><label class="task-check"><input data-task-field="enable_pronouns" type="checkbox" checked><span>Xuất xưng hô</span></label><label class="task-check"><input data-task-field="enable_review" type="checkbox" checked><span>Review sau khi dịch</span></label></div><small class="pipeline-settings-hint">Engine và model được quản lý trong Cài đặt > Quy trình dịch.</small>`;
    } else if(multiChapterTasks.has(kind))fields=`<label class="task-field"><span>Số chương muốn chạy</span><input data-task-field="max_chapters" type="number" min="1" step="1" value="1" placeholder="Tất cả"><small>Để trống để chạy đến hết.</small></label>${fields}`;
    if(kind==='hako'){
      const publishingBooks=publishingBooksFeature.getBooks();
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
    if(pendingTask==='pipeline'){
      const saved=settingsFeature.getValue;
      config.translate_provider=saved('pipeline_translate_provider')||'gemini-api';
      config.gemini_api_streaming=saved('gemini_api_streaming')||'off';
      config.polish_provider=saved('pipeline_polish_provider')||'gemini-api';
      config.pronouns_provider=saved('pipeline_pronouns_provider')||'gemini-api';
      config.review_provider=saved('pipeline_review_provider')||'gemini-api';
      ['translate','polish','pronouns','review'].forEach(stage=>{
        config[`${stage}_stage_model`]=saved(`pipeline_${stage}_model`);
        config[`${stage}_stage_thinking`]=saved(`pipeline_${stage}_thinking`);
      });
      config.open_browser_setup=true;config.batch_size=1;config.batch_runs=1;
      if(!config.enable_polish)config.polish_provider='off';
      if(!config.enable_pronouns)config.pronouns_provider='off';
      if(!config.enable_review)config.review_provider='off';
      delete config.enable_polish;delete config.enable_pronouns;delete config.enable_review;
    }
    if(pendingTask==='context'){
      const saved=settingsFeature.getValue;
      config.context_provider=saved('pipeline_context_provider')||'gemini-api';
      config.context_stage_model=saved('pipeline_context_model');
      config.context_stage_thinking=saved('pipeline_context_thinking');
    }
    if(pendingTask==='characters'){
      const saved=settingsFeature.getValue;
      config.characters_provider=saved('pipeline_characters_provider')||'gemini-api';
      config.characters_stage_model=saved('pipeline_characters_model');
      config.characters_stage_thinking=saved('pipeline_characters_thinking');
    }
    if(pendingTask==='review'){
      const saved=settingsFeature.getValue;
      config.review_provider=saved('pipeline_review_provider')||'gemini-api';
      if(config.review_provider==='gemini-web'||config.review_provider==='chatgpt-web')config.workers=1;
      config.review_stage_model=saved('pipeline_review_model');
      config.review_stage_thinking=saved('pipeline_review_thinking');
      config.open_browser_setup=true;
    }
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
    if(!['pipeline','interactions','manual','retranslate'].includes(kind))return true;
    const glossaryIndex=Number(state.context?.index)||0;
    let startIndex=kind==='retranslate'
      ? state.chapters.findIndex(item=>item.name===state.current)
      : state.chapters.findIndex(item=>!item.translated);
    if(startIndex<0)return true;
    let endChapter=startIndex+1;
    if(kind!=='retranslate'){
      endChapter=config.max_chapters===''?state.chapters.length:Math.min(state.chapters.length,startIndex+Math.max(1,Number(config.max_chapters)||1));
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
  
  async function executePipeline(kind,config,options={}) {
    activeJobKind=kind;
    lastLiveDataRefresh=0;
    novelStreamSequence=0;
    const pipelineItem=pipelineItems.find(item=>item.id===kind);
    if(pipelineItem)selectPipelineGroup(pipelineItem.group);
    const button = $(`[data-run="${kind}"]`)||(kind==='hako-edit'?$('#runHakoEdit'):null); button.disabled=true; button.textContent='Đang chạy…'; $('#console').classList.add('open'); updateConsoleOutput('Đang khởi động tác vụ…');
    const translation=['pipeline','interactions','manual'].includes(kind);
    setTaskStopControls(translation,true);
    if (!state.project) { button.disabled=false; button.textContent='Chạy tác vụ'; return toast('Hãy chọn truyện trước'); }
    if(!options.stayOnView)showView('pipeline');
    const streaming=kind==='interactions'||(kind==='pipeline'&&config.translate_provider==='gemini-api'&&config.gemini_api_streaming==='on');
    try { await api('/api/run/'+kind+'?project='+encodeURIComponent(state.project),{method:'POST',body:JSON.stringify({config:{skip_login_prompt:true,...config}})}); if(streaming)openNovelEventStream(kind); pollJob(kind,button,options); } catch(error){ button.disabled=false; button.textContent='Chạy lại'; options.onComplete?.({status:'error',output:error.message}); toast(error.message); }
  }
  async function pollJob(kind, button, options={}) {
    try { const job=await api('/api/job/'+kind); if(!novelStreamSource)await applyNovelStreamEvents(job); updateConsoleOutput(job.output || 'Đang xử lý…'); options.onUpdate?.(job); if(job.status==='running'){const now=Date.now();if(now-lastLiveDataRefresh>=1200){lastLiveDataRefresh=now;if(['pipeline','interactions','manual'].includes(kind))await loadChapters();if(kind==='review')await loadReviews($('#reviewSource').value||'');}return setTimeout(()=>pollJob(kind,button,options),500);} activeJobKind=null; button.disabled=false; button.textContent=job.status==='done'?'Chạy lại':'Thử lại'; toast(job.status==='done'?'Tác vụ đã hoàn tất':job.status==='cancelled'?'Đã dừng tác vụ':'Tác vụ gặp lỗi'); await loadChapters(); if(kind==='review')await loadReviews(); if(kind==='context')await loadContext(); if(kind==='characters')await loadCharacters(); options.onComplete?.(job); } catch(error){ button.disabled=false; options.onComplete?.({status:'error',output:error.message}); toast(error.message); }
  }
  
  async function restoreActiveJob(job) {
    if(!job)return;
    if(job.project&&state.project!==job.project&&state.projects.includes(job.project))await selectProject(job.project);
    if(job.kind==='polish'){
      activeJobKind='polish';
      const button=$('#polishButton');
      button.disabled=true;button.textContent='Đang hiệu đính…';
      pollPolish(job.chapter||state.current);
      return;
    }
    if(job.kind==='review'&&job.workspace_review){
      activeJobKind='review';
      projectMemoryFeature.setReviewLoading(job.chapter||state.current);
      const item=pipelineItems.find(item=>item.id==='review');
      if(item)selectPipelineGroup(item.group);
      const button=$('[data-run="review"]');
      button.disabled=true;button.textContent='Đang chạy…';
      $('#console').classList.add('open');
      pollJob('review',button,{
        stayOnView:true,
        onComplete:()=>projectMemoryFeature.setReviewLoading(null),
      });
      return;
    }
    novelStreamSequence=0;
    $('#console').classList.add('open');
    updateConsoleOutput(job.output||'Đang xử lý…');
    showView('pipeline');
    const translation=['pipeline','interactions','manual','retranslate'].includes(job.kind);
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
      if(engine==='interactions'||(engine==='gemini-api'&&settingsFeature.getValue('gemini_api_streaming')==='on'))openNovelEventStream('retranslate');
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

  async function startPolish() {
    if(!state.current)return toast('Hãy chọn một chương trước');
    if(state.dirty)await saveChapter();
    const chapter=state.current, button=$('#polishButton');
    button.disabled=true;button.textContent='Đang hiệu đính…';
    try {
      await api('/api/run/polish?project='+encodeURIComponent(state.project),{
        method:'POST',body:JSON.stringify({config:{target_chapter:chapter,skip_login_prompt:true}})
      });
      activeJobKind='polish';
      toast('Đã bắt đầu hiệu đính chương');
      pollPolish(chapter);
    } catch(error) {
      button.disabled=false;button.textContent='Hiệu đính';toast(error.message);
    }
  }

  async function pollPolish(chapter) {
    const button=$('#polishButton');
    try {
      const job=await api('/api/job/polish');
      if(job.status==='running')return setTimeout(()=>pollPolish(chapter),500);
      activeJobKind=null;button.disabled=false;button.textContent='Hiệu đính';
      if(job.status==='done'){
        toast('Đã hiệu đính chương');
        await loadChapters();
        if(state.current===chapter)await openChapter(chapter);
      }else{
        const detail=String(job.output||'Hiệu đính thất bại').trim();
        toast(detail.slice(-300));
      }
    } catch(error) {
      button.disabled=false;button.textContent='Hiệu đính';toast(error.message);
    }
  }
  
  
  function handleDocumentClick(event) {
    const run=event.target.closest('[data-run]');
    if(run)configureTask(run.dataset.run);
  }

  function bind() {
    $('#cancelTask').onclick=()=>{manualPromptRequest++;$('#taskModal').classList.remove('open');};
    $('#confirmTask').onclick=confirmTask;
    $('#stopAfterCurrent').onclick=()=>cancelTranslation('after_current');
    $('#stopImmediately').onclick=()=>cancelTranslation('immediate');
    $('#stopCurrentTask').onclick=cancelCurrentTask;
  }

  return {bind,bootstrap:bootstrapWorkspace,configureTask,execute:executePipeline,handleDocumentClick,init:initPipeline,publishingTargets:publishingChapterTargets,selectGroup:selectPipelineGroup,startPolish,startRetranslate};
}
