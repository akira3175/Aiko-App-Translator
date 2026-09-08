export function createProjectLoadingFeature({retry}) {
  const main=document.querySelector('main');
  const overlay=document.createElement('div');
  overlay.id='projectLoading';overlay.hidden=true;
  overlay.innerHTML='<div class="project-loading-content"><div class="project-loading-art" aria-hidden="true"></div><div class="project-loading-spinner" aria-hidden="true"></div><p role="status" aria-live="polite"></p><button class="primary" type="button" hidden>Thử lại</button></div>';
  main.appendChild(overlay);
  const status=overlay.querySelector('p'),button=overlay.querySelector('button');
  let active=0,timer=null,locked=[];
  const unlock=()=>{for(const [el,inert] of locked)el.inert=inert;locked=[];main.removeAttribute('aria-busy');main.classList.remove('project-is-loading');};
  button.onclick=()=>retry();
  const position=()=>{const rect=main.getBoundingClientRect();overlay.style.top=Math.max(0,document.querySelector('.topbar')?.getBoundingClientRect().bottom||0)+'px';overlay.style.left=Math.max(0,rect.left)+'px';overlay.style.right=Math.max(0,window.innerWidth-rect.right)+'px';};
  window.addEventListener('resize',position);
  window.addEventListener('scroll',()=>{if(active)position();},{passive:true});
  return {
    begin(id,name){
      clearTimeout(timer);unlock();active=id;overlay.hidden=true;overlay.classList.remove('is-error');button.hidden=true;
      status.textContent=`Đang mở ${name}…`;
      document.querySelector('#toast')?.classList.remove('show');
      locked=[...main.querySelectorAll('.view,.top-actions')].map(el=>[el,el.inert]);
      for(const [el] of locked)el.inert=true;
      main.classList.add('project-is-loading');main.setAttribute('aria-busy','true');position();
      timer=setTimeout(()=>{if(active===id)overlay.hidden=false;},250);
    },
    finish(id){if(active!==id)return;clearTimeout(timer);overlay.hidden=true;unlock();active=0;},
    fail(id,name,error){if(active!==id)return;clearTimeout(timer);overlay.hidden=false;overlay.classList.add('is-error');status.textContent=`Không thể mở ${name}. ${error.message}`;button.hidden=false;main.setAttribute('aria-busy','false');},
  };
}
