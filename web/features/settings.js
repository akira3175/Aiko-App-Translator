import { createCloudflareSettingsFeature, r2CredentialGuide } from './cloudflare-settings.js';

const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const settingsGroups={
  pipeline:['Quy trình dịch','Chọn engine, model và mức suy nghĩ cho từng công đoạn.'],
  'gemini-api':['Gemini API','Model và thông số sinh nội dung khi dịch, hậu dịch và review qua API.'],
  'gemini-web':['Gemini Web','Gem, model và mức suy nghĩ khi tự động hóa trình duyệt Gemini.'],
  'chatgpt-web':['ChatGPT Web','Model và mức suy nghĩ khi tự động hóa trình duyệt ChatGPT.'],
  'gpt-api':['OpenAI API','Khóa, model và thông số cho các công đoạn dùng OpenAI API.'],
  publishing:['Xuất bản','Tài khoản Hako và kho ảnh Cloudflare R2.'],
  sharing:['Chia sẻ','Bucket R2 private và Worker phục vụ bản đọc chia sẻ.'],
  general:['Chung','Hành vi chung của workspace và quy trình hậu xử lý.'],
};
const PROVIDER_LABELS={'gemini-api':'Gemini API','gemini-web':'Gemini Web','openai-api':'OpenAI API','chatgpt-web':'ChatGPT Web'};
const PIPELINE_OWNED_SETTING_KEYS=new Set([
  'translate_model','polish_model','pronoun_model','review_bg_model','gemini_api_thinking',
  'gemini_web_model','gemini_thinking',
  'gpt_api_translate_model','gpt_api_polish_model','gpt_api_pronoun_model','gpt_api_review_model',
  'gpt_api_translate_effort','gpt_api_polish_effort','gpt_api_review_effort',
]);
const visibleSettingsForGroup=(items,group)=>items.filter(item=>
  item.group===group && (group==='pipeline'||!PIPELINE_OWNED_SETTING_KEYS.has(item.key))
);

export function createSettingsFeature({api,escapeHtml,refreshUpdate,showView,toast}) {
  let items=[];
  let activeGroup='pipeline';
  const cloudflareSettingsFeature=createCloudflareSettingsFeature({api,getSettingsItems:()=>items,renderSettings:render,toast});

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
    $('#settingsGroupTitle').textContent=title; $('#settingsGroupDescription').textContent=description;
    $('#workspaceSettings').classList.toggle('active',activeGroup==='general');
    $('#geminiApiKeyManager').classList.toggle('active',activeGroup==='gemini-api');
    $('#publishingManager').classList.toggle('active',activeGroup==='publishing');
    $('#publishingR2Manager').classList.toggle('active',activeGroup==='publishing');
    $('#cloudflareDeployManager').classList.toggle('active',activeGroup==='sharing');
    const renderSetting=item=>{
      const control=item.type==='select'
        ? `<select data-python-setting="${escapeHtml(item.key)}">${item.options.map(([value,label])=>`<option value="${escapeHtml(value)}" ${value===item.value?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>`
        : item.type==='textarea'
          ? `<textarea data-python-setting="${escapeHtml(item.key)}" rows="10" spellcheck="false">${escapeHtml(item.value)}</textarea>`
        : `<input data-python-setting="${escapeHtml(item.key)}" type="${item.type}" value="${escapeHtml(item.value)}" ${item.inputmode?`inputmode="${item.inputmode}"`:''} ${item.type==='number'?`min="${item.min}" max="${item.max}"`:''} autocomplete="off">`;
      return `<label class="python-setting ${item.type==='textarea'?'textarea-setting':''}"><span>${escapeHtml(item.label)}${item.overridden?'<em>Đã tùy chỉnh</em>':''}</span>${control}<small>${item.description?escapeHtml(item.description)+' · ':''}${item.type==='textarea'?'Dùng “Khôi phục mặc định” để lấy lại tiêu chí chuẩn.':`Mặc định: ${escapeHtml(item.default||'để trống')}`}</small></label>`;
    };
    const groupItems=visibleSettingsForGroup(items,activeGroup);
    const settingFields=groupItems.map(renderSetting).join('');
    const settingItem=key=>items.find(item=>item.key===key);
    const providerDefaults={
      'gemini-api':{
        translate:['translate_model','gemini_api_thinking'],polish:['polish_model','gemini_api_thinking'],
        pronouns:['pronoun_model','gemini_api_thinking'],review:['review_bg_model','gemini_api_thinking'],context:['context_model','gemini_api_thinking'],characters:['character_model','gemini_api_thinking'],
      },
      'gemini-web':{
        translate:['gemini_web_model','gemini_thinking'],polish:['gemini_web_model','gemini_thinking'],
        pronouns:['gemini_web_model','gemini_thinking'],review:['gemini_web_model','gemini_thinking'],context:['gemini_web_model','gemini_thinking'],characters:['gemini_web_model','gemini_thinking'],
      },
      'openai-api':{
        translate:['gpt_api_translate_model','gpt_api_translate_effort'],polish:['gpt_api_polish_model','gpt_api_polish_effort'],
        pronouns:['gpt_api_pronoun_model','gpt_api_polish_effort'],review:['gpt_api_review_model','gpt_api_review_effort'],context:['gpt_api_translate_model','gpt_api_translate_effort'],characters:['gpt_api_translate_model','gpt_api_translate_effort'],
      },
      'chatgpt-web':{
        translate:['chatgpt_model','chatgpt_thinking'],polish:['chatgpt_model','chatgpt_thinking'],
        pronouns:['chatgpt_model','chatgpt_thinking'],review:['chatgpt_model','chatgpt_thinking'],context:['chatgpt_model','chatgpt_thinking'],characters:['chatgpt_model','chatgpt_thinking'],
      },
    };
    const engineOptions=(stage,value)=>[['gemini-api','Gemini API'],['gemini-web','Gemini Web'],['openai-api','OpenAI API'],['chatgpt-web','ChatGPT Web']].map(([key,label])=>{
      const supported=Boolean(providerDefaults[key][stage]);
      return `<option value="${key}" ${key===value?'selected':''} ${supported?'':'disabled'}>${label}${supported?'':' (chưa hỗ trợ)'}</option>`;
    }).join('');
    const pipelineStage=(label,stage)=>{
      const provider=settingItem(`pipeline_${stage}_provider`);
      const model={...settingItem(`pipeline_${stage}_model`),description:`Model riêng cho ${label.toLowerCase()}.`};
      const thinking={...settingItem(`pipeline_${stage}_thinking`),description:provider.value==='openai-api'?'Reasoning riêng cho công đoạn này.':'Thinking riêng cho công đoạn này.'};
      return `<details class="pipeline-stage-setting" data-pipeline-stage="${stage}" ${stage==='translate'?'open':''}><summary><strong>${label}</strong><span>${PROVIDER_LABELS[provider.value]||provider.value}</span></summary><div class="pipeline-stage-body"><label class="python-setting"><span>Engine</span><select data-python-setting="${provider.key}" data-stage-engine="${stage}">${engineOptions(stage,provider.value)}</select><small>Engine dùng riêng cho công đoạn này.</small></label>${renderSetting(model)}${renderSetting(thinking)}</div></details>`;
    };
    $('#pythonSettingsFields').innerHTML=activeGroup==='pipeline'
      ? `<div class="pipeline-stage-list">${pipelineStage('Dịch','translate')}${pipelineStage('Hiệu đính','polish')}${pipelineStage('Xuất xưng hô','pronouns')}${pipelineStage('Review','review')}${pipelineStage('Tạo Context','context')}${pipelineStage('Hồ sơ nhân vật','characters')}</div>`
      : activeGroup==='publishing'&&settingFields
      ? `${r2CredentialGuide('publishing')}<details class="publishing-advanced"><summary>Cài đặt nâng cao: tài khoản Hako và kho ảnh</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
      : activeGroup==='sharing'&&settingFields
        ? `${r2CredentialGuide('sharing')}<details class="publishing-advanced"><summary>Cài đặt R2 nâng cao</summary><div class="publishing-advanced-fields">${settingFields}</div></details>`
        : settingFields;
    $$('[data-settings-tab]').forEach(button=>button.onclick=()=>{
      $$('[data-python-setting]').forEach(input=>{ const item=items.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=input.value; });
      activeGroup=button.dataset.settingsTab;
      render(items);
    });
    $$('[data-stage-engine]').forEach(select=>select.onchange=()=>{
      $$('[data-python-setting]').forEach(input=>{ const item=items.find(entry=>entry.key===input.dataset.pythonSetting); if(item)item.value=input.value; });
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
    $$('[data-python-setting]').forEach(input=>values[input.dataset.pythonSetting]=input.value);
    try { render((await api('/api/settings',{method:'POST',body:JSON.stringify({values})})).items); await Promise.all([refreshUpdate(),loadLanStatus()]); toast('Đã lưu cấu hình · thay đổi LAN cần khởi động lại app'); }
    catch(error) { toast(error.message); }
    finally { button.disabled=false; }
  }
  
  async function reset() {
    const button=$('#resetPythonSettings'); button.disabled=true;
    try { render((await api('/api/settings',{method:'POST',body:JSON.stringify({reset:true})})).items); await loadLanStatus(); toast('Đã khôi phục toàn bộ giá trị mặc định'); }
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
