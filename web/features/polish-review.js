import {inlineDiff,highlightedText,reviewHunks} from './polish-diff.js';
const $=selector=>document.querySelector(selector);

// Migrate sessions created by the earlier paragraph-based review UI.
export function reviewedText(review,values) {
  return values.map((value,index)=>{
    const block=review.blocks[index];
    if(value&&value!==block.old&&value!==block.new){
      const suffix=(block.new||block.old).match(/\n[ \t\n]*$/)?.[0];
      if(suffix&&!value.endsWith(suffix))return value.replace(/\n+$/,'')+suffix;
    }
    return value;
  }).join('');
}

export function createPolishReviewFeature({api,state,toast,escapeHtml,reload,editorFeature}) {
  let session=null,timer=null,paintTimer=null,frozen=0;
  const target=$('.target-panel'),panel=document.createElement('section');
  panel.id='polishReview';panel.className='polish-review';panel.hidden=true;
  panel.setAttribute('aria-label','Duyệt hiệu đính trong trình soạn thảo');
  target.insertBefore(panel,$('#targetEditorShell'));
  function menu(items,label) {
    return `<details class="polish-menu"><summary aria-label="${label}" title="${label}"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg></summary><div>${items}</div></details>`;
  }
  const status=message=>{const node=panel.querySelector('[data-review-status]');if(node)node.textContent=message;};
  const recovery=()=>{const node=panel.querySelector('[data-review-recovery]');if(node)node.hidden=false;};
  function controls() {
    if(!session)return;
    const s=session,locked=Boolean(frozen||s.busy);
    s.editor.setOption('readOnly',locked||s.readOnly);
    target.querySelectorAll('[data-review-action]').forEach(node=>node.disabled=locked);
    panel.querySelector('[data-review-action="undo"]').disabled=locked||!s.editor.historySize().undo;
    panel.querySelector('[data-review-action="previous-change"]').disabled=locked||s.active<=0;
    panel.querySelector('[data-review-action="next-change"]').disabled=locked||s.active>=s.hunks.length-1;
    panel.querySelector('[data-change-position]').textContent=`${s.hunks.length?s.active+1:0} / ${s.hunks.length}`;
    $('#saveButton').disabled=locked;
  }
  function clearDecorations(s) {
    s.marks.forEach(mark=>mark.clear());s.marks=[];
    s.widgets.forEach(widget=>widget.clear());s.widgets=[];
    s.lines.forEach(line=>s.editor.removeLineClass(line,'background','polish-added-line'));s.lines=[];
    s.editor.clearGutter('polish-diff-gutter');
  }
  function renderDiff() {
    clearTimeout(paintTimer);
    const s=session;if(!s)return;
    const editor=s.editor,scroll=editor.getScrollInfo();
    s.hunks=reviewHunks(s.review.original,s.text,s.review.proposed);
    s.active=Math.min(Math.max(0,s.active),Math.max(0,s.hunks.length-1));
    editor.operation(()=>{
      clearDecorations(s);
      s.hunks.forEach((hunk,index)=>{
        const pos=editor.posFromIndex(hunk.from),diff=inlineDiff(hunk.old,hunk.value);
        const widget=document.createElement('div');
        widget.className='polish-inline-hunk';widget.dataset.hunk=String(index);widget.dataset.original=String(hunk.oldFrom);
        const hasOldRow=Boolean(hunk.old&&hunk.old!==hunk.value);
        const actions='<button type="button" data-review-action="old">Dùng lại bản cũ</button><button type="button" data-review-action="ai">Khôi phục đề xuất AI</button>';
        const label=`Thao tác thay đổi ${index+1}`;
        widget.innerHTML=hasOldRow
          ? `<details class="polish-menu"><summary class="polish-inline-old" title="${label}"><span class="polish-old-sign" aria-hidden="true">−</span><span>${highlightedText(hunk.old,diff.removed,'polish-diff-removed',escapeHtml)}</span></summary><div>${actions}</div></details>`
          : menu(actions,label);
        s.widgets.push(editor.addLineWidget(pos.line,widget,{above:pos.ch===0,coverGutter:false,noHScroll:false,handleMouseEvents:false}));
        if(hunk.value!==hunk.old&&hunk.value){
          const end=editor.posFromIndex(hunk.to),last=end.ch===0?end.line-1:end.line;
          for(let line=pos.line;line<=last;line++){
            s.lines.push(editor.addLineClass(line,'background','polish-added-line'));
            const marker=document.createElement('span');marker.className='polish-gutter-plus';marker.textContent='+';marker.setAttribute('aria-hidden','true');
            editor.setGutterMarker(line,'polish-diff-gutter',marker);
          }
          for(const range of diff.added)s.marks.push(editor.markText(editor.posFromIndex(hunk.from+range.from),editor.posFromIndex(hunk.from+range.to),{className:'polish-diff-added'}));
        }
      });
    });
    editor.scrollTo(scroll.left,scroll.top);controls();
  }
  function onChange(editor) {
    const s=session;if(!s||editorFeature.runtime.syncing)return;
    s.text=editor.getValue();s.dirty=true;status('Chưa lưu tiến độ duyệt');
    clearTimeout(timer);timer=setTimeout(()=>flush(),800);
    clearTimeout(paintTimer);paintTimer=setTimeout(renderDiff,120);controls();
  }
  function beforeChange(_editor,change) {
    if(session&&(frozen||session.busy)&&!editorFeature.runtime.syncing)change.cancel();
  }
  function onCursor(editor) {
    if(!session||editorFeature.runtime.syncing)return;
    const offset=editor.indexFromPos(editor.getCursor());
    const index=session.hunks.findIndex(hunk=>offset>=hunk.from&&offset<=hunk.to);
    if(index>=0){session.active=index;controls();}
  }
  function detach() {
    if(!session)return;
    const s=session;
    s.editor.off('change',onChange);s.editor.off('beforeChange',beforeChange);s.editor.off('cursorActivity',onCursor);
    s.editor.operation(()=>clearDecorations(s));
    s.editor.setOption('gutters',s.gutters);s.editor.setOption('readOnly',s.readOnly);
  }
  function open(review) {
    clearTimeout(timer);clearTimeout(paintTimer);detach();session=null;
    state.polishReview=Boolean(review);state.dirty=false;
    target.classList.toggle('reviewing-polish',Boolean(review));panel.hidden=!review;
    $('#saveButton').textContent=review?'Lưu bản đang duyệt':'Lưu bản dịch';
    $('#retranslateButton').disabled=Boolean(review);
    if(!review){panel.replaceChildren();return;}
    const editor=editorFeature.views.target,text=review.draft_text??reviewedText(review,review.values);
    session={review,text,editor,project:state.project,chapter:state.current,dirty:false,pending:null,busy:false,hunks:[],active:0,marks:[],widgets:[],lines:[],gutters:[...editor.getOption('gutters')],readOnly:editor.getOption('readOnly')};
    panel.innerHTML=`<div class="polish-review-toolbar"><strong>Hiệu đính</strong><span data-change-position role="status" aria-live="polite"></span><button type="button" class="secondary" data-review-action="previous-change" aria-label="Thay đổi trước">Trước</button><button type="button" class="secondary" data-review-action="next-change" aria-label="Thay đổi sau">Sau</button><button type="button" class="secondary" data-review-action="undo">Hoàn tác</button>${menu('<button type="button" data-review-action="discard">Bỏ toàn bộ hiệu đính</button>','Thao tác cả chương')}</div><div class="polish-review-status" data-review-status role="status">Đỏ: bản cũ · Xanh: bản mới · Tiến độ tự lưu riêng</div><div class="polish-review-recovery" data-review-recovery hidden><p>Giữ lại nội dung bạn đã sửa trước khi tải phiên mới nhất.</p><button type="button" class="secondary" data-review-action="copy">Sao chép bản đang duyệt</button><button type="button" class="secondary" data-review-action="reload">Tải lại phiên duyệt</button></div>`;
    editorFeature.setEditorValue('target',text);editorFeature.setEditorMode('target-text');
    editor.setOption('gutters',[...session.gutters,'polish-diff-gutter']);
    editor.on('change',onChange);editor.on('beforeChange',beforeChange);editor.on('cursorActivity',onCursor);
    renderDiff();editorFeature.updateCounts();editorFeature.refreshFind('target');
    requestAnimationFrame(()=>{if(session?.editor===editor)editor.refresh();});
  }
  function freeze() {
    frozen++;controls();$('#saveButton').disabled=true;
    return ()=>{frozen=Math.max(0,frozen-1);if(session)controls();else if(!frozen)$('#saveButton').disabled=false;};
  }
  async function flush() {
    clearTimeout(timer);const s=session;if(!s)return true;
    if(s.pending){if(!await s.pending)return false;return session===s?flush():true;}
    if(!s.dirty)return true;
    const text=s.text;status('Đang lưu tiến độ…');
    s.pending=(async()=>{
      try{
        const result=await api(`/api/polish-review/${encodeURIComponent(s.chapter)}?project=${encodeURIComponent(s.project)}`,{method:'POST',body:JSON.stringify({action:'draft',id:s.review.id,revision:s.review.revision,draft_text:text})});
        s.review.revision=result.revision;s.dirty=s.text!==text;
        if(session===s)status(s.dirty?'Chưa lưu thay đổi mới':'Tiến độ đã lưu · Bản dịch gốc chưa thay đổi');
        return true;
      }catch(error){if(session===s){status('Chưa lưu được tiến độ · Thử lại hoặc tải lại phiên duyệt');recovery();toast(error.message);}return false;}
      finally{s.pending=null;}
    })();
    const ok=await s.pending;return ok&&session===s&&s.dirty?flush():ok;
  }
  async function finish(action) {
    const s=session;if(!s||s.busy||frozen)return;
    if(action==='discard'&&!window.confirm(s.text!==s.review.proposed?'Bỏ toàn bộ hiệu đính và các chỉnh sửa trong phiên này?':'Bỏ toàn bộ hiệu đính và giữ nguyên bản dịch hiện tại?'))return;
    s.busy=true;controls();
    try{
      if(!await flush())return;
      const result=await api(`/api/polish-review/${encodeURIComponent(s.chapter)}?project=${encodeURIComponent(s.project)}`,{method:'POST',body:JSON.stringify({action,id:s.review.id,revision:s.review.revision,draft_text:s.text})});
      if(session!==s)return;
      applyLiveText(result.translated);
      open(null);await reload(s.chapter,s.project);
      toast(action==='accept'?'Đã lưu bản đang duyệt':'Đã bỏ hiệu đính; bản dịch được giữ nguyên');
    }catch(error){if(session===s){recovery();toast(error.message);}}
    finally{s.busy=false;if(session===s)controls();else $('#saveButton').disabled=Boolean(frozen);}
  }
  function applyLiveText(text) {
    if(typeof text!=='string')throw new Error('Chưa tải được bản dịch đã lưu. Hãy tải lại phiên duyệt trước khi tiếp tục.');
    editorFeature.setEditorValue('target',text);
    editorFeature.updateCounts();editorFeature.refreshFind('target');editorFeature.renderMarkdownEditors();
  }
  async function recover() {
    if(!window.confirm('Tải lại phiên duyệt mới nhất? Những chỉnh sửa chưa lưu ở cửa sổ này sẽ bị bỏ. Hãy sao chép nội dung cần giữ trước.'))return;
    const s=session,release=freeze();clearTimeout(timer);
    try{
      if(s.pending)await s.pending;
      const chapter=await api(`/api/chapter/${encodeURIComponent(s.chapter)}?project=${encodeURIComponent(s.project)}`);
      if(session===s){
        if(!chapter.polish_review)applyLiveText(chapter.translated);
        open(chapter.polish_review||null);
        if(!chapter.polish_review)await reload(s.chapter,s.project);
      }
    }catch(error){toast(error.message);}finally{release();}
  }
  target.addEventListener('click',event=>{
    const row=event.target.closest('summary.polish-inline-old');
    if(row){
      event.preventDefault();
      const details=row.parentElement;
      details.open=!details.open;
      if(details.open){
        const popup=details.lastElementChild;
        const bounds=details.getBoundingClientRect();
        const editorBounds=session.editor.getWrapperElement().getBoundingClientRect();
        const x=event.detail?event.clientX:row.getBoundingClientRect().left;
        const y=event.detail?event.clientY:Math.max(bounds.top,editorBounds.top);
        const left=Math.max(0,editorBounds.left),right=Math.min(innerWidth,editorBounds.right);
        const top=Math.max(0,editorBounds.top),bottom=Math.min(innerHeight,editorBounds.bottom);
        popup.style.left=(Math.max(left,Math.min(x,right-popup.offsetWidth))-bounds.left)+'px';
        popup.style.right='auto';
        popup.style.top=(Math.max(top,y+popup.offsetHeight+4<=bottom?y+4:y-popup.offsetHeight-4)-bounds.top)+'px';
      }
      return;
    }
    const button=event.target.closest('[data-review-action]');if(!button||!session||session.busy||frozen)return;
    const action=button.dataset.reviewAction;button.closest('details')?.removeAttribute('open');
    if(action==='accept'||action==='discard'){finish(action);return;}
    if(action==='reload'){recover();return;}
    if(action==='copy'){
      Promise.resolve().then(()=>navigator.clipboard.writeText(session.text)).then(()=>toast('Đã sao chép bản đang duyệt'),()=>toast('Không thể sao chép. Hãy chọn nội dung trong trình soạn thảo để sao chép.'));return;
    }
    const s=session,editor=s.editor;
    if(action==='undo'){editor.undo();renderDiff();editor.focus();return;}
    if(action==='previous-change'||action==='next-change'){
      renderDiff();s.active=Math.max(0,Math.min(s.hunks.length-1,s.active+(action==='next-change'?1:-1)));
      const hunk=s.hunks[s.active];if(!hunk)return;
      const pos=editor.posFromIndex(hunk.from);editor.setCursor(pos);editor.scrollIntoView(pos,80);editor.focus();
      const widget=s.widgets[s.active]?.node;
      if(widget){const scroll=editor.getScrollInfo();const top=widget.getBoundingClientRect().top-editor.getScrollerElement().getBoundingClientRect().top;editor.scrollTo(scroll.left,Math.max(0,scroll.top+top-16));}
      controls();return;
    }
    if(action==='old'||action==='ai'){
      const original=Number(button.closest('[data-hunk]').dataset.original);renderDiff();
      const hunk=s.hunks.find(item=>original>=item.oldFrom&&original<=item.oldTo);if(!hunk)return;
      editor.replaceRange(action==='old'?hunk.old:hunk.ai,editor.posFromIndex(hunk.from),editor.posFromIndex(hunk.to),'review-restore');renderDiff();editor.focus();
    }
  });
  document.addEventListener('click',event=>target.querySelectorAll('.polish-menu[open]').forEach(node=>{if(!node.contains(event.target))node.open=false;}));
  target.addEventListener('keydown',event=>{if(event.key==='Escape'){const detail=event.target.closest('.polish-menu');if(detail){detail.open=false;detail.querySelector('summary').focus();}}});
  window.addEventListener('beforeunload',event=>{if(session?.dirty||session?.pending){event.preventDefault();event.returnValue='';}});
  return {open,flush,freeze,accept:()=>finish('accept'),get active(){return Boolean(session);},get busy(){return Boolean(session?.busy);}};
}
