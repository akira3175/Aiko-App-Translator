const $ = (selector) => document.querySelector(selector);

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
