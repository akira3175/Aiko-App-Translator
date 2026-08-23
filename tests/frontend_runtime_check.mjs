class ElementStub {
  constructor() {
    this.value='';
    this.checked=false;
    this.disabled=false;
    this.hidden=false;
    this.files=[];
    this.dataset={};
    this.style={setProperty(){}};
    this.children=[];
    this.classList={add(){},remove(){},toggle(){},contains(){return false;}};
  }
  addEventListener() {}
  insertAdjacentHTML() {}
  querySelector() { return new ElementStub(); }
  querySelectorAll() { return []; }
  focus() {}
  select() {}
  setAttribute() {}
  removeAttribute() {}
  scrollIntoView() {}
  getBoundingClientRect() { return {left:0,right:10,top:0,bottom:10,width:10,height:10}; }
  cloneNode() { return new ElementStub(); }
  appendChild() {}
  remove() {}
}

const elements=new Map();
globalThis.HTMLElement=ElementStub;
globalThis.document={
  documentElement:new ElementStub(),
  body:new ElementStub(),
  querySelector(selector) {
    if(!elements.has(selector))elements.set(selector,new ElementStub());
    return elements.get(selector);
  },
  querySelectorAll() { return []; },
  createElement() { return new ElementStub(); },
  createRange() { return {selectNodeContents(){}}; },
  execCommand() { return true; },
  addEventListener() {},
};
globalThis.window=globalThis;
globalThis.innerWidth=1200;
globalThis.innerHeight=800;
globalThis.addEventListener=()=>{};
globalThis.matchMedia=()=>({matches:false});
globalThis.localStorage={getItem(){return null;},setItem(){}};
globalThis.requestAnimationFrame=callback=>{callback();return 1;};
globalThis.cancelAnimationFrame=()=>{};
globalThis.confirm=()=>true;
Object.defineProperty(globalThis,'navigator',{value:{clipboard:{}},configurable:true});
globalThis.getSelection=()=>({removeAllRanges(){},addRange(){},toString(){return '';}});
globalThis.EventSource=class { addEventListener() {} close() {} };

const editor={
  on(){},getValue(){return '';},setValue(){},clearHistory(){},
  getWrapperElement(){return new ElementStub();},refresh(){},
  lineCount(){return 1;},getLine(){return '';},operation(callback){callback();},
  replaceRange(){},posFromIndex(){return {line:0,ch:0};},removeLineClass(){},
  addLineClass(){},setBookmark(){return {clear(){}};},
  getViewport(){return {from:0,to:1};},scrollIntoView(){},hasFocus(){return false;},
  getCursor(){return {line:0,ch:0};},setSelection(){},getSelection(){return '';},
  getRange(){return '';},indexFromPos(){return 0;},setCursor(){},
  replaceSelection(){},focus(){},
};
globalThis.CodeMirror={fromTextArea(){return Object.create(editor);}};
globalThis.fetch=async()=>({
  ok:true,
  status:200,
  json:async()=>({items:[],sidebar:{pinned:[]},versions:[],current_version:'0',sources:[],chapters:[],books:[],pairs:[],count:0,locked_count:0}),
  text:async()=>'',
});

await import('../web/app.js?runtime-check='+Date.now());
await new Promise(resolve=>setTimeout(resolve,20));
console.log('runtime-import-ok');
