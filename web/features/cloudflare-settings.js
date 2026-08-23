const $ = (selector) => document.querySelector(selector);

export function r2CredentialGuide(kind){
  const label=kind==='sharing'?'Share R2':'R2 Xuất bản';
  const note=kind==='sharing'?'<p>Nếu dùng <strong>Tự động thiết lập Cloudflare</strong> ở trên, app sẽ tự điền ba giá trị này.</p>':'';
  return `<details class="cloudflare-token-guide r2-credential-guide"><summary>Cách lấy ${label} Account ID và Access Key</summary>${note}<ol><li>Mở <a href="https://dash.cloudflare.com/?to=/:account/r2/overview" target="_blank" rel="noopener noreferrer">Cloudflare → R2 Overview</a>. Trong <strong>Account Details</strong>, sao chép <strong>Account ID</strong>.</li><li>Chọn <strong>Manage R2 API Tokens</strong> rồi tạo Account API token hoặc User API token.</li><li>Chọn quyền <strong>Object Read & Write</strong>. Có thể giới hạn token vào bucket dùng cho ${kind==='sharing'?'chia sẻ':'ảnh xuất bản'}.</li><li>Sau khi tạo, sao chép đúng hai giá trị <strong>Access Key ID</strong> và <strong>Secret Access Key</strong> vào app.</li></ol><small>Secret Access Key chỉ được Cloudflare hiển thị một lần. Đây không phải chuỗi API Token dùng để deploy Worker.</small></details>`;
}

export function createCloudflareSettingsFeature({api,getSettingsItems,renderSettings,toast}){
  const setupPublishing=async()=>{
    const button=$('#setupPublishingR2'),token=$('#publishingR2Token').value.trim();
    if(!token)return toast('Hãy nhập Cloudflare API Token');
    button.disabled=true;button.textContent='Đang thiết lập…';$('#publishingR2Status').textContent='Đang tạo bucket và bật đường dẫn public…';
    try{const data=await api('/api/publishing-r2/setup',{method:'POST',body:JSON.stringify({account_id:$('#publishingR2Account').value.trim(),api_token:token,bucket:$('#publishingR2Bucket').value.trim()||'aiko-images'})});$('#publishingR2Token').value='';renderSettings(data.items);$('#publishingR2Status').textContent=`Hoàn tất: ${data.public_url}`;toast(data.bucket_created?'Đã tạo và cấu hình bucket ảnh':'Đã cập nhật cấu hình bucket ảnh');}
    catch(error){$('#publishingR2Status').textContent=error.message;toast(error.message);}finally{button.disabled=false;button.textContent='Tự động thiết lập';}
  };
  const deploySharing=async()=>{
    const button=$('#deployShareWorker'),token=$('#cloudflareDeployToken').value.trim();
    if(!token)return toast('Hãy nhập Cloudflare API Token');
    const visibleBucket=$('[data-python-setting="share_r2_bucket"]')?.value,bucket=visibleBucket||getSettingsItems().find(item=>item.key==='share_r2_bucket')?.value||'private-shares';
    button.disabled=true;button.textContent='Đang thiết lập…';$('#cloudflareDeployStatus').textContent='Đang tạo bucket và tải Worker lên Cloudflare…';
    try{const data=await api('/api/share-worker/deploy',{method:'POST',body:JSON.stringify({account_id:$('#cloudflareDeployAccount').value.trim(),api_token:token,bucket,worker_name:$('#cloudflareDeployWorker').value.trim()})});$('#cloudflareDeployToken').value='';renderSettings(data.items);$('#cloudflareDeployStatus').textContent=`Hoàn tất: ${data.worker_url}`;toast(data.bucket_created?'Đã tạo bucket và deploy Worker':'Đã cập nhật Worker');}
    catch(error){$('#cloudflareDeployStatus').textContent=error.message;toast(error.message);}finally{button.disabled=false;button.textContent='Tự động thiết lập';}
  };
  return {deploySharing,setupPublishing};
}
