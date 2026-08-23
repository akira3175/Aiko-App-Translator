const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

export function createPublishingBooksFeature({api,escapeHtml,getProject,toast}) {
  let books=[];
  const sync=()=>{books=$$('[data-publishing-book]').map(row=>({book_id:row.querySelector('[data-book-id]').value,volume:row.querySelector('[data-book-volume]').value}));};
  const render=()=>{
    $('#publishingProjectLabel').textContent=getProject()||'Chưa chọn truyện';
    $('#publishingBookList').innerHTML=books.map((book,index)=>`<div class="publishing-book-row" data-publishing-book><span>${index+1}</span><label><small>Volume</small><input data-book-volume type="number" min="0" value="${escapeHtml(book.volume??'')}"></label><label><small>Book ID hoặc link tạo chương</small><input data-book-id value="${escapeHtml(book.book_id||'')}" placeholder="40699"></label><button type="button" data-remove-publishing-book aria-label="Xóa volume ${index+1}">Xóa</button></div>`).join('')||'<div class="publishing-book-empty">Chưa thiết lập nơi đăng. Hãy thêm volume đầu tiên.</div>';
    $$('[data-remove-publishing-book]').forEach((button,index)=>button.onclick=()=>{sync();books.splice(index,1);render();});
  };
  const load=async()=>{
    const project=getProject();
    if(!project){books=[];render();return;}
    try{const data=await api('/api/publishing?project='+encodeURIComponent(project));books=data.books||[];render();}
    catch(error){books=[];render();toast(error.message);}
  };
  const save=async()=>{
    const project=getProject();if(!project)return toast('Hãy chọn truyện trước');
    sync();const button=$('#savePublishingBooks');button.disabled=true;
    try{const data=await api('/api/publishing?project='+encodeURIComponent(project),{method:'POST',body:JSON.stringify({books})});books=data.books||[];render();toast('Đã lưu book ID cho truyện');}
    catch(error){toast(error.message);}finally{button.disabled=false;}
  };
  const add=()=>{sync();const used=books.map(book=>Number(book.volume)).filter(Number.isFinite);books.push({book_id:'',volume:used.length?Math.max(...used)+1:1});render();};
  const bind=()=>{$('#addPublishingBook').onclick=add;$('#savePublishingBooks').onclick=save;};
  const getBooks=()=>books.map(book=>({...book}));
  return {bind,getBooks,load};
}
