export async function api(path, options) {
  const canRetry=!options?.method||options.method==='GET';
  for(let attempt=0;attempt<(canRetry?2:1);attempt++){
    try {
      const response = await fetch(path, { cache:'no-store', headers: {'Content-Type':'application/json'}, ...options });
      const contentType=response.headers.get('content-type')||'';
      if(!contentType.includes('application/json')){
        throw new Error('Backend đang chạy phiên bản cũ. Hãy khởi động lại app rồi thử lại.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Có lỗi xảy ra');
      return data;
    } catch(error) {
      if(attempt===0&&canRetry&&error instanceof TypeError){
        await new Promise(resolve=>setTimeout(resolve,150));
        continue;
      }
      if(error instanceof TypeError)throw new Error('Không kết nối được server. Hãy chạy lại start_app.bat rồi thử lại.');
      throw error;
    }
  }
}
