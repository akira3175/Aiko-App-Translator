import assert from 'node:assert/strict';
import {createLibraryFeature} from '../web/features/library.js';

const elements=new Map();
globalThis.document={querySelector(selector){
  if(selector.includes('[data-index'))return null;
  if(!elements.has(selector))elements.set(selector,{value:'',innerHTML:'',textContent:'',disabled:false,setAttribute(){},focus(){},classList:{contains(){return true;}}});
  return elements.get(selector);
}};
const el=selector=>document.querySelector(selector);
el('#libraryFilter').value='all';
let rows=[{name:'Alpha',hidden:false,total:2,translated:1},{name:'Beta',hidden:true,total:1,translated:0}];
const state={project:'Alpha'},views=[],requests=[],messages=[];
let fail=false,pickerUpdates=0;
const feature=createLibraryFeature({
  state,escapeHtml:value=>value,renderProjectPicker(){pickerUpdates++;},
  selectProject:async name=>{state.project=name;},showView:name=>views.push(name),toast:message=>messages.push(message),
  api:async(path,options)=>{
    requests.push(path);
    if(fail)throw Error('offline');
    if(path==='/api/library')return {items:structuredClone(rows),can_open_folder:true};
    if(path.startsWith('/api/library/visibility')){
      rows.find(row=>row.name===new URL('http://test'+path).searchParams.get('project')).hidden=JSON.parse(options.body).hidden;
    }
    return {ok:true};
  },
});
feature.bind();
const click=(index,action)=>el('#libraryItems').onclick({target:{closest:()=>({dataset:{index:String(index),libraryAction:action},disabled:false})}});
await feature.load();
assert.deepEqual(state.hiddenProjects,['Beta']);
await click(0,'visibility');
assert.deepEqual(state.hiddenProjects,['Alpha','Beta']);
assert.equal(state.project,'Alpha');
await feature.load();
assert.deepEqual(state.hiddenProjects,['Alpha','Beta']);
el('#libraryFilter').value='visible';el('#libraryFilter').onchange();
assert.match(el('#libraryItems').innerHTML,/library-empty/);
el('#libraryFilter').value='hidden';el('#libraryFilter').onchange();
assert.match(el('#libraryItems').innerHTML,/Beta/);
el('#librarySearch').value='ALPHA';el('#librarySearch').oninput();
assert.match(el('#libraryItems').innerHTML,/Alpha/);assert.doesNotMatch(el('#libraryItems').innerHTML,/Beta/);
fail=true;await click(0,'visibility');assert.deepEqual(state.hiddenProjects,['Alpha','Beta']);assert.equal(messages.at(-1),'offline');
fail=false;await click(0,'visibility');assert.deepEqual(state.hiddenProjects,['Beta']);
await click(1,'open');assert.equal(state.project,'Beta');assert.equal(views.at(-1),'workspace');assert.deepEqual(state.hiddenProjects,['Beta']);
await click(1,'folder');assert.ok(requests.includes('/api/library/open-folder?project=Beta'));
fail=true;await feature.load();assert.match(el('#libraryStatus').textContent,/offline/);assert.equal(el('#libraryRefresh').disabled,false);
fail=false;rows=[];await feature.load();assert.match(el('#libraryItems').innerHTML,/library-empty/);
assert.ok(pickerUpdates>=4);
console.log('library-check-ok: visibility, reload, filters, failed save, hidden project opening, folder action, retry, empty state');
