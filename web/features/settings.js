import { createCloudflareSettingsFeature } from './cloudflare-settings.js';

const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const settingValue=input=>input.type==='checkbox'?(input.checked?'on':'off'):input.value;
const settingsGroups={
  import:['Nhập truyện','Chọn engine và model dùng khi tách TXT bằng AI. AI chỉ xác định vị trí chương; nội dung được lấy từ file gốc.'],
  pipeline:['Quy trình dịch','Chọn engine, model và mức suy nghĩ cho từng công đoạn.'],
  'gemini-api':['Gemini API','Model và thông số sinh nội dung khi dịch, hậu dịch và review qua API.'],
  'gemini-web':['Gemini Web','Gem, model và mức suy nghĩ khi tự động hóa trình duyệt Gemini.'],
  'google-ai-studio-web':['Google AI Studio Web','Gắn link prompt AI Studio, chọn model và mức suy nghĩ trong Run settings.'],
  'chatgpt-web':['ChatGPT Web','Model và mức suy nghĩ khi tự động hóa trình duyệt ChatGPT.'],
  'chatgpt-plan':['ChatGPT Plan','Đăng nhập ChatGPT để thử dùng gói của tài khoản qua OpenAI Responses API.'],
  'antigravity-cli':['Antigravity CLI','Dùng gói thuê bao và AI Credits của tài khoản Antigravity đã đăng nhập qua lệnh agy trên máy.'],
  'gpt-api':['OpenAI API','Khóa, model và thông số cho các công đoạn dùng OpenAI API.'],
  publishing:['Xuất bản','Tài khoản Hako và kho ảnh Cloudflare R2.'],
  sharing:['Chia sẻ','Bucket R2 private và Worker phục vụ bản đọc chia sẻ.'],
  general:['Chung','Hành vi chung của workspace và quy trình hậu xử lý.'],
};
const PROVIDER_LABELS={'gemini-api':'Gemini API','gemini-web':'Gemini Web','google-ai-studio-web':'Google AI Studio Web','openai-api':'OpenAI API','chatgpt-web':'ChatGPT Web','chatgpt-plan':'ChatGPT Plan','antigravity-cli':'Antigravity CLI'};
const PIPELINE_OWNED_SETTING_KEYS=new Set([
  'translate_model','polish_model','pronoun_model','review_bg_model','review_model','context_model','gemini_api_thinking',
  'gemini_web_model','gemini_thinking',
  'ai_studio_model','ai_studio_pronoun_model','ai_studio_review_model',
  'gpt_api_translate_model','gpt_api_polish_model','gpt_api_pronoun_model','gpt_api_review_model',
  'gpt_api_translate_effort','gpt_api_polish_effort','gpt_api_review_effort',
]);
const visibleSettingsForGroup=(items,group)=>items.filter(item=>
  item.group===group && (group==='pipeline'||!PIPELINE_OWNED_SETTING_KEYS.has(item.key))
);

export function createSettingsFeature({api,escapeHtml,refreshUpdate,showView,toast}) {
  let items=[];
  let activeGroup='pipeline';
  let chatgptPlanModels=null;
  let chatgptPlanModelsLoading=false;
  let antigravityCliModels=null;
  let antigravityCliModelsLoading=false;
  const cloudflareSettingsFeature=createCloudflareSettingsFeature({api,getSettingsItems:()=>items,renderSettings:render,toast});

  function updateLinkFields() {
    for(const [prefix,defaultKey] of [['gemini_web','link_gemini'],['ai_studio','link_ai_studio']]) {
      const field=key=>$(`[data-python-setting="${key}"]`);
      const useList=['enabled','on_error'].some(suffix=>field(`${prefix}_rotation_${suffix}`)?.value==='on');
      const periodic=field(`${prefix}_rotation_enabled`)?.value==='on';
      const defaultRow=field(defaultKey)?.closest('.python-setting');
      const listRow=field(`${prefix}_rotation_links`)?.closest('.python-setting');
      if(defaultRow)defaultRow.hidden=useList;
      if(listRow)listRow.hidden=!useList;
      for(const suffix of ['minutes','chapters','loop']) {
        const row=field(`${prefix}_rotation_${suffix}`)?.closest('.python-setting');
        if(row)row.hidden=!periodic;
      }
      for(const suffix of ['enabled','on_error']) {
        const toggle=field(`${prefix}_rotation_${suffix}`);
        if(toggle)toggle.onchange=updateLinkFields;
      }
    }
  }

  function planModelOptions(value) {
    const models=chatgptPlanModels||[];
    const fallback=items.find(item=>item.key==='chatgpt_plan_model')?.value||'';
    const selected=value||fallback||models[0]?.slug||'';
    if(!models.length)return `<option value="${escapeHtml(selected)}">${selected?escapeHtml(selected):chatgptPlanModels?'Kết nối tài khoản ở tab ChatGPT Plan':'Đang tải model…'}</option>`;
    const unavailable=selected&&!models.some(model=>model.slug===selected)
      ? `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} (không có trong tài khoản)</option>`:'';
    return unavailable+models.map(model=>`<option value="${escapeHtml(model.slug)}" ${model.slug===selected?'selected':''}>${escapeHtml(model.display_name)}</option>`).join('');
  }

  function refreshPlanStageModels() {
    $$('[data-plan-stage-model]').forEach(select=>{
      const selected=select.value;
      select.innerHTML=planModelOptions(selected);
    });
  }

  async function ensurePlanModels() {
    if(chatgptPlanModels!==null||chatgptPlanModelsLoading)return;
    chatgptPlanModelsLoading=true;
    try {
      const data=await api('/api/chatgpt-plan/status');
      chatgptPlanModels=data.models||[];
      refreshPlanStageModels();
    } catch(error) { toast(`Không tải được danh sách model ChatGPT: ${error.message}`); }
    finally { chatgptPlanModelsLoading=false; }
  }

  function antigravityModelOptions(value) {
    const models=antigravityCliModels||[];
    const fallback=items.find(item=>item.key==='antigravity_cli_model')?.value||'';
    const selected=value||fallback||models[0]?.slug||'';
    if(!models.length)return `<option value="${escapeHtml(selected)}">${selected?escapeHtml(selected):antigravityCliModels?'Kiểm tra đăng nhập ở tab Antigravity CLI':'Đang tải model từ agy…'}</option>`;
    const unavailable=selected&&!models.some(model=>model.slug===selected)
      ? `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} (không có trong danh sách hiện tại)</option>`:'';
    return unavailable+models.map(model=>`<option value="${escapeHtml(model.slug)}" ${model.slug===selected?'selected':''}>${escapeHtml(model.display_name)}</option>`).join('');
  }

  function refreshAntigravityStageModels() {
    $$('[data-agy-stage-model]').forEach(select=>{
      const selected=select.value;
      select.innerHTML=antigravityModelOptions(selected);
    });
  }

  async function ensureAntigravityModels() {
    if(antigravityCliModels!==null||antigravityCliModelsLoading)return;
    antigravityCliModelsLoading=true;
    try {
      const data=await api('/api/antigravity-cli/status');
      antigravityCliModels=data.models||[];
      refreshAntigravityStageModels();
    } catch(error) { toast(`Không tải được danh sách model Antigravity CLI: ${error.message}`); }
    finally { antigravityCliModelsLoading=false; }
  }

  function render(nextItems) {
    items=nextItems;
    if(!$('#openAppBrowser')){
      $('#workspaceSettings').insertAdjacentHTML('afterbegin',`<section class="app-browser-card"><div><strong>Chrome của ứng dụng</strong><small>Dùng chung cho ChatGPT, Gemini và duyệt web. Bạn có thể đăng nhập, đăng xuất hoặc đổi tài khoản tùy ý.</small></div><button class="primary" id="openAppBrowser" type="button">Mở Chrome</button></section>`);
      $('#openAppBrowser').onclick=openAppBrowser;
    }
    if(!$('#publishingR2Manager')){
      $('#publishingManager').insertAdjacentHTML('afterend',`<div class="cloudflare-deploy-manager" id="publishingR2Manager"><div class="cloudflare-deploy-head"><strong>Tự động thiết lập R2 xuất bản</strong><small>Tạo hoặc cập nhật bucket ảnh public và tự điền toàn bộ cấu hình R2.</small></div><div class="cloudflare-deploy-fields"><label><small>Cloudflare Account ID</small><input id="publishingR2Account" autocomplete="off" placeholder="32 ký tự"></label><label><small>API Token</small><input id="publishingR2Token" type="password" autocomplete="new-password" placeholder="Không lưu token gốc"></label><label><small>Tên bucket ảnh</small><input id="publishingR2Bucket" placeholder="aiko-images"></label></div><details class="cloudflare-token-guide"><summary>Cách lấy Account ID và API Token</summary><ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong> vào ô trên.</li><li>Mở <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noopener noreferrer">Cloudflare → API Tokens</a>, chọn <strong>Create Token</strong> rồi <strong>Create Custom Token</strong>.</li><li>Thêm quyền <strong>Account · Workers R2 Storage · Edit</strong>.</li><li>Ở Account Resources, chọn tài khoản cần dùng; tạo token rồi sao chép vào ô API Token.</li></ol><small>App chỉ dùng token một lần để thiết lập và không lưu token gốc.</small></details><div class="cloudflare-deploy-actions"><small id="publishingR2Status">Bucket này sẽ được bật public qua r2.dev.</small><button class="primary" id="setupPublishingR2" type="button">Tự động thiết lập</button></div></div>`);
      $('#setupPublishingR2').onclick=cloudflareSettingsFeature.setupPublishing;
    }
    if(!$('#cloudflareDeployManager')){
      $('#geminiApiKeyManager').insertAdjacentHTML('beforebegin',`<div class="cloudflare-deploy-manager" id="cloudflareDeployManager"><div class="cloudflare-deploy-head"><strong>Tự động thiết lập Cloudflare</strong><small>Nhập một token; Python tự tạo khóa R2, bucket, Worker và URL chia sẻ.</small></div><div class="cloudflare-deploy-fields"><label><small>Cloudflare Account ID</small><input id="cloudflareDeployAccount" autocomplete="off" placeholder="32 ký tự"></label><label><small>API Token</small><input id="cloudflareDeployToken" type="password" autocomplete="new-password" placeholder="Không lưu token gốc"></label><label><small>Tên Worker</small><input id="cloudflareDeployWorker" value="aiko-share-reader"></label></div><details class="cloudflare-token-guide"><summary>Cách lấy Account ID và API Token</summary><ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong> vào ô trên.</li><li>Mở <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noopener noreferrer">Cloudflare → API Tokens</a>, chọn <strong>Create Token</strong> rồi <strong>Create Custom Token</strong>.</li><li>Thêm quyền <strong>Account · Workers Scripts · Edit</strong>.</li><li>Thêm quyền <strong>Account · Workers R2 Storage · Edit</strong>.</li><li>Ở Account Resources, chọn tài khoản cần dùng; tạo token rồi sao chép vào ô API Token.</li></ol><small>Token chỉ hiển thị một lần. App không lưu token gốc sau khi thiết lập.</small></details><div class="cloudflare-deploy-actions"><small id="cloudflareDeployStatus">Token cần quyền Workers Scripts Edit và Workers R2 Storage Edit.</small><button class="primary" id="deployShareWorker" type="button">Tự động thiết lập</button></div></div>`);
      $('#deployShareWorker').onclick=cloudflareSettingsFeature.deploySharing;
    }
    if(!$('#publishingR2Account').value)$('#publishingR2Account').value=items.find(item=>item.key==='r2_account_id')?.value||items.find(item=>item.key==='share_r2_account_id')?.value||'';
    if(!$('#publishingR2Bucket').value)$('#publishingR2Bucket').value=items.find(item=>item.key==='r2_bucket')?.value||'aiko-images';
    if(!$('#cloudflareDeployAccount').value)$('#cloudflareDeployAccount').value=items.find(item=>item.key==='share_r2_account_id')?.value||'';
    $('#settingsTabs').innerHTML=Object.entries(settingsGroups).map(([key,[label]])=>`<button type="button" role="tab" data-settings-tab="${key}" aria-selected="${key===activeGroup}" class="${key===activeGroup?'active':''}">${label}<span>${visibleSettingsForGroup(items,key).length+(key==='general'||key==='publishing'?1:0)}</span></button>`).join('');
    const [title,description]=settingsGroups[activeGroup];
    $('#settingsGroupTitle').textContent=title;
    $('#workspaceSettings').classList.toggle('active',activeGroup==='general');
    $('#geminiApiKeyManager').classList.toggle('active',activeGroup==='gemini-api');
    $('#publishingManager').classList.toggle('active',activeGroup==='publishing');
    $('#publishingR2Manager').classList.toggle('active',activeGroup==='publishing');
    $('#cloudflareDeployManager').classList.toggle('active',activeGroup==='sharing');
    const renderSetting=item=>{
      if(item.key==='image_markers')return `<div class="setting-row image-marker-setting"><span><strong id="imageMarkerSettingLabel">${escapeHtml(item.label)}</strong><small id="imageMarkerSettingHint">${escapeHtml(item.description)} Mặc định: Tắt.</small></span><label class="switch"><input data-python-setting="image_markers" type="checkbox" role="switch" aria-labelledby="imageMarkerSettingLabel" aria-describedby="imageMarkerSettingHint" ${item.value==='on'?'checked':''}><i aria-hidden="true"></i></label></div>`;
      const control=item.type==='select'
        ? `<select data-python-setting="${escapeHtml(item.key)}">${item.options.map(([value,label])=>`<option value="${escapeHtml(value)}" ${value===item.value?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>`
        : item.type==='text' && item.options?.length
          ? `<input data-python-setting="${escapeHtml(item.key)}" type="text" value="${escapeHtml(item.value)}" list="suggestions-${escapeHtml(item.key)}" autocomplete="off"><datalist id="suggestions-${escapeHtml(item.key)}">${item.options.map(([value,label])=>`<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('')}</datalist>`
        : item.type==='textarea'
          ? `<textarea data-python-setting="${escapeHtml(item.key)}" rows="${item.key.endsWith('_rotation_links')?5:item.key==='gemini_web_upload_instruction'?4:10}" spellcheck="false">${escapeHtml(item.value)}</textarea>`
        : `<input data-python-setting="${escapeHtml(item.key)}" type="${item.type}" value="${escapeHtml(item.value)}" ${item.inputmode?`inputmode="${item.inputmode}"`:''} ${item.type==='number'?`min="${item.min}" max="${item.max}"`:''} autocomplete="off">`;
      return `<label class="python-setting ${item.type==='textarea'?'textarea-setting':''}"><span>${escapeHtml(item.label)}${item.overridden?'<em>Đã tùy chỉnh</em>':''}</span>${control}<small>${item.description?escapeHtml(item.description)+' · ':''}${item.type==='textarea'?'Dùng “Khôi phục mặc định” để đặt lại nội dung.':`Mặc định: ${escapeHtml(item.default??'để trống')}`}</small></label>`;
    };
    const groupItems=visibleSettingsForGroup(items,activeGroup);
    const settingFields=groupItems.filter(item=>
      (activeGroup!=='chatgpt-plan'||item.key!=='chatgpt_plan_model') &&
      (activeGroup!=='antigravity-cli'||item.key!=='antigravity_cli_model')
    ).map(renderSetting).join('');
    const settingItem=key=>items.find(item=>item.key===key);
    const providerDefaults={
      'gemini-api':{
        translate:['translate_model','gemini_api_thinking'],polish:['polish_model','gemini_api_thinking'],
        pronouns:['pronoun_model','gemini_api_thinking'],review:['review_bg_model','gemini_api_thinking'],context:['context_model','gemini_api_thinking'],characters:['translate_model','gemini_api_thinking'],import:['translate_model','gemini_api_thinking'],
      },
      'gemini-web':{
        translate:['gemini_web_model','gemini_thinking'],polish:['gemini_web_model','gemini_thinking'],
        pronouns:['gemini_web_model','gemini_thinking'],review:['gemini_web_model','gemini_thinking'],context:['gemini_web_model','gemini_thinking'],characters:['gemini_web_model','gemini_thinking'],import:['gemini_web_model','gemini_thinking'],
      },
      'google-ai-studio-web':{
        translate:['ai_studio_model','ai_studio_thinking'],polish:['ai_studio_model','ai_studio_thinking'],
        pronouns:['ai_studio_pronoun_model','ai_studio_thinking'],review:['ai_studio_review_model','ai_studio_thinking'],context:['ai_studio_model','ai_studio_thinking'],characters:['ai_studio_model','ai_studio_thinking'],import:['ai_studio_model','ai_studio_thinking'],
      },
      'openai-api':{
        translate:['gpt_api_translate_model','gpt_api_translate_effort'],polish:['gpt_api_polish_model','gpt_api_polish_effort'],
        pronouns:['gpt_api_pronoun_model','gpt_api_polish_effort'],review:['gpt_api_review_model','gpt_api_review_effort'],context:['gpt_api_translate_model','gpt_api_translate_effort'],characters:['gpt_api_translate_model','gpt_api_translate_effort'],import:['gpt_api_translate_model','gpt_api_translate_effort'],
      },
      'chatgpt-web':{
        translate:['chatgpt_model','chatgpt_thinking'],polish:['chatgpt_model','chatgpt_thinking'],
        pronouns:['chatgpt_model','chatgpt_thinking'],review:['chatgpt_model','chatgpt_thinking'],context:['chatgpt_model','chatgpt_thinking'],characters:['chatgpt_model','chatgpt_thinking'],import:['chatgpt_model','chatgpt_thinking'],
      },
      'chatgpt-plan':{
        translate:['chatgpt_plan_model','chatgpt_plan_effort'],polish:['chatgpt_plan_model','chatgpt_plan_effort'],
        pronouns:['chatgpt_plan_model','chatgpt_plan_effort'],review:['chatgpt_plan_model','chatgpt_plan_effort'],context:['chatgpt_plan_model','chatgpt_plan_effort'],characters:['chatgpt_plan_model','chatgpt_plan_effort'],import:['chatgpt_plan_model','chatgpt_plan_effort'],
      },
      'antigravity-cli':{
        translate:['antigravity_cli_model','antigravity_cli_effort'],polish:['antigravity_cli_model','antigravity_cli_effort'],
        pronouns:['antigravity_cli_model','antigravity_cli_effort'],review:['antigravity_cli_model','antigravity_cli_effort'],context:['antigravity_cli_model','antigravity_cli_effort'],characters:['antigravity_cli_model','antigravity_cli_effort'],import:['antigravity_cli_model','antigravity_cli_effort'],
      },
    };
    const engineOptions=(stage,value)=>[['gemini-api','Gemini API'],['gemini-web','Gemini Web'],['google-ai-studio-web','Google AI Studio Web'],['openai-api','OpenAI API'],['chatgpt-web','ChatGPT Web'],['chatgpt-plan','ChatGPT Plan'],['antigravity-cli','Antigravity CLI']].map(([key,label])=>{
      const supported=Boolean(providerDefaults[key][stage]);
      return `<option value="${key}" ${key===value?'selected':''} ${supported?'':'disabled'}>${label}${supported?'':' (chưa hỗ trợ)'}</option>`;
    }).join('');
    const pipelineStage=(label,stage)=>{
      const provider=settingItem(`pipeline_${stage}_provider`);
      const sourceKeys=providerDefaults[provider.value][stage];
      const sourceModel=settingItem(sourceKeys[0]);
      const sourceThinking=settingItem(sourceKeys[1]);
      const modelValue=settingItem(`pipeline_${stage}_model`);
      const thinkingValue=settingItem(`pipeline_${stage}_thinking`);
      const model={...modelValue,default:sourceModel?.default||'',overridden:modelValue.value!==(sourceModel?.default||''),description:`Model riêng cho ${label.toLowerCase()}.`};
      const thinking={...thinkingValue,default:sourceThinking?.default||'',overridden:thinkingValue.value!==(sourceThinking?.default||''),description:provider.value==='openai-api'?'Reasoning riêng cho công đoạn này.':'Thinking riêng cho công đoạn này.'};
      if(provider.value==='google-ai-studio-web'){
        thinking.type='text';
        thinking.options=sourceThinking?.options;
        thinking.description=sourceThinking?.description;
      } else if(provider.value==='antigravity-cli'&&sourceThinking?.options){
        thinking.type='select';
        thinking.options=sourceThinking.options;
        thinking.description=sourceThinking.description;
      }
      const modelField=provider.value==='chatgpt-plan'
        ? `<label class="python-setting"><span>Model</span><select data-python-setting="${model.key}" data-plan-stage-model="${stage}">${planModelOptions(model.value)}</select><small>Model của tài khoản ChatGPT dùng riêng cho ${label.toLowerCase()}.</small></label>`
        : provider.value==='antigravity-cli'
          ? `<label class="python-setting"><span>Model</span><select data-python-setting="${model.key}" data-agy-stage-model="${stage}">${antigravityModelOptions(model.value)}</select><small>Model của Antigravity CLI dùng riêng cho ${label.toLowerCase()}.</small></label>`
          : renderSetting(model);
      return `<details class="pipeline-stage-setting" data-pipeline-stage="${stage}" ${stage==='translate'||stage==='import'?'open':''}><summary><strong>${label}</strong><span>${PROVIDER_LABELS[provider.value]||provider.value}</span></summary><div class="pipeline-stage-body"><label class="python-setting"><span>Engine</span><select data-python-setting="${provider.key}" data-stage-engine="${stage}">${engineOptions(stage,provider.value)}</select><small>Engine dùng riêng cho công đoạn này.</small></label>${modelField}${renderSetting(thinking)}</div></details>`;
    };
    $('#pythonSettingsFields').innerHTML=activeGroup==='pipeline'
      ? `<div class="pipeline-stage-list">${pipelineStage('Dịch','translate')}${pipelineStage('Hiệu đính','polish')}${pipelineStage('Xuất xưng hô','pronouns')}${pipelineStage('Review','review')}${pipelineStage('Tạo Context','context')}${pipelineStage('Hồ sơ nhân vật','characters')}</div>`
      : activeGroup==='import'
      ? `<div class="pipeline-stage-list">${pipelineStage('Tách TXT bằng AI','import')}</div>`
      : activeGroup==='publishing'&&settingFields
      ? `<details class="publishing-advanced"><summary>Cài đặt nâng cao: tài khoản Hako và kho ảnh</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
      : activeGroup==='sharing'&&settingFields
        ? `<details class="publishing-advanced"><summary>Cài đặt R2 nâng cao</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
        : activeGroup==='chatgpt-plan'
          ? `<section class="chatgpt-plan-account"><div class="chatgpt-plan-account-copy"><div class="chatgpt-plan-account-title"><strong>Tài khoản ChatGPT</strong><span id="chatgptPlanBadge" class="chatgpt-plan-badge">Đang kiểm tra</span></div><span id="chatgptPlanStatus">Đang đọc trạng thái…</span><small>Yêu cầu dùng hạn mức của tài khoản ChatGPT. <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Xem mức sử dụng</a></small></div><div class="chatgpt-plan-actions"><button class="primary" id="chatgptPlanConnect" type="button" disabled>Continue with ChatGPT</button><button class="secondary" id="chatgptPlanDisconnect" type="button" hidden>Đăng xuất</button></div></section><label class="python-setting chatgpt-plan-model"><span>Model mặc định</span><select id="chatgptPlanModels" data-python-setting="chatgpt_plan_model">${planModelOptions(settingItem('chatgpt_plan_model')?.value)}</select><small>Dùng khi công đoạn dịch chưa chọn model riêng.</small></label>${settingFields}`
          : activeGroup==='antigravity-cli'
            ? `<section class="chatgpt-plan-account"><div class="chatgpt-plan-account-copy"><div class="chatgpt-plan-account-title"><strong>Antigravity CLI (agy)</strong><span id="antigravityCliBadge" class="chatgpt-plan-badge">Đang kiểm tra</span></div><span id="antigravityCliStatus">Đang đọc trạng thái từ lệnh agy…</span><small>Chạy chế độ ẩn (headless) bằng phiên đăng nhập Antigravity trên máy. Mở Terminal để đăng nhập hoặc gõ <code>/usage</code> kiểm tra hạn mức.</small></div><div class="chatgpt-plan-actions"><button class="secondary" id="antigravityCliRefresh" type="button">Làm mới model</button><button class="primary" id="antigravityCliTerminal" type="button">Mở Terminal agy</button></div></section><label class="python-setting chatgpt-plan-model"><span>Model mặc định</span><select id="antigravityCliModels" data-python-setting="antigravity_cli_model">${antigravityModelOptions(settingItem('antigravity_cli_model')?.value)}</select><small>Dùng khi công đoạn chưa chọn model riêng.</small></label>${settingFields}`
            : settingFields;
    if(activeGroup==='chatgpt-plan'){
      $('#chatgptPlanConnect').onclick=connectChatgptPlan;
      $('#chatgptPlanDisconnect').onclick=disconnectChatgptPlan;
      loadChatgptPlanStatus();
    }
    if(activeGroup==='antigravity-cli'){
      $('#antigravityCliRefresh').onclick=()=>loadAntigravityCliStatus(true);
      $('#antigravityCliTerminal').onclick=openAntigravityCliTerminal;
      loadAntigravityCliStatus(false);
    }
    if(['pipeline','import'].includes(activeGroup)&&$$('[data-plan-stage-model]').length)ensurePlanModels();
    if(['pipeline','import'].includes(activeGroup)&&$$('[data-agy-stage-model]').length)ensureAntigravityModels();
    $$('[data-settings-tab]').forEach(button=>button.onclick=()=>{
      $$('[data-python-setting]').forEach(input=>{ const item=items.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=settingValue(input); });
      activeGroup=button.dataset.settingsTab;
      render(items);
    });
    updateLinkFields();
    $$('[data-stage-engine]').forEach(select=>select.onchange=()=>{
      $$('[data-python-setting]').forEach(input=>{ const item=items.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=settingValue(input); });
      const stage=select.dataset.stageEngine;
      const sourceKeys=providerDefaults[select.value][stage];
      const model=items.find(item=>item.key===`pipeline_${stage}_model`);
      const thinking=items.find(item=>item.key===`pipeline_${stage}_thinking`);
      model.value=settingItem(sourceKeys[0])?.value||'';
      thinking.value=settingItem(sourceKeys[1])?.value||'';
      const opened=new Set($$('.pipeline-stage-setting[open]').map(detail=>detail.dataset.pipelineStage));
      render(items);
      $$('.pipeline-stage-setting').forEach(detail=>detail.open=opened.has(detail.dataset.pipelineStage));
    });
  }

  async function load() {
    try { render((await api('/api/settings')).items); }
    catch(error) { toast(error.message); }
  }

  async function loadChatgptPlanStatus() {
    const label=$('#chatgptPlanStatus'); if(!label)return;
    try {
      const data=await api('/api/chatgpt-plan/status');
      if(!$('#chatgptPlanStatus'))return;
      chatgptPlanModels=data.models||[];
      label.textContent=data.error|| (data.connected?(data.email||'Tài khoản ChatGPT'):'Kết nối để xem model của tài khoản.');
      $('#chatgptPlanBadge').textContent=data.connected?'Đã kết nối':data.error?'Có lỗi':'Chưa kết nối';
      const connect=$('#chatgptPlanConnect');
      connect.disabled=false;
      connect.textContent=data.connected?'Kết nối lại':'Continue with ChatGPT';
      connect.classList.toggle('primary',!data.connected);
      connect.classList.toggle('secondary',Boolean(data.connected));
      $('#chatgptPlanDisconnect').hidden=!data.connected;
      const picker=$('#chatgptPlanModels');
      const selected=picker.value||items.find(item=>item.key==='chatgpt_plan_model')?.value||'';
      picker.innerHTML=planModelOptions(selected);
    } catch(error) { label.textContent=error.message; $('#chatgptPlanBadge').textContent='Có lỗi'; $('#chatgptPlanConnect').disabled=false; }
  }

  async function connectChatgptPlan() {
    const popup=window.open('about:blank','_blank');
    if(!popup){ toast('Trình duyệt chặn cửa sổ đăng nhập.'); return; }
    try {
      const result=await api('/api/chatgpt-plan/connect',{method:'POST',body:'{}'});
      chatgptPlanModels=null;
      popup.location.href=result.url;
      let attempts=0;
      const poll=async()=>{
        if(!$('#chatgptPlanStatus')||attempts++>=60)return;
        await loadChatgptPlanStatus();
        if($('#chatgptPlanDisconnect')?.hidden && attempts<60)setTimeout(poll,3000);
      };
      setTimeout(poll,3000);
    } catch(error) { popup.close(); toast(error.message); }
  }

  async function disconnectChatgptPlan() {
    try { const result=await api('/api/chatgpt-plan/disconnect',{method:'POST',body:'{}'}); chatgptPlanModels=null; await loadChatgptPlanStatus(); toast(result.warning||'Đã đăng xuất ChatGPT'); }
    catch(error) { toast(error.message); }
  }

  async function loadAntigravityCliStatus(refresh=false) {
    const label=$('#antigravityCliStatus'); if(!label)return;
    const refreshBtn=$('#antigravityCliRefresh');
    if(refreshBtn)refreshBtn.disabled=true;
    try {
      const data=await api('/api/antigravity-cli/status'+(refresh?'?refresh=1':''));
      if(!$('#antigravityCliStatus'))return;
      antigravityCliModels=data.models||[];
      if(data.connected){
        const ver=data.version?`v${data.version} · `:'';
        label.textContent=`${ver}${antigravityCliModels.length} model khả dụng · ${data.binary||'agy'}`;
        $('#antigravityCliBadge').textContent='Đã sẵn sàng';
      } else {
        label.textContent=data.error||'Chưa kết nối được với Antigravity CLI.';
        $('#antigravityCliBadge').textContent=data.installed?'Chưa đăng nhập':'Chưa cài đặt';
      }
      const picker=$('#antigravityCliModels');
      if(picker){
        const selected=picker.value||items.find(item=>item.key==='antigravity_cli_model')?.value||'';
        picker.innerHTML=antigravityModelOptions(selected);
      }
      refreshAntigravityStageModels();
    } catch(error) {
      if($('#antigravityCliStatus'))label.textContent=error.message;
      if($('#antigravityCliBadge'))$('#antigravityCliBadge').textContent='Có lỗi';
    } finally {
      if($('#antigravityCliRefresh'))$('#antigravityCliRefresh').disabled=false;
    }
  }

  async function openAntigravityCliTerminal() {
    const button=$('#antigravityCliTerminal');
    if(button)button.disabled=true;
    try {
      const result=await api('/api/antigravity-cli/open-terminal',{method:'POST',body:'{}'});
      toast(result.message||'Đã mở Antigravity CLI');
    } catch(error) {
      toast(error.message);
    } finally {
      if(button)button.disabled=false;
    }
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

  async function save() {
    const button=$('#savePythonSettings'); button.disabled=true;
    const values=Object.fromEntries(items.map(item=>[item.key,item.value]));
    $$('[data-python-setting]').forEach(input=>values[input.dataset.pythonSetting]=settingValue(input));
    try { antigravityCliModels=null; render((await api('/api/settings',{method:'POST',body:JSON.stringify({values})})).items); await Promise.all([refreshUpdate(),loadLanStatus()]); toast('Đã lưu cấu hình · thay đổi LAN cần khởi động lại app'); }
    catch(error) { toast(error.message); }
    finally { button.disabled=false; }
  }

  async function reset() {
    const button=$('#resetPythonSettings'); button.disabled=true;
    try { antigravityCliModels=null; render((await api('/api/settings',{method:'POST',body:JSON.stringify({reset:true})})).items); await loadLanStatus(); toast('Đã khôi phục toàn bộ giá trị mặc định'); }
    catch(error) { toast(error.message); }
    finally { button.disabled=false; }
  }

  async function openAppBrowser() {
    const button=$('#openAppBrowser'); button.disabled=true; button.textContent='Đang mở…';
    try { const result=await api('/api/app-browser/open',{method:'POST',body:'{}'}); toast(result.message); }
    catch(error) { toast(error.message); }
    finally { button.disabled=false; button.textContent='Mở Chrome'; }
  }


  function openGroup(group) {
    activeGroup=group;
    render(items);
    showView('settings');
  }

  function getValue(key) {
    return items.find(item=>item.key===key)?.value||'';
  }

  function bind() {
    $('#savePythonSettings').onclick=save;
    $('#resetPythonSettings').onclick=reset;
    $('#copyLanAccess').onclick=copyLanAccess;
  }

  return {bind,getValue,load,loadLanStatus,openGroup,render};
}
