const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

export function createProjectMemoryFeature({api,escapeHtml,executePipeline,getSetting,markdownToHtml,navigationCounts,prettyName,saveChapter,state,toast,onReviewsChanged=()=>{}}) {
  let pronounEditIndex=null;
  let reviewLoadingChapter=null;

  async function loadContext({strict=false}={}) {
    if (!state.project) return;
    const project=state.project, revision=state.projectRevision;
    try {
      const context=await api('/api/context?project='+encodeURIComponent(project));
      if(state.project!==project||state.projectRevision!==revision)return;
      state.context=context;
      state.glossaryDirty=false;
    } catch(error) {
      if(state.project!==project||state.projectRevision!==revision)return;
      if(strict)throw error;
      state.context={index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_json:''}; toast(error.message);
    }
    state.glossaryDirty=false;
    renderContext($('#glossarySearch')?.value||'');
  }

  async function loadCharacters({strict=false}={}) {
    if(!state.project)return;
    const project=state.project, revision=state.projectRevision;
    try {
      const data=await api('/api/characters?project='+encodeURIComponent(project));
      if(state.project!==project||state.projectRevision!==revision)return;
      state.characters=data; state.characterDirty=false;
      $('#characterEditor').value=data.content||'';
      renderCharacters();
    } catch(error) { if(state.project===project&&state.projectRevision===revision){if(strict)throw error;toast(error.message);} }
  }

  function renderCharacters() {
    const content=$('#characterEditor').value, count=(content.match(/^##\s+.+$/gm)||[]).length;
    navigationCounts.characters=count;if($('#characterBadge'))$('#characterBadge').textContent=count;

    $('#characterSaveState').textContent=state.characterDirty?'Chưa lưu':(!state.characters.exists?'Chưa có dữ liệu':state.characters.backup?'Đã lưu · Có backup':'Đã lưu');
    $('#characterPreview').innerHTML=markdownToHtml(content,[]);
    $('#characterEmpty').classList.toggle('open',!content.trim()&&!state.characterDirty);
  }

  async function loadPronouns({strict=false}={}) {
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
      if(strict)throw error;
      state.pronouns={pairs:[],count:0,locked_count:0,raw_json:''};state.pronounCurrent=null;renderPronouns();toast(error.message);
    }
  }

  function pronounPairLabel(pair) {
    const latest=pair.latest||{};
    return latest.speaker&&latest.listener?`${latest.speaker} → ${latest.listener}`:(pair.characters||[]).join(' ↔ ');
  }

  function renderPronouns() {
    const data=state.pronouns||{pairs:[],count:0,locked_count:0,raw_json:''};
    const query=($('#pronounSearch')?.value||'').trim().toLocaleLowerCase('vi');
    const filter=$('#pronounFilter')?.value||'all';
    const pairs=data.pairs.filter(pair=>{
      const haystack=`${(pair.characters||[]).join(' ')} ${pronounPairLabel(pair)}`.toLocaleLowerCase('vi');
      return (!query||haystack.includes(query))&&(filter==='all'||(filter==='locked'&&pair.locked)||(filter==='conflict'&&pair.changed));
    });
    navigationCounts.pronouns=data.count||0;if($('#pronounBadge'))$('#pronounBadge').textContent=data.count||0;

    $('#pronounCount').textContent=`${pairs.length}/${data.count||0} cặp`;
    $('#pronounRawJson').textContent=data.raw_json||'# Chưa có dữ liệu xưng hô.';
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

  async function openContextEditor() {
    if(!requireProject())return;
    if(state.glossaryDirty){
      await saveGlossaryChanges();
      if(state.glossaryDirty)return;
    }
    await loadContext();
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

  async function saveContextJson() {
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

  async function loadReviews(source='',{strict=false}={}) {
    if (!state.project) return;
    const project=state.project, revision=state.projectRevision;
    try {
      const query = '?project='+encodeURIComponent(project)+(source?'&source='+encodeURIComponent(source):'');
      const data = await api('/api/reviews'+query);
      if(state.project!==project||state.projectRevision!==revision)return;
      state.reviews=data.items; state.reviewCurrent=null; onReviewsChanged();
      $('#reviewBadge').textContent=data.items.length;
      $('#reviewSource').innerHTML=data.sources.map(x=>`<option value="${escapeHtml(x)}" ${x===data.source?'selected':''}>${escapeHtml(x)}</option>`).join('');
      renderWorkspaceReview();
    } catch(error) { if(state.project!==project||state.projectRevision!==revision)return;if(strict)throw error; state.reviews=[]; onReviewsChanged(); $('#reviewBadge').textContent='0'; toast(error.message); }
  }

  function renderWorkspaceReview() {
    const chapterId=(state.current||'').replace(/\.md$/,'');
    const item=state.reviews.find(x=>x.chapter_id===chapterId);
    const currentChapter=state.chapters.find(chapter=>chapter.name===state.current);
    const loading=reviewLoadingChapter===state.current;
    $('#reviewCurrentChapter').disabled=!currentChapter?.translated||Boolean(reviewLoadingChapter);
    $('#reviewCurrentChapter').textContent=loading?'Đang review…':'Review lại';
    $('#workspaceReviewTitle').textContent=state.current?prettyName(state.current):'Chưa chọn chương';
    const reviewBody=$('#workspaceReviewBody');
    reviewBody.setAttribute('aria-busy',String(loading));
    if(loading){if(!reviewBody.firstElementChild?.classList.contains('review-loading'))reviewBody.innerHTML='<div class="review-loading"><span></span><span></span><span></span><i></i><i></i><i></i></div>';return;}
    if(!item){reviewBody.innerHTML='<div class="empty-review"><strong>Chưa có review</strong><span>Chương này chưa có dữ liệu trong file đã chọn.</span></div>';return;}
    const issues=item.issues||[];
    reviewBody.innerHTML=`<div class="review-detail-head"><div class="review-metrics"><span class="metric">Điểm <strong>${item.score??'—'}/10</strong></span><span class="metric"><strong>${item.issue_count??issues.length}</strong> lỗi</span></div></div><p class="review-copy">${escapeHtml(item.summary||'Không có tóm tắt.')}</p><div class="issues">${issues.length?issues.map((issue,index)=>`<section class="issue"><div class="issue-top"><span class="issue-type">Lỗi ${index+1} · ${escapeHtml(issue.type||'khác')}</span><span>${escapeHtml(issue.severity||'')}</span></div><dl><div><dt>NGUYÊN VĂN</dt><dd>${escapeHtml(issue.original_kr||issue.original||'—')}</dd></div><div><dt>BẢN DỊCH</dt><dd>${escapeHtml(issue.original_vi||issue.translation||'—')}</dd></div><div><dt>ĐỀ XUẤT</dt><dd class="suggestion">${escapeHtml(issue.suggestion||'—')}</dd></div></dl></section>`).join(''):'<div class="empty-review"><strong>Không phát hiện lỗi</strong><span>Chương này đã đạt yêu cầu.</span></div>'}</div>`;
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
    const chapter=state.current;
    reviewLoadingChapter=chapter;
    renderWorkspaceReview();
    await executePipeline('review',{
      start:target,
      end:target,
      force:true,
      batch_size:1,
      workers:1,
      sleep:0,
      workspace_review:true,
      target_chapter:chapter,
      review_provider:getSetting('pipeline_review_provider')||'gemini-api',
      review_stage_model:getSetting('pipeline_review_model'),
      review_stage_thinking:getSetting('pipeline_review_thinking'),
      open_browser_setup:true,
    },{
      stayOnView:true,
      onComplete:()=>{
        reviewLoadingChapter=null;
        renderWorkspaceReview();
      },
    });
  }

  function setReviewLoading(chapter=null) {
    reviewLoadingChapter=chapter;
    renderWorkspaceReview();
  }


  function handleDocumentClick(event) {
    const historyEdit=event.target.closest('[data-pronoun-history-index]');
    if(historyEdit){openPronounEditor(historyEdit.dataset.pronounHistoryIndex);return true;}
    const pronoun=event.target.closest('[data-pronoun-key]');
    if(pronoun){state.pronounCurrent=pronoun.dataset.pronounKey;renderPronouns();}
    return false;
  }

  function bind() {
    $('#reviewSource').onchange=event=>loadReviews(event.target.value);
    $('#reviewToggle').onclick=()=>$('#workspaceReview').classList.toggle('open');
    $('#reviewCurrentChapter').onclick=reviewCurrentChapter;
    $('#closeWorkspaceReview').onclick=()=>$('#workspaceReview').classList.remove('open');
    $('#glossarySearch').oninput=event=>renderContext(event.target.value);
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
    $('#saveContextEdit').onclick=saveContextJson;
    ['contextIndexEditor','contextStyleEditor','contextGlossaryEditor'].forEach(id=>$('#'+id).oninput=updateContextEditorStatus);
    ['contextPromptRole','contextPromptTask'].forEach(id=>$('#'+id).oninput=()=>{syncPromptPreset();updateContextEditorStatus();});
    $('#contextPromptPreset').onchange=applyPromptPreset;
    ['contextPolishPromptRole','contextPolishPromptTask'].forEach(id=>$('#'+id).oninput=()=>{syncPolishPromptPreset();updateContextEditorStatus();});
    $('#contextPolishPromptPreset').onchange=applyPolishPromptPreset;
    $$('[data-context-tab]').forEach(button=>button.onclick=()=>setContextTab(button.dataset.contextTab));
    $('#importGlossaryButton').onclick=()=>{if(requireProject()){$('#glossaryModal').classList.add('open');$('#glossaryImportText').focus();}};
    $('#cancelGlossaryImport').onclick=()=>$('#glossaryModal').classList.remove('open');
    $('#confirmGlossaryImport').onclick=importGlossary;
    $('#characterEditor').oninput=()=>{state.characterDirty=true;renderCharacters();};
    $$('[data-character-mode]').forEach(button=>button.onclick=()=>setCharacterMode(button.dataset.characterMode));
    $('#saveCharacters').onclick=saveCharacters;
    $('#characterEmpty').onclick=event=>{if(event.target.closest('button'))return;state.characterDirty=true;renderCharacters();$('#characterEditor').focus();};
  }

  return {bind,handleDocumentClick,loadCharacters,loadContext,loadPronouns,loadReviews,renderContext,renderWorkspaceReview,requireProject,saveCharacters,saveGlossaryChanges,setReviewLoading};
}
