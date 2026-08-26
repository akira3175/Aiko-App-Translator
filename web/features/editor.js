const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

export function createEditorFeature({api,escapeHtml,positionPopover,saveChapter,state,toast}) {
  const views={};
  const runtime={syncing:false,pendingTargetEdit:null};
  const punctuationStyles=[
    ['single-straight', "' '", "'", "'"],
    ['single-curly', '‘ ’', '‘', '’'],
    ['double-straight', '" "', '"', '"'],
    ['double-curly', '“ ”', '“', '”'],
    ['book-title', '《 》', '《', '》']
  ];
  const findState={
    source:{matches:[],index:-1,case:false,word:false,regex:false,error:''},
    target:{matches:[],index:-1,case:false,word:false,regex:false,error:''}
  };
  let selectionTranslationRequest=0;

  function highlightSelectedText(view) {
    if(!view?.on||!view.listSelections||!view.markText)return;
    let markers=[];
    const refresh=()=>{
      markers.forEach(marker=>marker.clear());
      markers=view.listSelections().filter(range=>!range.empty()).map(range=>
        view.markText(range.from(),range.to(),{className:'CodeMirror-selectedtext'})
      );
    };
    view.on('cursorActivity',refresh);
    refresh();
  }

  function initCodeEditors() {
    views.source=CodeMirror.fromTextArea($('#sourceEditor'),{mode:'markdown',lineNumbers:true,lineWrapping:true,readOnly:true,viewportMargin:20});
    views.target=CodeMirror.fromTextArea($('#targetEditor'),{mode:'markdown',lineNumbers:true,lineWrapping:true,viewportMargin:20,extraKeys:{'Ctrl-B':()=>applyFormat('bold'),'Cmd-B':()=>applyFormat('bold'),'Ctrl-I':()=>applyFormat('italic'),'Cmd-I':()=>applyFormat('italic')}});
    highlightSelectedText(views.source);
    highlightSelectedText(views.target);
    views.target.on('change',view=>{
      $('#targetEditor').value=view.getValue();
      if(!runtime.syncing){
        markTargetChanged();
        requestAnimationFrame(()=>{
          const cursor=view.getCursor();
          const height=view.getScrollInfo().clientHeight;
          view.scrollIntoView(cursor,Math.max(80,Math.min(160,height*.25)));
        });
      }
    });
    views.source.getWrapperElement().addEventListener('mouseup',translateRawSelection);
  }
  
  function editorValue(kind) { return views[kind]?.getValue() ?? $(`#${kind}Editor`).value; }
  function setEditorValue(kind,value) {
    const view=views[kind];
    runtime.syncing=true;
    if(view){
      view.setValue(value||'');
      view.clearHistory();
    }
    $(`#${kind}Editor`).value=value||'';
    runtime.syncing=false;
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
    const lineIndex=Number(previewLine.dataset.sourceLine), editor=views.target;
    const lines=editorValue('target').split('\n');
    if(!Number.isInteger(lineIndex)||lineIndex<0||lineIndex>=lines.length)return;
    const previewRect=$('#targetPreview').getBoundingClientRect();
    const clickedOffset=Math.max(60,Math.min(previewRect.height-60,event.clientY-previewRect.top));
    runtime.pendingTargetEdit={line:lineIndex,offset:clickedOffset,attempt:0};
    setEditorMode('target-text');
  }

  function restorePendingTargetEdit() {
    const pending=runtime.pendingTargetEdit, editor=views.target;
    if(!pending||!editor)return;
    editor.refresh();
    const cursor={line:pending.line,ch:0};
    if(pending.attempt===0){
      editor.setCursor(cursor);
      editor.focus();
      editor.getWrapperElement?.().scrollIntoView({block:'nearest'});
    }
    const scroller=editor.getScrollerElement();
    const coordinates=editor.charCoords(cursor,'local');
    scroller.scrollTop=Math.max(0,coordinates.top-pending.offset);
    pending.attempt++;
    if(pending.attempt>=5){
      runtime.pendingTargetEdit=null;
      return;
    }
    const delays=[0,40,100,220];
    setTimeout(restorePendingTargetEdit,delays[pending.attempt-1]||220);
  }
  
  function setEditorMode(mode) {
    const source=mode.startsWith('source'), preview=mode.endsWith('preview');
    const editor=$(source?'#sourceEditorShell':'#targetEditorShell'), output=$(source?'#sourcePreview':'#targetPreview');
    if(preview)renderMarkdownEditors();
    editor.classList.toggle('editor-hidden',preview); output.classList.toggle('editor-hidden',!preview);
    $$(`[data-editor-mode^="${source?'source':'target'}-"]`).forEach(x=>x.classList.toggle('active',x.dataset.editorMode===mode));
    if(!preview)requestAnimationFrame(()=>{
      updateLineNumbers(source?'source':'target');
      if(!source)restorePendingTargetEdit();
    });
  }
  
  function updateLineNumbers(kind) {
    views[kind]?.refresh();
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
    const editor=views[kind], match=current.matches[current.index], start=match.index;
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
    const editor=views.target, query=$('#targetFind').value, replacement=$('#targetReplace').value;
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
    const editor=views.target;
    if($('#targetEditorShell').classList.contains('editor-hidden'))setEditorMode('target-text');
    const marker=type==='bold'?'**':'*';
    const placeholder=type==='bold'?'văn bản in đậm':'văn bản in nghiêng';
    const from=editor.getCursor('from');
    const to=editor.getCursor('to');
    const selected=editor.getRange(from,to);
    if(selected){
      const lines=selected.split('\n');
      const hasText=line=>line.trim().length>0;
      const wrapped=line=>hasText(line)&&line.startsWith(marker)&&line.endsWith(marker)&&line.length>=marker.length*2&&(marker==='**'||(!line.startsWith('**')&&!line.endsWith('**')));
      const removeMarkers=lines.some(hasText)&&lines.filter(hasText).every(wrapped);
      const replacement=lines.map(line=>{
        if(!hasText(line))return line;
        return removeMarkers?line.slice(marker.length,-marker.length):marker+line+marker;
      }).join('\n');
      const startIndex=editor.indexFromPos(from);
      editor.replaceRange(replacement,from,to,'+format');
      editor.setSelection(editor.posFromIndex(startIndex),editor.posFromIndex(startIndex+replacement.length));
    }else{
      const replacement=marker+placeholder+marker;
      editor.replaceRange(replacement,from,to,'+format');
      const start=editor.posFromIndex(editor.indexFromPos(from)+marker.length);
      const end=editor.posFromIndex(editor.indexFromPos(from)+marker.length+placeholder.length);
      editor.setSelection(start,end);
    }
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
    const editor=views.target, result=replaceDelimitedPairs(editor.getValue(),from,to);
    if(!result.count)return toast(`Không tìm thấy cặp ${from[1]}`);
    editor.setValue(result.text);
    toast(`Đã đổi ${result.count} cặp ${from[1]} thành ${to[1]}`);
  }
  
  
  function updateCounts() {
    const source=countText(editorValue('source'));
    const target=countText(editorValue('target'));
    $('#sourceCount').textContent = `${source.count.toLocaleString('vi-VN')} ${source.unit}`;
    $('#targetCount').textContent = `${target.count.toLocaleString('vi-VN')} ${target.unit}`;
  }
  function setSaveState(text) { $('#saveState span').textContent=text; }
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
    const fromEditor=event.currentTarget===views.source?.getWrapperElement();
    const text=(fromEditor?views.source.getSelection():String(getSelection()||'')).trim();
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
  
  
  function setWorkspaceMode(mode,remember=true){
    if(!['split','source','target'].includes(mode))mode='split';
    $$('[data-mode]').forEach(button=>button.classList.toggle('active',button.dataset.mode===mode));
    $('#editorGrid').className='editor-grid '+(mode==='split'?'':mode);
    if(remember&&window.matchMedia('(max-width:560px)').matches)localStorage.setItem('mobileWorkspaceMode',mode);
    requestAnimationFrame(()=>{
      views.source?.refresh();
      views.target?.refresh();
      updateLineNumbers('source');
      updateLineNumbers('target');
    });
  }

  function refreshEditors() {
    views.source?.refresh();views.target?.refresh();
  }

  function init() {
    initPunctuationOptions();
    initCodeEditors();
  }

  function bind() {
    $('#copyTargetPreview').onclick=copyTargetPreview;
    $('#punctuationToggle').onclick=event=>{event.stopPropagation();const popover=$('#punctuationPopover'),opening=!popover.classList.contains('open');popover.classList.toggle('open',opening);$('#punctuationToggle').setAttribute('aria-expanded',String(opening));if(opening)$('#punctuationFrom').focus();};
    $('#convertPunctuation').onclick=convertPunctuation;
    $('#targetPreview').ondblclick=editTargetPreviewLine;
    $('#sourcePreview').addEventListener('mouseup',translateRawSelection);
    $('#closeSelectionTranslation').onclick=closeSelectionTranslation;
    ['source','target'].forEach(kind=>{
      $('#'+kind+'Find').addEventListener('input',()=>{findState[kind].index=-1;refreshFind(kind);});
      $('#'+kind+'Find').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();selectFind(kind,event.shiftKey?-1:1);}if(event.key==='Escape')$('#'+kind+'FindBar').classList.remove('open');});
    });
    $('#targetReplace').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();replaceCurrent(false);}if(event.key==='Escape')$('#targetFindBar').classList.remove('open');});
    $$('[data-find-panel]').forEach(button=>button.onclick=()=>openFind(button.dataset.findPanel));
    $$('[data-find-option]').forEach(button=>button.onclick=()=>{const kind=button.dataset.findEditor,option=button.dataset.findOption,current=findState[kind];current[option]=!current[option];current.index=-1;button.classList.toggle('active',current[option]);button.setAttribute('aria-pressed',String(current[option]));refreshFind(kind);});
    $$('[data-find-action]').forEach(button=>button.onclick=()=>{const kind=button.dataset.findEditor,action=button.dataset.findAction;if(action==='next')selectFind(kind,1);if(action==='previous')selectFind(kind,-1);if(action==='close')$('#'+kind+'FindBar').classList.remove('open');if(action==='replace')replaceCurrent(false);if(action==='replace-all')replaceCurrent(true);});
    document.addEventListener('click',event=>{if(event.target.closest('#punctuationPopover'))return;$('#punctuationPopover').classList.remove('open');$('#punctuationToggle').setAttribute('aria-expanded','false');});
    $('#focusButton').onclick=()=>{document.body.classList.toggle('focus');$('#focusButton').textContent=document.body.classList.contains('focus')?'Thoát tập trung':'Tập trung';requestAnimationFrame(()=>{updateLineNumbers('source');updateLineNumbers('target');});};
    $$('[data-mode]').forEach(button=>button.onclick=()=>setWorkspaceMode(button.dataset.mode));
    $$('[data-editor-mode]').forEach(button=>button.onclick=()=>setEditorMode(button.dataset.editorMode));
    $$('[data-format]').forEach(button=>{
      button.onmousedown=event=>event.preventDefault();
      button.onclick=()=>applyFormat(button.dataset.format);
    });
  }

  function handleShortcut(event) {
    const typing=event.target instanceof HTMLElement&&(event.target.matches('input,textarea,select')||event.target.isContentEditable);
    if(!(event.ctrlKey||event.metaKey))return false;
    const key=event.key.toLowerCase();
    if(!['f','h'].includes(key))return false;
    const kind=views.source?.hasFocus()?'source':'target';
    event.preventDefault();openFind(kind,key==='h');return true;
  }

  return {bind,closeSelectionTranslation,handleShortcut,init,markdownToHtml,refreshEditors,refreshFind,renderMarkdownEditors,runtime,setEditorMode,setEditorValue,setSaveState,setWorkspaceMode,updateCounts,updateLineNumbers,value:editorValue,views};
}
