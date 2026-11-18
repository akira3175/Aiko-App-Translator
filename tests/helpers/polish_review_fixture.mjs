import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {createEditorFeature} from '../../web/features/editor.js';
import {createPolishReviewFeature} from '../../web/features/polish-review.js';
const require=createRequire(new URL('../../web-client/package.json',import.meta.url));
const {JSDOM}=require('jsdom');

export function fixture() {
  const dom=new JSDOM(readFileSync(new URL('../../web/index.html',import.meta.url),'utf8'),{runScripts:'outside-only',pretendToBeVisual:true});
  const {window}=dom;window.focus=()=>{};window.scrollTo=()=>{};
  window.document.elementFromPoint=()=>null;
  const errors=[];window.addEventListener('error',event=>errors.push(event.error));
  // Real CodeMirror state/operations; jsdom has no pixel layout or IME engine.
  const rect=()=>({left:0,right:100,top:0,bottom:20,width:100,height:20});
  Object.defineProperties(window.HTMLElement.prototype,{clientHeight:{get:()=>600},clientWidth:{get:()=>800},offsetHeight:{get:()=>20},offsetWidth:{get:()=>800}});
  window.Range.prototype.getBoundingClientRect=rect;window.Range.prototype.getClientRects=()=>[rect()];
  window.eval(readFileSync(new URL('../../web/vendor/codemirror/lib/codemirror.js',import.meta.url),'utf8'));
  Object.assign(globalThis,{window,document:window.document,innerWidth:window.innerWidth,innerHeight:window.innerHeight,HTMLElement:window.HTMLElement,CodeMirror:window.CodeMirror,requestAnimationFrame:callback=>callback()});
  const $=selector=>document.querySelector(selector);
  const state={project:'Demo',current:'v1_c1_s1.md',dirty:false,currentImages:[]};
  const calls=[],messages=[],reloads=[],normalSaves=[];
  const server={fail:false,hold:null,latest:null,liveText:'Bản dịch trên đĩa',reloadFails:false};
  const api=async(url,options)=>{
    if(!options)return {polish_review:structuredClone(server.latest),translated:server.liveText};
    const body=JSON.parse(options.body);calls.push({url,...body});
    if(server.hold)await server.hold;
    if(server.fail)throw new Error('Lỗi kết nối hoặc xung đột');
    return {ok:true,revision:body.revision+1,translated:body.action==='discard'?server.liveText:body.draft_text};
  };
  const escapeHtml=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const editorFeature=createEditorFeature({api,state,escapeHtml,toast:message=>messages.push(message),saveChapter:()=>normalSaves.push(editorFeature.value('target'))});
  editorFeature.init();
  const feature=createPolishReviewFeature({api,state,toast:message=>messages.push(message),escapeHtml,editorFeature,reload:async(...args)=>{reloads.push(args);if(server.reloadFails)throw new Error('Chapter reload failed');}});
  const blocks=[{old:'# Tên\n\n',new:'# Tên\n\n'},{old:'Câu này khó hiểu.\n\n',new:'Câu này dễ hiểu.\n\n'},{old:'Không đổi\n\n',new:'Không đổi\n\n'},{old:'Hai lựa chọn.\n',new:'Chỉ hai lựa chọn.\n'}];
  const review={id:'one',revision:0,original:blocks.map(b=>b.old).join(''),proposed:blocks.map(b=>b.new).join(''),blocks,values:blocks.map(b=>b.new)};
  const open=()=>feature.open(structuredClone(review));
  const click=action=>$(`[data-review-action="${action}"]`).click();
  const close=()=>{feature.open(null);dom.window.close();if(errors.length)throw errors[0];};
  return {$,window,dom,state,editorFeature,feature,cm:editorFeature.views.target,review,server,calls,messages,reloads,normalSaves,open,click,close};
}
