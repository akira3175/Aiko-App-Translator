import assert from 'node:assert/strict';
import {createProjectMemoryFeature} from '../web/features/project-memory.js';

function setup(save=async()=>({pairs:[],count:0})) {
  const elements=new Map(),calls=[],messages=[];
  const element=selector=>{
    if(!elements.has(selector))elements.set(selector,{
      value:'',checked:false,disabled:false,
      classList:{add(){},remove(){},toggle(){}},
      insertAdjacentHTML(){},querySelectorAll(){return [];},
    });
    return elements.get(selector);
  };
  globalThis.document={querySelector:element,querySelectorAll:()=>[]};
  const record={record_index:1,chapter_number:2,speaker:'Alice',listener:'Bob',speaker_self:'I',speaker_to_listener:'you'};
  const pair={key:'Alice---Bob',revision:'revision-at-open',characters:['Alice','Bob'],latest:record,timeline:[record]};
  const state={project:'Novel',projectRevision:1,pronounCurrent:pair.key,pronouns:{pairs:[pair],count:1}};
  const feature=createProjectMemoryFeature({
    state,navigationCounts:{},escapeHtml:String,toast:message=>messages.push(message),
    api:async(url,options)=>{
      if(!options)return state.pronouns;
      const request={url,body:JSON.parse(options.body)};
      calls.push(request);
      return save(request);
    },
  });
  feature.bind();
  feature.handleDocumentClick({target:{closest:selector=>selector==='[data-pronoun-history-index]'?{dataset:{pronounHistoryIndex:'1'}}:null}});
  return {state,pair,element,calls,messages,feature,save:()=>element('#savePronounEdit').onclick()};
}

// Refreshing the list or selecting a different pair must not retarget an open editor.
{
  const test=setup();
  test.pair.revision='newer-list-revision';
  test.state.pronounCurrent='Other---Pair';
  test.element('#pronounSelf').value='MANUAL';
  await test.save();
  assert.equal(test.calls.length,1);
  assert.equal(test.calls[0].body.key,'Alice---Bob');
  assert.equal(test.calls[0].body.expected_revision,'revision-at-open');
  assert.equal(test.calls[0].body.timeline_index,1);
  assert.equal(test.calls[0].body.expected_speaker,'Alice');
  assert.equal(test.calls[0].body.speaker_self,'MANUAL');
  await test.save();
  assert.equal(test.calls.length,1);
}

// Switching away and back to the same project also invalidates the open editor.
for(const changeProject of [false,true]) {
  const test=setup();
  test.state.projectRevision++;
  if(changeProject)test.state.project='Other novel';
  await test.save();
  assert.equal(test.calls.length,0);
  assert.match(test.messages.at(-1),/Truyện đang mở đã thay đổi/);
}

// A completed request for the old project cannot overwrite the new project's UI.
{
  let finish;
  const test=setup(()=>new Promise(resolve=>{finish=resolve;}));
  const saving=test.save();
  const newData={pairs:[],count:123};
  test.state.project='Other novel';
  test.state.projectRevision++;
  test.state.pronouns=newData;
  finish({pairs:[],count:0});
  await saving;
  assert.equal(test.calls[0].url,'/api/pronouns?project=Novel');
  assert.equal(test.state.pronouns,newData);
}

// A rejected stale edit leaves entered text available and reports the server error.
{
  const test=setup(async()=>{throw new Error('Lịch sử xưng hô đã thay đổi');});
  test.element('#pronounSelf').value='MANUAL';
  await test.save();
  assert.equal(test.element('#pronounSelf').value,'MANUAL');
  assert.equal(test.element('#savePronounEdit').disabled,false);
  assert.match(test.messages.at(-1),/đã thay đổi/);
}

{
  const test=setup();
  test.element('#cancelPronounEdit').onclick();
  await test.save();
  assert.equal(test.calls.length,0);
}

// Deletion sends the revision of the pair that the user actually confirmed.
{
  const test=setup();
  globalThis.confirm=()=>true;
  await test.feature.loadPronouns();
  await test.element('#deletePronounPair').onclick();
  assert.equal(test.calls[0].body.action,'delete');
  assert.equal(test.calls[0].body.expected_revision,'revision-at-open');
}

console.log('pronoun-editor-check-ok');
