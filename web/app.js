import { api } from './api.js';
import { createAppShellFeature } from './features/app-shell.js';
import { createApiKeyFeature } from './features/api-keys.js';
import { createAiLogFeature } from './features/ai-logs.js';
import { createBookExportFeature } from './features/book-export.js';
import { createChapterImportFeature } from './features/chapter-import.js';
import { createEditorFeature } from './features/editor.js';
import { createHakoEditFeature } from './features/hako-edit.js';
import { createPipelineFeature } from './features/pipeline.js';
import { createPublishingBooksFeature } from './features/publishing-books.js';
import { createProjectMemoryFeature } from './features/project-memory.js';
import { createR19Feature } from './features/r19.js';
import { createSettingsFeature } from './features/settings.js';
import { createSharingFeature } from './features/sharing.js';
import { createUpdateFeature } from './features/updates.js';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = { projects: [], project: null, projectRevision: 0, chapters: [], reviews: [], context: {index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_json:''}, characters: {content:'',count:0,exists:false,backup:false}, pronouns: {pairs:[],count:0,locked_count:0,raw_json:''}, pronounCurrent: null, characterDirty: false, glossaryDirty: false, reviewCurrent: null, currentImages: [], current: null, dirty: false, timer: null };
const navigationCounts={chapters:0,characters:0,pronouns:0};
async function loadChapters() {
  if (!state.project) return;
  const project=state.project, revision=state.projectRevision;
  try {
    const data = await api('/api/chapters?project=' + encodeURIComponent(project));
    if(state.project!==project||state.projectRevision!==revision)return;
    state.chapters = data.items;
    navigationCounts.chapters=data.total; if($('#chapterBadge'))$('#chapterBadge').textContent=data.total;
    renderChapterList(); renderPopover();
    const currentItem=state.chapters.find(item=>item.name===state.current);
    if(currentItem)$('#currentChapter').textContent=currentItem.title||prettyName(currentItem.name);
    sharingFeature.render();
    updateChapterNavigation();
    if (!state.current && state.chapters.length) await openChapter(state.chapters.find(x => !x.translated)?.name || state.chapters[0].name,project,revision);
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
  state.reviews=[]; state.context={index:0,glossary:[],style_notes:'',prompt_preset:'default',prompt_role:'',prompt_task:'',prompt_presets:[],polish_prompt_preset:'default',polish_prompt_role:'',polish_prompt_task:'',polish_prompt_presets:[],raw_json:''};
  sharingFeature.render();
  renderContext();
  state.currentImages=[]; renderMarkdownEditors();
  $('#projectPopover').classList.remove('open');
  await loadChapters();
  toast('Đã mở ' + name);
  Promise.allSettled([loadReviews(), loadContext(), loadCharacters(), loadPronouns(), publishingBooksFeature.load(), sharingFeature.load(), r19Feature.load()]);
  if($('#aiLogDrawer').classList.contains('open'))aiLogFeature.load(true);
  $('#hakoPublicUrl').value=localStorage.getItem(`hako-public-url:${name}`)||'';
  hakoEditFeature.reset();
}

function escapeHtml(value){return String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));}

async function copyPlainText(text){
  try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);else{const input=document.createElement('textarea');input.value=text;document.body.appendChild(input);input.select();document.execCommand('copy');input.remove();}}
  catch(_error){toast('Không thể sao chép vào clipboard');}
}

let pipelineFeature;
const editorFeature=createEditorFeature({api,escapeHtml,positionPopover,saveChapter,state,toast});
const {markdownToHtml,refreshFind,renderMarkdownEditors,runtime:editorRuntime,setEditorValue,updateCounts,updateLineNumbers,value:editorValue,views:editorViews}=editorFeature;
const projectMemoryFeature=createProjectMemoryFeature({api,escapeHtml,executePipeline:(...args)=>pipelineFeature.execute(...args),markdownToHtml,navigationCounts,prettyName,saveChapter,state,toast});
const {loadCharacters,loadContext,loadPronouns,loadReviews,renderContext,renderWorkspaceReview,requireProject,saveCharacters,saveGlossaryChanges}=projectMemoryFeature;
const aiLogFeature=createAiLogFeature({api,copyPlainText,escapeHtml,getProject:()=>state.project,toast});
const apiKeyFeature=createApiKeyFeature({api,escapeHtml,toast});
const {open:openAiLog,close:closeAiLog}=aiLogFeature;
const appShellFeature=createAppShellFeature({api,escapeHtml,navigationCounts,openAiLog,refreshEditors:editorFeature.refreshEditors,showView,toast});
const r19Feature=createR19Feature({api,getProject:()=>state.project,showView,toast});
const bookExportFeature=createBookExportFeature({escapeHtml,getChapters:()=>state.chapters,getProject:()=>state.project,toast});
const chapterImportFeature=createChapterImportFeature({api,escapeHtml,getProject:()=>state.project,loadChapters,openChapter,toast});
const publishingBooksFeature=createPublishingBooksFeature({api,escapeHtml,getProject:()=>state.project,toast});
const hakoEditFeature=createHakoEditFeature({api,escapeHtml,getProject:()=>state.project,getTargets:()=>pipelineFeature.publishingTargets(),toast});
const updateFeature=createUpdateFeature({api,escapeHtml,hasUnsavedChanges:()=>state.dirty||state.characterDirty,toast});
const settingsFeature=createSettingsFeature({api,escapeHtml,refreshUpdate:updateFeature.load,showView,toast});
const sharingFeature=createSharingFeature({api,copyPlainText,escapeHtml,getChapters:()=>state.chapters,getProject:()=>state.project,openSettings:()=>settingsFeature.openGroup('sharing'),toast});
pipelineFeature=createPipelineFeature({api,editorRuntime,editorViews,escapeHtml,loadChapters,loadProjects,openChapter,projectMemoryFeature,publishingBooksFeature,saveChapter,selectProject,settingsFeature,showView,state,toast,updateCounts});

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
  const viewMeta=appShellFeature.getView(name);
  if(!viewMeta||!$('#' + name + 'View'))return;
  $$('.view').forEach(x => x.classList.remove('active'));
  $$('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  $('#' + name + 'View').classList.add('active');
  $('#viewEyebrow').textContent = viewMeta[0]; $('#viewTitle').textContent = viewMeta[1];
  $('#saveButton').style.display = name === 'workspace' ? '' : 'none';
  $('#retranslateButton').style.display = name === 'workspace' ? '' : 'none';
  $('#polishButton').style.display = name === 'workspace' ? '' : 'none';
  $('#sidebar').classList.remove('open');
  appShellFeature.renderNavigation();
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
    settingsFeature.openGroup(action==='gemini-settings'?'gemini-api':'publishing');
    return;
  }
  const group={translation:'translation',manual:'translation',quality:'quality',publishing:'publishing'}[action];
  if(!group)return;
  pipelineFeature.selectGroup(group);
  showView('pipeline');
  if(action==='manual')requestAnimationFrame(()=>document.querySelector('[data-run="manual"]')?.focus());
}

function prettyName(name) { const m=name.match(/c(\d+)/i); return m ? `Chương ${Number(m[1])} · ${name}` : name; }
function setSaveState(text) { $('#saveState span').textContent = text; }
function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('show'); clearTimeout(el._timer); el._timer=setTimeout(()=>el.classList.remove('show'),2400); }

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

document.addEventListener('click', (event) => {
  const featureAction=event.target.closest('[data-feature-action]');if(featureAction?.dataset.featureAction==='ai-log')openAiLog();
  const view=event.target.closest('[data-view]'); if(view) showView(view.dataset.view);
  const helpView=event.target.closest('[data-help-view]'); if(helpView) showView(helpView.dataset.helpView);
  const helpAction=event.target.closest('[data-help-action]'); if(helpAction) handleHelpAction(helpAction.dataset.helpAction);
  const chapter=event.target.closest('[data-chapter]'); if(chapter) openChapter(chapter.dataset.chapter);
  const project=event.target.closest('[data-project]'); if(project) selectProject(project.dataset.project);
  pipelineFeature.handleDocumentClick(event);
  if(projectMemoryFeature.handleDocumentClick(event))return;
  if(!event.target.closest('.popover,#chapterSelect,#projectSelect'))$$('.popover.open').forEach(item=>item.classList.remove('open'));
});
$('#chapterSelect').onclick = () => { togglePopover($('#chapterPopover'),$('#chapterSelect')); if($('#chapterPopover').classList.contains('open'))requestAnimationFrame(focusCurrentChapterInPopover); };
$('#previousChapter').onclick=()=>openAdjacentChapter(-1);
$('#nextChapter').onclick=()=>openAdjacentChapter(1);
$('#projectSelect').onclick = () => togglePopover($('#projectPopover'),$('#projectSelect'));
$('#addProjectButton').onclick=()=>$('#newProjectModal').classList.add('open');
$('#cancelNewProject').onclick=()=>$('#newProjectModal').classList.remove('open');
$('#confirmNewProject').onclick=createProject;
chapterImportFeature.bind();
$('#helpSearch').oninput=event=>filterHelp(event.target.value);
$$('[data-help-topic-button]').forEach(button=>button.onclick=()=>openHelpTopic(button.dataset.helpTopicButton));
$('#chapterSearch').oninput = e => renderChapterList(e.target.value);
bookExportFeature.bind();
sharingFeature.bind();
$('#popoverSearch').oninput = e => renderPopover(e.target.value);
projectMemoryFeature.bind();
editorFeature.bind();
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){
    editorFeature.closeSelectionTranslation();
    closeAiLog();
    if($('#whatsNewModal').classList.contains('open'))updateFeature.closeWhatsNew();
  }
  if(r19Feature.handleShortcut(event))return;
  editorFeature.handleShortcut(event);
});
$('#saveButton').onclick=saveChapter;
$('#polishButton').onclick=pipelineFeature.startPolish;
$('#retranslateButton').onclick=()=>{if(!state.current)return toast('Hãy chọn một chương trước');$('#retranslateChapter').textContent=prettyName(state.current)+' · Bản cũ sẽ được giữ nếu dịch lỗi.';$('#retranslateModal').classList.add('open');};
$('#cancelRetranslate').onclick=()=>$('#retranslateModal').classList.remove('open');
$('#confirmRetranslate').onclick=pipelineFeature.startRetranslate;
appShellFeature.bind();
aiLogFeature.bind();
r19Feature.bind();
pipelineFeature.bind();
$('#runCharacterAnalysis').onclick=()=>pipelineFeature.configureTask('characters');
$('#emptyRunCharacterAnalysis').onclick=()=>pipelineFeature.configureTask('characters');
settingsFeature.bind();
updateFeature.bind();
apiKeyFeature.bind();
publishingBooksFeature.bind();
hakoEditFeature.bind();
$('#openHakoSettings').onclick=()=>settingsFeature.openGroup('publishing');
window.addEventListener('beforeunload', e=>{if(state.dirty||state.characterDirty){e.preventDefault();e.returnValue='';}});
window.addEventListener('resize',()=>{repositionPopovers();updateLineNumbers('source');updateLineNumbers('target');});
window.addEventListener('scroll',repositionPopovers,true);
editorFeature.setEditorMode('source-text');
updateLineNumbers('source'); updateLineNumbers('target');
editorFeature.init();
editorFeature.setWorkspaceMode(window.matchMedia('(max-width:560px)').matches?(localStorage.getItem('mobileWorkspaceMode')||'target'):'split',false);
appShellFeature.load();appShellFeature.renderThemes();pipelineFeature.init();pipelineFeature.bootstrap();settingsFeature.load();apiKeyFeature.load();updateFeature.load().then(updateFeature.autoCheck);updateFeature.loadWhatsNew();settingsFeature.loadLanStatus();
