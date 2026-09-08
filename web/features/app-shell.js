const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

export function createAppShellFeature({api,escapeHtml,navigationCounts,openAiLog,refreshEditors,showView,toast}) {
  let pinnedFeatures=[];
  let editorSaveTimer=null;
  let editorPreferences={font:'system',size:17,line_height:1.75};
  const editorFonts={
    system:'"Segoe UI Variable Text","Segoe UI",Arial,sans-serif',
    georgia:'Georgia,"Times New Roman",serif',
    sans:'Arial,"Helvetica Neue",sans-serif',
    monospace:'Consolas,"Courier New",monospace',
    times:'"Times New Roman",Times,serif',
  };
  const appThemes=[
    {id:'quiet-light',name:'Quiet Light',description:'Sáng, nhẹ mắt',color:'#f5f5f5'},
    {id:'dark-modern',name:'Dark Modern',description:'Tối hiện đại',color:'#101412'},
    {id:'github-dark',name:'GitHub Theme',description:'Dark Default chính thức',color:'#0d1117'},
    {id:'one-dark-pro',name:'One Dark Pro',description:'Atom cổ điển',color:'#282c34'},
    {id:'synthwave-84',name:"SynthWave '84",description:'Neon hoài cổ',color:'#21182d'},
    {id:'solarized-dark',name:'Solarized Dark',description:'Tương phản dịu',color:'#002b36'},
    {id:'monokai-dimmed',name:'Monokai Dimmed',description:'Ấm và tập trung',color:'#1e1f1c'},
    {id:'sakura-night',name:'Sakura Night',description:'Anime đêm hoa anh đào',color:'#101625'},
    {id:'tokyo-night',name:'Tokyo Night',description:'Xanh tím Tokyo',color:'#1a1b26'},
    {id:'abyss',name:'Abyss',description:'Xanh vực sâu',color:'#000c18'},
    {id:'kimbie-dark',name:'Kimbie Dark',description:'Nâu hổ phách',color:'#221a0f'},
    {id:'everforest-dark-medium',name:'Everforest Dark Medium',description:'Rừng xanh dịu mắt',color:'#2d353b'},
    {id:'night-owl',name:'Night Owl',description:'Xanh đêm sắc nét',color:'#011627'},
    {id:'catppuccin-mocha',name:'Catppuccin Mocha',description:'Mocha tím pastel',color:'#1e1e2e'},
    {id:'aiko-anime',name:'Aiko Midnight',description:'Midnight Slate',color:'#0f1218'},
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
    try{const data=await api('/api/ui-preferences');pinnedFeatures=(data.sidebar?.pinned||defaultPinnedFeatures).filter(id=>!fixedSidebarFeatures.has(id));editorPreferences={...editorPreferences,...(data.editor||{})};}
    catch(error){pinnedFeatures=[...defaultPinnedFeatures];toast(error.message);}
    renderPinnedNavigation();applyEditorPreferences();
  }
  async function saveUiPreferences(){
    $('#featureSaveStatus').textContent='Đang lưu…';
    if($('#editorAppearanceStatus'))$('#editorAppearanceStatus').textContent='Đang lưu…';
    try{const data=await api('/api/ui-preferences',{method:'POST',body:JSON.stringify({sidebar:{pinned:pinnedFeatures},editor:editorPreferences})});editorPreferences=data.editor||editorPreferences;renderPinnedNavigation();applyEditorPreferences();$('#featureSaveStatus').textContent='Đã lưu';if($('#editorAppearanceStatus'))$('#editorAppearanceStatus').textContent='Đã lưu';}
    catch(error){$('#featureSaveStatus').textContent='Lỗi lưu';if($('#editorAppearanceStatus'))$('#editorAppearanceStatus').textContent='Lỗi lưu';toast(error.message);}
  }

  function ensureEditorAppearanceControls(){
    if($('#editorAppearance'))return;
    const row=$('#workspaceSettings .setting-row');
    row?.insertAdjacentHTML('beforebegin','<section class="editor-appearance" id="editorAppearance"><div><strong>Trình soạn thảo</strong><small>Áp dụng cho nội dung soạn thảo và bản xem trước.</small></div><div class="editor-appearance-controls"><label><span>Kiểu chữ</span><select id="editorFont"><option value="system">Mặc định</option><option value="georgia">Georgia</option><option value="sans">Sans-serif</option><option value="monospace">Monospace</option><option value="times">Times New Roman</option></select></label><label><span>Cỡ chữ <output id="editorFontSizeValue">17 px</output></span><input id="editorFontSize" type="range" min="14" max="24" step="1" value="17"></label><label><span>Giãn dòng <output id="editorLineHeightValue">1.75</output></span><input id="editorLineHeight" type="range" min="1.4" max="2.2" step="0.05" value="1.75"></label></div><small id="editorAppearanceStatus">Đã lưu</small></section>');
  }

  function ensureAnimeIllustrationControl(){
    const themeSetting=$('#workspaceSettings .theme-setting');
    if(!$('#animeIllustrationSetting'))themeSetting?.insertAdjacentHTML('afterend','<section class="anime-illustration-setting" id="animeIllustrationSetting"><span><strong>Minh họa Aiko</strong><small>Bật mascot, icon và mũi tên anime. Khi tắt, giao diện dùng biểu tượng mặc định.</small></span><label class="switch"><input id="animeIllustrations" type="checkbox"><i></i></label></section>');
    if(!$('#brushCursorSetting'))$('#animeIllustrationSetting')?.insertAdjacentHTML('afterend','<section class="anime-illustration-setting" id="brushCursorSetting"><span><strong>Con trỏ bút lông</strong><small>Đổi con trỏ chuột trên vùng soạn thảo; caret và thao tác bôi đen vẫn giữ nguyên.</small></span><label class="switch"><input id="brushCursor" type="checkbox"><i></i></label></section>');
  }

  function applyAnimeIllustrationPreference(){
    const enabled=localStorage.getItem('novel-anime-illustrations')==='on';
    document.documentElement.dataset.animeIllustrations=enabled?'on':'off';
    if($('#animeIllustrations'))$('#animeIllustrations').checked=enabled;
  }

  function applyBrushCursorPreference(){
    const enabled=localStorage.getItem('novel-brush-cursor')!=='off';
    document.documentElement.dataset.brushCursor=enabled?'on':'off';
    if($('#brushCursor'))$('#brushCursor').checked=enabled;
  }

  function applyEditorPreferences(){
    ensureEditorAppearanceControls();
    const font=editorFonts[editorPreferences.font]?editorPreferences.font:'system';
    const size=Math.max(14,Math.min(24,Number(editorPreferences.size)||17));
    const lineHeight=Math.max(1.4,Math.min(2.2,Number(editorPreferences.line_height)||1.75));
    editorPreferences={font,size,line_height:Number(lineHeight.toFixed(2))};
    document.documentElement.style.setProperty('--editor-font-family',editorFonts[font]);
    document.documentElement.style.setProperty('--editor-font-size',size+'px');
    document.documentElement.style.setProperty('--editor-line-height-ratio',String(editorPreferences.line_height));
    document.documentElement.style.setProperty('--editor-computed-line-height',(size*editorPreferences.line_height).toFixed(2)+'px');
    $('#editorFont').value=font;$('#editorFontSize').value=String(size);$('#editorLineHeight').value=String(editorPreferences.line_height);
    $('#editorFontSizeValue').textContent=size+' px';$('#editorLineHeightValue').textContent=editorPreferences.line_height.toFixed(2);
    requestAnimationFrame(()=>refreshEditors());
  }

  function changeEditorAppearance(){
    editorPreferences={font:$('#editorFont').value,size:Number($('#editorFontSize').value),line_height:Number($('#editorLineHeight').value)};
    applyEditorPreferences();
    $('#editorAppearanceStatus').textContent='Chưa lưu';
    clearTimeout(editorSaveTimer);editorSaveTimer=setTimeout(saveUiPreferences,350);
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
      return `<div class="feature-row" ${canReorder?`draggable="true" data-feature-drag="${item.id}"`:''}>${canReorder?'<span class="feature-drag-handle" aria-hidden="true"><span class="ui-icon ui-icon-grip" aria-hidden="true"></span></span>':'<span class="feature-drag-spacer"></span>'}<span class="feature-row-icon" data-feature-icon="${item.id}">${escapeHtml(item.icon)}</span><button class="feature-row-copy" type="button" data-feature-open="${item.id}"><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.description+note)}</small></button><span class="feature-row-actions">${isFixed?'<span class="feature-fixed-label">Luôn hiển thị</span>':`<button class="pin ${isPinned?'active':''}" data-feature-pin="${item.id}">${isPinned?'Gỡ':'Ghim'}</button>`}</span></div>`;
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
  
  function renderThemeOptions() {
    const current=document.documentElement.dataset.theme||'aiko-anime';
    $('#themeOptions').innerHTML=appThemes.map(theme=>`<button class="theme-option ${theme.id===current?'active':''}" type="button" data-theme-option="${theme.id}" aria-pressed="${theme.id===current}"><span class="theme-swatch" aria-hidden="true"></span><span><strong>${theme.name}</strong><small>${theme.description}</small></span></button>`).join('');
    $$('[data-theme-option]').forEach(button=>button.onclick=()=>applyTheme(button.dataset.themeOption));
  }
  
  function applyTheme(themeId) {
    const theme=appThemes.find(item=>item.id===themeId)||appThemes[1];
    document.documentElement.dataset.theme=theme.id;
    localStorage.setItem('novel-theme',theme.id);
    $('#themeColor').setAttribute('content',theme.color);
    renderThemeOptions();
    requestAnimationFrame(()=>refreshEditors());
  }
  
  
  function getView(name) { return views[name]; }

  function bind() {
    ensureAnimeIllustrationControl();
    applyAnimeIllustrationPreference();
    applyBrushCursorPreference();
    ensureEditorAppearanceControls();
    $('#animeIllustrations').onchange=event=>{const enabled=event.target.checked;localStorage.setItem('novel-anime-illustrations',enabled?'on':'off');applyAnimeIllustrationPreference();};
    $('#brushCursor').onchange=event=>{const enabled=event.target.checked;localStorage.setItem('novel-brush-cursor',enabled?'on':'off');applyBrushCursorPreference();};
    $('#editorFont').onchange=changeEditorAppearance;
    $('#editorFontSize').oninput=changeEditorAppearance;
    $('#editorLineHeight').oninput=changeEditorAppearance;
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
  }

  return {bind,getView,load:loadUiPreferences,renderNavigation:renderPinnedNavigation,renderThemes:renderThemeOptions};
}
