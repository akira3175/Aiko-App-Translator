const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];

const CHAPTER_ID_RE=/^v\d+_c\d+_s\d+(?:\.md)?$/i;

const FIELD_GROUPS=[
  {
    title:'Thông tin nền & nhận diện',
    hint:'Vẫn hỗ trợ gắn mốc chương nếu tên, tuổi hay xuất thân được tiết lộ hoặc thay đổi về sau.',
    keys:['original_name','aliases','gender','age','origin'],
  },
  {
    title:'Vai trò & trạng thái theo chương',
    hint:'Thêm mốc mới thay vì xóa giá trị cũ để AI dựng đúng trạng thái cho từng chương.',
    keys:['status','faction','special_state'],
  },
  {
    title:'Giọng điệu & xưng hô nền',
    hint:'Khóa (🔒) những mục bạn đã xác nhận để AI không tự ghi đè khi phân tích lại.',
    keys:['voice','narration_pronoun','self_reference','address'],
  },
];

const DEFAULT_FIELDS=[
  {key:'original_name',label:'Tên gốc'},
  {key:'aliases',label:'Biệt danh / Danh hiệu'},
  {key:'gender',label:'Giới tính'},
  {key:'age',label:'Tuổi / Độ tuổi'},
  {key:'origin',label:'Chủng tộc / Xuất thân'},
  {key:'status',label:'Địa vị / Chức vụ'},
  {key:'faction',label:'Phe / Tổ chức'},
  {key:'special_state',label:'Trạng thái đặc biệt (cơ thể / thân phận)'},
  {key:'voice',label:'Giọng điệu / Khẩu khí'},
  {key:'narration_pronoun',label:'Đại từ dẫn truyện (ngôi thứ ba)'},
  {key:'self_reference',label:'Tự xưng thường dùng'},
  {key:'address',label:'Xưng hô với nhân vật quan trọng'},
];

const MULTILINE_FIELDS=new Set(['special_state','address']);

const FIELD_PLACEHOLDERS={
  original_name:'Ví dụ: 林峰 / Lin Feng',
  aliases:'Ví dụ: Kiếm Tôn, Hắc Y Nhân',
  gender:'Nam / Nữ / Không xác định',
  age:'Ví dụ: ~18 tuổi',
  origin:'Ví dụ: Nhân tộc, xuất thân gia tộc nhỏ',
  status:'Ví dụ: Đệ tử ngoại môn → Trưởng lão',
  faction:'Ví dụ: Thanh Vân Tông',
  special_state:'Ví dụ: Bị phong ấn tu vi, giả trang nam, chuyển sinh…',
  voice:'Ví dụ: Lạnh lùng, nói ngắn, hay mỉa mai nhẹ',
  narration_pronoun:'Ví dụ: hắn / anh / cậu / cô / nàng',
  self_reference:'Ví dụ: ta, bản tọa, tại hạ…',
  address:'Ví dụ: Sư phụ → tự xưng "đồ nhi", gọi "sư tôn"',
};

function makeLocalId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2,10)}${Date.now().toString(36).slice(-4)}`;
}

function cloneCharacters(list) {
  return (Array.isArray(list)?list:[]).map(character=>({
    id:String(character?.id||makeLocalId('ch')),
    name:String(character?.name||''),
    fields:Object.fromEntries(
      Object.entries(character?.fields||{}).map(([key,entries])=>[
        key,
        (Array.isArray(entries)?entries:[]).map(entry=>({
          id:String(entry?.id||makeLocalId('e')),
          value:String(entry?.value||''),
          chapter:entry?.chapter?String(entry.chapter):'',
          confirmed:Boolean(entry?.confirmed),
          source:String(entry?.source||'user'),
        })),
      ]),
    ),
    notes:(Array.isArray(character?.notes)?character.notes:[]).map(note=>({
      id:String(note?.id||makeLocalId('e')),
      text:String(note?.text||''),
      chapter:note?.chapter?String(note.chapter):'',
      confirmed:Boolean(note?.confirmed),
      source:String(note?.source||'user'),
    })),
    unclassified:String(character?.unclassified||''),
  }));
}

function normalizeChapterInput(value) {
  const text=String(value||'').trim();
  if(!text)return '';
  const match=text.match(/^v(\d+)_c(\d+)_s(\d+)(?:\.md)?$/i);
  if(!match)return null;
  return `v${Number(match[1])}_c${Number(match[2])}_s${Number(match[3])}.md`;
}

function sourceLabel(source) {
  if(source==='ai')return 'AI';
  if(source==='legacy')return 'Cũ';
  return 'Thủ công';
}

function characterSummary(character) {
  const fields=character.fields||{};
  const parts=[];
  const original=(fields.original_name||[])[0]?.value;
  if(original)parts.push(original);
  const statusList=fields.status||[];
  const factionList=fields.faction||[];
  const latestStatus=statusList[statusList.length-1]?.value;
  const latestFaction=factionList[factionList.length-1]?.value;
  if(latestStatus)parts.push(latestStatus);
  else if(latestFaction)parts.push(latestFaction);
  let dated=0;
  let confirmed=0;
  for(const entries of Object.values(fields)){
    for(const entry of entries||[]){
      if(entry.chapter)dated++;
      if(entry.confirmed)confirmed++;
    }
  }
  for(const note of character.notes||[]){
    if(note.chapter)dated++;
    if(note.confirmed)confirmed++;
  }
  return {
    subtitle:parts.join(' · ')||(dated?`${dated} mốc theo chương`:'Chưa có thông tin chi tiết'),
    dated,
    confirmed,
    hasUnclassified:Boolean(String(character.unclassified||'').trim()),
  };
}

export function createCharactersFeature({
  api,
  copyPlainText,
  escapeHtml,
  markdownToHtml,
  navigationCounts,
  requireProject,
  state,
  toast,
}) {
  let selectedId=null;
  let profileMode='list';
  let listScroll=0;
  let snapshotMode='rendered';
  let snapshotMarkdown='';
  let snapshotRevision=0;

  function ensureStore() {
    if(!state.characters||typeof state.characters!=='object'){
      state.characters={revision:0,characters:[],fields:DEFAULT_FIELDS,chapters:[],content:'',exists:false,count:0,backup:false,legacy_backup:false};
    }
    if(!Array.isArray(state.characters.characters))state.characters.characters=[];
    if(!Array.isArray(state.characters.fields)||!state.characters.fields.length)state.characters.fields=DEFAULT_FIELDS;
    if(!Array.isArray(state.characters.chapters))state.characters.chapters=[];
    return state.characters;
  }

  function fieldLabel(key) {
    const found=(ensureStore().fields||DEFAULT_FIELDS).find(item=>item.key===key);
    return found?found.label:key;
  }

  function availableChapters() {
    const store=ensureStore();
    if(store.chapters.length)return store.chapters;
    return (state.chapters||[]).map(chapter=>chapter.name).filter(Boolean);
  }

  function currentCharacter() {
    const list=ensureStore().characters;
    return list.find(item=>item.id===selectedId)||null;
  }

  function markDirty() {
    state.characterDirty=true;
    updateFooterAndBadges();
  }

  function renderChapterDatalist() {
    const datalist=$('#characterChapterOptions');
    if(!datalist)return;
    const chapters=availableChapters();
    datalist.innerHTML=chapters.map(name=>`<option value="${escapeHtml(name)}"></option>`).join('');
  }

  function updateFooterAndBadges() {
    const store=ensureStore();
    const total=store.characters.length;
    if($('#saveCharacters'))$('#saveCharacters').textContent=state.characterDirty?'Lưu thay đổi •':'Lưu hồ sơ';
    navigationCounts.characters=total;
    if($('#characterBadge'))$('#characterBadge').textContent=total;

    const saveState=$('#characterSaveState');
    if(saveState){
      const parts=[];
      if(store.recovery_required)parts.push('Hồ sơ bị lỗi. Hãy khôi phục từ bản sao .bak.');
      else if(state.characterDirty)parts.push('Có thay đổi chưa lưu');
      else if(!store.exists&&!total)parts.push('Chưa có dữ liệu');
      else parts.push(`Đã lưu · Rev ${store.revision||0}`);
      if(store.backup)parts.push('Có backup .bak');
      if(store.legacy_backup)parts.push('Đã giữ characters.legacy.md');
      saveState.textContent=parts.join(' · ');
    }
    const restoreButton=$('#restoreCharactersBackup');
    if(restoreButton){
      restoreButton.hidden=!store.backup;
      restoreButton.disabled=!store.backup;
    }
    const recovery=Boolean(store.recovery_required);
    for(const selector of ['#addCharacterButton','#saveCharacters','#openCharacterSnapshot','#openCharacterMarkdown']){
      const button=$(selector);
      if(button)button.disabled=recovery;
    }
  }

  function characterMatchesQuery(character, query) {
    if(!query)return true;
    const bag=[character.name,character.unclassified||''];
    for(const entries of Object.values(character.fields||{})){
      for(const entry of entries||[])bag.push(entry.value||'',entry.chapter||'');
    }
    for(const note of character.notes||[])bag.push(note.text||'',note.chapter||'');
    return bag.join(' ').toLocaleLowerCase('vi').includes(query);
  }

  function renderCharacterList() {
    const store=ensureStore();
    const query=($('#characterSearch')?.value||'').trim().toLocaleLowerCase('vi');
    const filter=$('#characterFilter')?.value;
    const items=store.characters.filter(character=>characterMatchesQuery(character,query)
      && (!filter || (filter==='locked'?characterSummary(character).confirmed:character.unclassified?.trim())));
    if($('#characterCount'))$('#characterCount').textContent=`${items.length}/${store.characters.length} nhân vật`;
    const listEl=$('#characterList');
    if(!listEl)return;
    if(!items.length){
      listEl.innerHTML='<div class="character-list-empty">Không có nhân vật phù hợp.</div>';
      return;
    }
    listEl.innerHTML=items.map(character=>{
      const meta=characterSummary(character);
      const chips=[];
      if(meta.dated)chips.push(`<i class="character-chip">${meta.dated} mốc</i>`);
      if(meta.confirmed)chips.push(`<i class="character-chip locked">🔒 ${meta.confirmed}</i>`);
      if(meta.hasUnclassified)chips.push('<i class="character-chip warn">Chưa phân loại</i>');
      return `<button type="button" class="character-row ${character.id===selectedId?'active':''}" data-character-id="${escapeHtml(character.id)}"><span><strong>${escapeHtml(character.name||'(Chưa đặt tên)')}</strong><small>${escapeHtml(meta.subtitle)}</small></span><span class="character-row-meta">${chips.join('')}</span></button>`;
    }).join('');
  }

  function renderFieldEntryRow(key, entry, index) {
    const invalid=entry.chapter&&!CHAPTER_ID_RE.test(entry.chapter);
    const placeholder=FIELD_PLACEHOLDERS[key]||'Nhập thông tin…';
    const valueInput=MULTILINE_FIELDS.has(key)
      ? `<textarea rows="2" class="character-value-input" data-field-key="${escapeHtml(key)}" data-entry-index="${index}" data-entry-prop="value" placeholder="${escapeHtml(placeholder)}">${escapeHtml(entry.value)}</textarea>`
      : `<input class="character-value-input" data-field-key="${escapeHtml(key)}" data-entry-index="${index}" data-entry-prop="value" value="${escapeHtml(entry.value)}" placeholder="${escapeHtml(placeholder)}">`;
    return `<div class="character-entry-row ${entry.confirmed?'is-confirmed':''}">
      <div class="character-entry-main">${valueInput}</div>
      <div class="character-entry-controls">
        <input class="character-chapter-input ${invalid?'invalid':''}" list="characterChapterOptions" data-field-key="${escapeHtml(key)}" data-entry-index="${index}" data-entry-prop="chapter" value="${escapeHtml(entry.chapter)}" placeholder="Chưa rõ mốc" aria-label="Mã chương cho ${escapeHtml(fieldLabel(key))}">
        <span class="character-source-tag source-${escapeHtml(entry.source)}">${escapeHtml(sourceLabel(entry.source))}</span>
        <button type="button" class="character-lock-btn ${entry.confirmed?'active':''}" data-toggle-field-confirm="${escapeHtml(key)}" data-entry-index="${index}" title="Bảo vệ mục này không bị AI tự ghi đè">${entry.confirmed?'🔒 Đã khóa':'Xác nhận'}</button>
        <button type="button" class="character-remove-btn" data-remove-field-entry="${escapeHtml(key)}" data-entry-index="${index}" aria-label="Xóa mốc">×</button>
      </div>
    </div>`;
  }

  function renderNoteRow(note, index) {
    const invalid=note.chapter&&!CHAPTER_ID_RE.test(note.chapter);
    return `<div class="character-entry-row character-note-row ${note.confirmed?'is-confirmed':''}">
      <div class="character-entry-main">
        <textarea rows="2" class="character-value-input" data-note-index="${index}" data-note-prop="text" placeholder="Biến cố hoặc ghi chú dịch thuật quan trọng (lộ thân phận, đổi phe, đổi xưng hô…)">${escapeHtml(note.text)}</textarea>
      </div>
      <div class="character-entry-controls">
        <input class="character-chapter-input ${invalid?'invalid':''}" list="characterChapterOptions" data-note-index="${index}" data-note-prop="chapter" value="${escapeHtml(note.chapter)}" placeholder="Chưa rõ mốc" aria-label="Mã chương cho diễn biến">
        <span class="character-source-tag source-${escapeHtml(note.source)}">${escapeHtml(sourceLabel(note.source))}</span>
        <button type="button" class="character-lock-btn ${note.confirmed?'active':''}" data-toggle-note-confirm="${index}" title="Bảo vệ diễn biến này">${note.confirmed?'🔒 Đã khóa':'Xác nhận'}</button>
        <button type="button" class="character-remove-btn" data-remove-note="${index}" aria-label="Xóa diễn biến">×</button>
      </div>
    </div>`;
  }

  function renderCharacterDetail() {
    const store=ensureStore();
    const detail=$('#characterDetail');
    const empty=$('#characterEmpty');
    const showDetail=store.recovery_required||!store.characters.length||profileMode!=='list';
    $('#charactersView').classList.toggle('profile-open',Boolean(showDetail));
    if(store.recovery_required){
      if(empty)empty.classList.remove('open');
      if(detail){
        detail.innerHTML=`<div class="character-recovery">
          <strong>Hồ sơ nhân vật (<code>characters.json</code>) đang bị lỗi</strong>
          <span>Không thể đọc file hồ sơ hiện tại. Bản sao lưu <code>characters.json.bak</code> vẫn còn nguyên — hãy khôi phục trước khi chỉnh sửa (bản hỏng sẽ được giữ riêng dưới đuôi <code>.corrupt</code>).</span>
          <button type="button" class="primary" id="recoveryRestoreBackup">Khôi phục từ characters.json.bak</button>
        </div>`;
      }
      return;
    }
    const hasAny=store.characters.length>0;
    if(empty)empty.classList.toggle('open',!hasAny);
    if(!detail)return;
    const character=currentCharacter();
    if(!character){
      detail.innerHTML='<div class="character-placeholder"><strong>Chưa chọn nhân vật</strong><span>Chọn một nhân vật bên trái hoặc bấm + Thêm nhân vật để chỉnh hồ sơ.</span></div>';
      return;
    }

    const notes=character.notes||[];
    const hasUnclassified=Boolean(String(character.unclassified||'').trim());
    const back='<button type="button" class="secondary" data-profile-list>← Danh sách nhân vật</button>';
    if(profileMode==='read'){
      const section=(title,content)=>content?`<details open class="profile-section"><summary>${escapeHtml(title)}</summary>${content}</details>`:'';
      const line=(value,chapter)=>{
        const label=String(chapter||'').replace(/^v(\d+)_c(\d+)_s(\d+)\.md$/i,'Q$1 · Ch$2 · Phần $3');
        return `<p>${escapeHtml(value)}${label?` <small>${escapeHtml(label)}</small>`:''}</p>`;
      };
      const groups=FIELD_GROUPS.map(group=>section(group.title,group.keys.map(key=>{
        const entries=character.fields[key]||[];
        return entries.length?`<h4>${escapeHtml(fieldLabel(key))}</h4>${entries.map(e=>line(e.value,e.chapter)).join('')}`:'';
      }).join(''))).join('');
      const content=groups+section('Diễn biến',notes.map(n=>line(n.text,n.chapter)).join(''))+
        section('Ghi chú chưa phân loại',hasUnclassified?line(character.unclassified):'');
      detail.innerHTML=`<article class="profile-reader"><nav>${back}<button class="secondary" data-profile-edit>Sửa hồ sơ</button></nav><h2>${escapeHtml(character.name)}</h2>${content||'<p>Hồ sơ chưa có thông tin.</p>'}</article>`;
      return;
    }
    const groupsHtml=FIELD_GROUPS.map(group=>{
      const cards=group.keys.map(key=>{
        const entries=character.fields[key]||[];
        const rowsHtml=entries.length
          ? entries.map((entry,index)=>renderFieldEntryRow(key,entry,index)).join('')
          : '<p class="character-field-empty">Chưa có mốc dữ liệu.</p>';
        return `<div class="character-field-card" data-field-card="${escapeHtml(key)}">
          <div class="character-field-head">
            <label>${escapeHtml(fieldLabel(key))}</label>
            <button type="button" class="secondary character-mini-btn" data-add-field-entry="${escapeHtml(key)}">+ Thêm mốc</button>
          </div>
          <div class="character-field-rows">${rowsHtml}</div>
        </div>`;
      }).join('');
      return `<section class="character-group">
        <div class="character-group-head"><h4>${escapeHtml(group.title)}</h4><small>${escapeHtml(group.hint)}</small></div>
        <div class="character-group-grid">${cards}</div>
      </section>`;
    }).join('');


    const notesHtml=notes.length
      ? notes.map((note,index)=>renderNoteRow(note,index)).join('')
      : '<p class="character-field-empty">Chưa có diễn biến nào. Chỉ nên ghi biến cố ảnh hưởng tới cách dịch hoặc xưng hô.</p>';


    const unclassifiedHtml=`<details class="character-unclassified" ${hasUnclassified?'open':''}>
      <summary>Ghi chú chưa phân loại ${hasUnclassified?'(có dữ liệu bảo toàn)':''}</summary>
      <p>Nội dung cũ chưa phân loại tự động được giữ nguyên ở đây (chưa rõ mốc thời điểm). Bạn có thể chuyển dần lên các trường theo chương ở trên.</p>
      <textarea id="characterUnclassifiedInput" rows="4" spellcheck="false" placeholder="Không có ghi chú chưa phân loại.">${escapeHtml(character.unclassified||'')}</textarea>
    </details>`;

    detail.innerHTML=`<div class="profile-nav">${back}<button type="button" class="secondary" data-profile-read>Xem hồ sơ</button></div><div class="character-detail-head">
      <div class="character-name-box">
        <label for="characterNameInput">Tên chuẩn (dùng làm header khi gửi AI)</label>
        <input id="characterNameInput" value="${escapeHtml(character.name)}" placeholder="Tên đầy đủ theo glossary">
      </div>
      <div class="character-detail-actions">
        <button type="button" class="secondary character-delete-btn" id="deleteSelectedCharacter">Xóa nhân vật</button>
      </div>
    </div>
    ${groupsHtml}
    <section class="character-group">
      <div class="character-group-head">
        <div><h4>Diễn biến &amp; thay đổi theo chương</h4><small>Gắn đúng mã chương tiết lộ (ví dụ v7_c11_s1.md) để không lộ thông tin cho chương trước.</small></div>
        <button type="button" class="secondary character-mini-btn" id="addCharacterNote">+ Thêm diễn biến</button>
      </div>
      <div class="character-field-rows">${notesHtml}</div>
    </section>
    ${unclassifiedHtml}`;
  }

  function renderCharacters() {
    const store=ensureStore();
    if(!store.characters.some(item=>item.id===selectedId)){
      selectedId=store.characters[0]?.id||null;
    }
    renderChapterDatalist();
    updateFooterAndBadges();
    renderCharacterList();
    renderCharacterDetail();
  }

  async function loadCharacters({strict=false}={}) {
    if(!state.project)return;
    const project=state.project, revision=state.projectRevision;
    try {
      const data=await api('/api/characters?project='+encodeURIComponent(project));
      if(state.project!==project||state.projectRevision!==revision)return;
      state.characters={
        ...data,
        characters:cloneCharacters(data.characters),
        fields:Array.isArray(data.fields)&&data.fields.length?data.fields:DEFAULT_FIELDS,
        chapters:Array.isArray(data.chapters)?data.chapters:[],
      };
      state.characterDirty=false;
      const saveBtn=$('#saveCharacters');
      if(saveBtn)saveBtn.textContent='Lưu hồ sơ';
      renderCharacters();
    } catch(error) {
      if(state.project===project&&state.projectRevision===revision){
        if(strict)throw error;
        toast(error.message);
      }
    }
  }

  function addCharacter() {
    if(!requireProject())return;
    const store=ensureStore();
    if(store.recovery_required)return toast('Hồ sơ đang bị lỗi. Hãy khôi phục từ characters.json.bak trước khi chỉnh sửa.');
    const existingNames=new Set(store.characters.map(item=>item.name.trim().toLocaleLowerCase('vi')));
    let name='Nhân vật mới';
    let index=2;
    while(existingNames.has(name.toLocaleLowerCase('vi'))){
      name=`Nhân vật mới ${index++}`;
    }
    const created={id:makeLocalId('ch'),name,fields:{},notes:[],unclassified:''};
    store.characters.push(created);
    selectedId=created.id;
    profileMode='edit';
    if($('#characterSearch'))$('#characterSearch').value='';
    markDirty();
    renderCharacterList();
    renderCharacterDetail();
    const input=$('#characterNameInput');
    if(input){input.focus();input.select();}
  }

  function deleteSelectedCharacter() {
    const character=currentCharacter();
    if(!character)return;
    if(!confirm(`Xóa hồ sơ nhân vật “${character.name||'chưa đặt tên'}”? Bạn vẫn có thể khôi phục từ .bak sau khi lưu.`))return;
    const store=ensureStore();
    const index=store.characters.findIndex(item=>item.id===character.id);
    if(index>=0)store.characters.splice(index,1);
    profileMode='list';
    selectedId=store.characters[Math.min(index,store.characters.length-1)]?.id||null;
    markDirty();
    renderCharacterList();
    renderCharacterDetail();
  }

  function buildValidatedPayload() {
    const store=ensureStore();
    const seen=new Set();
    const characters=[];
    for(let i=0;i<store.characters.length;i++){
      const character=store.characters[i];
      const name=String(character.name||'').trim();
      if(!name)throw new Error(`Nhân vật thứ ${i+1} chưa có tên chuẩn`);
      const key=name.toLocaleLowerCase('vi');
      if(seen.has(key))throw new Error(`Tên nhân vật bị trùng: “${name}”`);
      seen.add(key);

      const fields={};
      for(const [fieldKey,entries] of Object.entries(character.fields||{})){
        const cleaned=[];
        for(const entry of entries||[]){
          const value=String(entry.value||'').trim();
          if(!value)continue;
          const chapter=normalizeChapterInput(entry.chapter);
          if(chapter===null){
            throw new Error(`“${name}” · ${fieldLabel(fieldKey)}: mã chương “${entry.chapter}” không hợp lệ (cần dạng v1_c2_s1.md)`);
          }
          cleaned.push({
            id:entry.id,
            value,
            chapter:chapter||null,
            confirmed:Boolean(entry.confirmed),
            source:entry.source||'user',
          });
        }
        if(cleaned.length)fields[fieldKey]=cleaned;
      }

      const notes=[];
      for(const note of character.notes||[]){
        const text=String(note.text||'').trim();
        if(!text)continue;
        const chapter=normalizeChapterInput(note.chapter);
        if(chapter===null){
          throw new Error(`“${name}” · Diễn biến: mã chương “${note.chapter}” không hợp lệ (cần dạng v1_c2_s1.md)`);
        }
        notes.push({
          id:note.id,
          text,
          chapter:chapter||null,
          confirmed:Boolean(note.confirmed),
          source:note.source||'user',
        });
      }

      characters.push({
        id:character.id,
        name,
        fields,
        notes,
        unclassified:String(character.unclassified||'').trim(),
      });
    }
    return characters;
  }

  async function saveCharacters() {
    if(!requireProject())return;
    const project=state.project, revision=state.projectRevision;
    const store=ensureStore();
    if(store.recovery_required)return toast('Hãy khôi phục hồ sơ trước khi chỉnh sửa.');
    let characters;
    try {
      characters=buildValidatedPayload();
    } catch(error) {
      toast(error.message);
      return;
    }
    const clearingAll=store.exists&&store.count>0&&characters.length===0;
    if(clearingAll&&!confirm('Hồ sơ hiện không còn nhân vật nào. Bạn chắc chắn muốn lưu trạng thái trống?'))return;
    const button=$('#saveCharacters');
    if(button){button.disabled=true;button.textContent='Đang lưu…';}
    try {
      const data=await api('/api/characters?project='+encodeURIComponent(project),{
        method:'POST',
        body:JSON.stringify({
          expected_revision:store.revision||0,
          characters,
          allow_empty:clearingAll,
        }),
      });
      if(state.project!==project||state.projectRevision!==revision)return;
      state.characters={
        ...data,
        characters:cloneCharacters(data.characters),
        fields:Array.isArray(data.fields)&&data.fields.length?data.fields:DEFAULT_FIELDS,
        chapters:Array.isArray(data.chapters)?data.chapters:[],
      };
      state.characterDirty=false;
      renderCharacters();
      toast(data.backup?'Đã lưu hồ sơ (characters.json) · Có bản sao .bak':'Đã lưu hồ sơ (characters.json)');
    } catch(error) {
      if(state.project===project&&state.projectRevision===revision)toast(error.message);
    } finally {
      if(button&&state.project===project&&state.projectRevision===revision){
        button.disabled=Boolean(ensureStore().recovery_required);
        button.textContent='Lưu hồ sơ';
      }
    }
  }

  async function restoreBackup() {
    if(!requireProject())return;
    const project=state.project, revision=state.projectRevision;
    if(!confirm('Khôi phục hồ sơ từ characters.json.bak? Bản hiện tại vẫn được sao lưu trước khi thay thế.'))return;
    const button=$('#restoreCharactersBackup');
    if(button)button.disabled=true;
    try {
      const data=await api('/api/characters?project='+encodeURIComponent(project),{
        method:'POST',
        body:JSON.stringify({action:'restore_backup'}),
      });
      if(state.project!==project||state.projectRevision!==revision)return;
      state.characters={
        ...data,
        characters:cloneCharacters(data.characters),
        fields:Array.isArray(data.fields)&&data.fields.length?data.fields:DEFAULT_FIELDS,
        chapters:Array.isArray(data.chapters)?data.chapters:[],
      };
      state.characterDirty=false;
      renderCharacters();
      toast('Đã khôi phục hồ sơ từ characters.json.bak');
    } catch(error) {
      if(state.project===project&&state.projectRevision===revision)toast(error.message);
    } finally {
      if(button&&state.project===project&&state.projectRevision===revision){
        button.disabled=!ensureStore().backup;
      }
    }
  }

  function renderSnapshotView() {
    const renderedEl=$('#characterSnapshotRendered');
    const rawEl=$('#characterSnapshotRaw');
    if(!renderedEl||!rawEl)return;
    const isRaw=snapshotMode==='raw';
    renderedEl.classList.toggle('editor-hidden',isRaw);
    rawEl.classList.toggle('editor-hidden',!isRaw);
    $$('[data-snapshot-mode]').forEach(btn=>btn.classList.toggle('active',btn.dataset.snapshotMode===snapshotMode));
    if(snapshotMarkdown){
      renderedEl.innerHTML=markdownToHtml(snapshotMarkdown,[]);
      rawEl.textContent=snapshotMarkdown;
    } else {
      renderedEl.innerHTML='<div class="character-snapshot-empty">Không có hồ sơ nhân vật nào được gửi cho chương này (chưa có nhân vật liên quan hoặc tất cả mốc đều nằm ở chương này trở về sau).</div>';
      rawEl.textContent='(Trống — không đính kèm characters.md cho chương này)';
    }
  }

  async function refreshSnapshotPreview() {
    if(!state.project)return;
    const project=state.project;
    const revision=++snapshotRevision;
    const select=$('#characterSnapshotChapter');
    const filterBox=$('#characterSnapshotFilterText');
    const status=$('#characterSnapshotStatus');
    const chapter=select?.value||'';
    const filterByText=filterBox?Boolean(filterBox.checked):true;

    let characters;
    try {
      characters=buildValidatedPayload();
    } catch(error) {
      if(status)status.textContent=`Không thể xem trước do lỗi biểu mẫu: ${error.message}`;
      return;
    }
    if(status)status.textContent='Đang dựng dữ liệu gửi AI…';
    try {
      const data=await api('/api/characters/snapshot?project='+encodeURIComponent(project),{
        method:'POST',
        body:JSON.stringify({
          chapter,
          characters,
          filter_by_chapter_text:filterByText,
        }),
      });
      if(state.project!==project||revision!==snapshotRevision)return;
      snapshotMarkdown=data.markdown||'';
      if(status){
        if(data.chapter){
          const scope=data.filtered_by_chapter_text
            ?'đã lọc theo nhân vật xuất hiện trong chương'
            :'toàn bộ nhân vật có dữ liệu trước mốc này';
          status.textContent=`Gửi ${data.matched_count}/${data.total_count} nhân vật · Trạng thái đã xác lập TRƯỚC ${data.chapter} (${scope}).`;
        } else {
          status.textContent=`Gửi ${data.matched_count}/${data.total_count} nhân vật · Không lọc mốc chương.`;
        }
      }
      renderSnapshotView();
    } catch(error) {
      if(state.project===project&&revision===snapshotRevision&&status){
        status.textContent=error.message;
      }
    }
  }

  function openSnapshotModal() {
    if(!requireProject())return;
    const chapters=availableChapters();
    const select=$('#characterSnapshotChapter');
    if(select){
      const options=['<option value="">Không lọc mốc (trạng thái mới nhất)</option>']
        .concat(chapters.map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`));
      select.innerHTML=options.join('');
      const preferred=state.current&&chapters.includes(state.current)
        ? state.current
        : (chapters[chapters.length-1]||'');
      select.value=preferred;
    }
    $('#characterSnapshotModal')?.classList.add('open');
    refreshSnapshotPreview();
  }

  function openMarkdownModal() {
    if(!requireProject())return;
    const store=ensureStore();
    const note=$('#characterMarkdownNotice');
    if(note){
      note.textContent=state.characterDirty
        ?'Đang hiển thị bản xuất đã lưu gần nhất. Bấm “Lưu hồ sơ” để cập nhật bản xuất theo các thay đổi mới.'
        :'Bản xuất một chiều từ characters.json để xem hoặc sao chép. Hãy chỉnh trực tiếp trong biểu mẫu để không làm hỏng cấu trúc.';
    }
    const content=store.content||'';
    if($('#characterMarkdownPreview'))$('#characterMarkdownPreview').textContent=content||'# Chưa có dữ liệu hồ sơ nhân vật.';
    $('#characterMarkdownModal')?.classList.add('open');
  }

  async function copyText(text, label) {
    if(!text)return toast('Chưa có nội dung để sao chép');
    if(copyPlainText){
      await copyPlainText(text);
    } else if(navigator.clipboard?.writeText){
      await navigator.clipboard.writeText(text);
    }
    toast(label);
  }

  function handleDetailInput(event) {
    const character=currentCharacter();
    if(!character)return;
    const target=event.target;
    if(target.id==='characterNameInput'){
      character.name=target.value;
      markDirty();
      const rowTitle=document.querySelector(`.character-row[data-character-id="${CSS?.escape?CSS.escape(character.id):character.id}"] strong`);
      if(rowTitle)rowTitle.textContent=character.name||'(Chưa đặt tên)';
      return;
    }
    if(target.id==='characterUnclassifiedInput'){
      character.unclassified=target.value;
      markDirty();
      return;
    }
    if(target.dataset?.fieldKey){
      const entries=character.fields[target.dataset.fieldKey];
      const entry=entries?.[Number(target.dataset.entryIndex)];
      if(!entry)return;
      const prop=target.dataset.entryProp;
      entry[prop]=target.value;
      if(prop==='chapter'){
        target.classList.toggle('invalid',Boolean(target.value.trim())&&!CHAPTER_ID_RE.test(target.value.trim()));
      }
      if(entry.source!=='user'||!entry.confirmed){
        entry.source='user';
        entry.confirmed=true;
        const row=target.closest('.character-entry-row');
        if(row){
          row.classList.add('is-confirmed');
          const lockBtn=row.querySelector('.character-lock-btn');
          if(lockBtn){lockBtn.classList.add('active');lockBtn.textContent='🔒 Đã khóa';}
          const srcTag=row.querySelector('.character-source-tag');
          if(srcTag){srcTag.className='character-source-tag source-user';srcTag.textContent='Thủ công';}
        }
      }
      markDirty();
      return;
    }
    if(target.dataset?.noteIndex!==undefined){
      const note=character.notes?.[Number(target.dataset.noteIndex)];
      if(!note)return;
      const prop=target.dataset.noteProp;
      note[prop]=target.value;
      if(prop==='chapter'){
        target.classList.toggle('invalid',Boolean(target.value.trim())&&!CHAPTER_ID_RE.test(target.value.trim()));
      }
      if(note.source!=='user'||!note.confirmed){
        note.source='user';
        note.confirmed=true;
        const row=target.closest('.character-entry-row');
        if(row){
          row.classList.add('is-confirmed');
          const lockBtn=row.querySelector('.character-lock-btn');
          if(lockBtn){lockBtn.classList.add('active');lockBtn.textContent='🔒 Đã khóa';}
          const srcTag=row.querySelector('.character-source-tag');
          if(srcTag){srcTag.className='character-source-tag source-user';srcTag.textContent='Thủ công';}
        }
      }
      markDirty();
    }
  }

  function handleDetailClick(event) {
    for(const [selector,mode] of [['[data-profile-list]','list'],['[data-profile-edit]','edit'],['[data-profile-read]','read']]){
      if(event.target.closest(selector)){
        profileMode=mode;
        renderCharacterDetail();
        if(mode==='list')$('#characterList').scrollTop=listScroll;
        else $('#characterDetail').scrollTop=0;
        return;
      }
    }
    if(event.target.closest?.('#recoveryRestoreBackup')){
      restoreBackup();
      return;
    }
    const character=currentCharacter();
    if(!character)return;

    if(event.target.closest('#deleteSelectedCharacter')){
      deleteSelectedCharacter();
      return;
    }

    const addFieldBtn=event.target.closest('[data-add-field-entry]');
    if(addFieldBtn){
      const key=addFieldBtn.dataset.addFieldEntry;
      if(!Array.isArray(character.fields[key]))character.fields[key]=[];
      const defaultChapter=state.current&&CHAPTER_ID_RE.test(state.current)?state.current:'';
      character.fields[key].push({id:makeLocalId('e'),value:'',chapter:defaultChapter,confirmed:true,source:'user'});
      markDirty();
      renderCharacterDetail();
      const card=document.querySelector(`[data-field-card="${key}"] .character-entry-row:last-child .character-value-input`);
      card?.focus();
      return;
    }

    const toggleFieldBtn=event.target.closest('[data-toggle-field-confirm]');
    if(toggleFieldBtn){
      const key=toggleFieldBtn.dataset.toggleFieldConfirm;
      const entry=character.fields[key]?.[Number(toggleFieldBtn.dataset.entryIndex)];
      if(!entry)return;
      entry.confirmed=!entry.confirmed;
      markDirty();
      renderCharacterList();
      renderCharacterDetail();
      return;
    }

    const removeFieldBtn=event.target.closest('[data-remove-field-entry]');
    if(removeFieldBtn){
      const key=removeFieldBtn.dataset.removeFieldEntry;
      const entries=character.fields[key];
      if(!entries)return;
      entries.splice(Number(removeFieldBtn.dataset.entryIndex),1);
      if(!entries.length)delete character.fields[key];
      markDirty();
      renderCharacterList();
      renderCharacterDetail();
      return;
    }

    if(event.target.closest('#addCharacterNote')){
      const defaultChapter=state.current&&CHAPTER_ID_RE.test(state.current)?state.current:'';
      character.notes.push({id:makeLocalId('e'),text:'',chapter:defaultChapter,confirmed:true,source:'user'});
      markDirty();
      renderCharacterDetail();
      const inputs=$$('[data-note-prop="text"]');
      inputs[inputs.length-1]?.focus();
      return;
    }

    const toggleNoteBtn=event.target.closest('[data-toggle-note-confirm]');
    if(toggleNoteBtn){
      const note=character.notes?.[Number(toggleNoteBtn.dataset.toggleNoteConfirm)];
      if(!note)return;
      note.confirmed=!note.confirmed;
      markDirty();
      renderCharacterList();
      renderCharacterDetail();
      return;
    }

    const removeNoteBtn=event.target.closest('[data-remove-note]');
    if(removeNoteBtn){
      character.notes.splice(Number(removeNoteBtn.dataset.removeNote),1);
      markDirty();
      renderCharacterList();
      renderCharacterDetail();
    }
  }

  function handleDocumentClick(event) {
    const row=event.target.closest('[data-character-id]');
    if(row){
      listScroll=$('#characterList').scrollTop;
      profileMode='read';
      selectedId=row.dataset.characterId;
      renderCharacterList();
      renderCharacterDetail();
      $('#characterDetail').scrollTop=0;
      return true;
    }
    return false;
  }

  function closeModals() {
    $('#characterSnapshotModal')?.classList.remove('open');
    $('#characterMarkdownModal')?.classList.remove('open');
  }

  function bind() {
    $('#characterFilter').onchange=renderCharacterList;
    if($('#characterSearch'))$('#characterSearch').oninput=renderCharacterList;
    if($('#addCharacterButton'))$('#addCharacterButton').onclick=addCharacter;
    if($('#emptyAddCharacter'))$('#emptyAddCharacter').onclick=addCharacter;
    if($('#saveCharacters'))$('#saveCharacters').onclick=saveCharacters;
    if($('#restoreCharactersBackup'))$('#restoreCharactersBackup').onclick=restoreBackup;
    if($('#openCharacterSnapshot'))$('#openCharacterSnapshot').onclick=openSnapshotModal;
    if($('#openCharacterMarkdown'))$('#openCharacterMarkdown').onclick=openMarkdownModal;
    if($('#closeCharacterSnapshot'))$('#closeCharacterSnapshot').onclick=()=>$('#characterSnapshotModal')?.classList.remove('open');
    if($('#closeCharacterMarkdown'))$('#closeCharacterMarkdown').onclick=()=>$('#characterMarkdownModal')?.classList.remove('open');
    if($('#characterSnapshotChapter'))$('#characterSnapshotChapter').onchange=refreshSnapshotPreview;
    if($('#characterSnapshotFilterText'))$('#characterSnapshotFilterText').onchange=refreshSnapshotPreview;
    if($('#copyCharacterSnapshot'))$('#copyCharacterSnapshot').onclick=()=>copyText(snapshotMarkdown,'Đã sao chép snapshot gửi AI');
    if($('#copyCharacterMarkdown'))$('#copyCharacterMarkdown').onclick=()=>copyText(ensureStore().content||'','Đã sao chép Markdown hồ sơ nhân vật');
    $$('[data-snapshot-mode]').forEach(button=>{
      button.onclick=()=>{snapshotMode=button.dataset.snapshotMode;renderSnapshotView();};
    });
    const detail=$('#characterDetail');
    if(detail){
      if(detail.addEventListener){
        detail.addEventListener('input',handleDetailInput);
        detail.addEventListener('click',handleDetailClick);
      } else {
        detail.oninput=handleDetailInput;
        detail.onclick=handleDetailClick;
      }
    }
    $('#characterSnapshotModal')?.addEventListener?.('click',event=>{
      if(event.target.id==='characterSnapshotModal')$('#characterSnapshotModal').classList.remove('open');
    });
    $('#characterMarkdownModal')?.addEventListener?.('click',event=>{
      if(event.target.id==='characterMarkdownModal')$('#characterMarkdownModal').classList.remove('open');
    });
  }

  return {
    bind,
    closeModals,
    handleDocumentClick,
    loadCharacters,
    renderCharacters,
    saveCharacters,
  };
}
