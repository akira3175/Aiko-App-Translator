import assert from 'node:assert/strict';
import {createCharactersFeature} from '../web/features/characters.js';

function createElement(id='') {
  const listeners=new Map();
  const classes=new Set();
  return {
    id,
    value:'',
    checked:false,
    disabled:false,
    hidden:false,
    innerHTML:'',
    textContent:'',
    dataset:{},
    classList:{
      add(name){classes.add(name);},
      remove(name){classes.delete(name);},
      toggle(name,force){if(force===undefined){if(classes.has(name))classes.delete(name);else classes.add(name);}else if(force)classes.add(name);else classes.delete(name);},
      contains(name){return classes.has(name);},
    },
    addEventListener(type,fn){listeners.set(type,fn);},
    trigger(type,event){listeners.get(type)?.(event);},
    focus(){},
    select(){},
    querySelector(){return null;},
    querySelectorAll(){return [];},
  };
}

function setup() {
  const elements=new Map();
  const get=selector=>{
    if(!elements.has(selector))elements.set(selector,createElement(selector.replace(/^#/,'')));
    return elements.get(selector);
  };
  globalThis.document={querySelector:get,querySelectorAll:()=>[]};
  globalThis.confirm=()=>true;

  const calls=[];
  const messages=[];
  const initialData={
    revision:2,
    exists:true,
    count:1,
    backup:true,
    legacy_backup:false,
    chapters:['v1_c1_s1.md','v7_c11_s1.md'],
    content:'# Hồ Sơ Nhân Vật\n\n## Lâm Phong\n',
    characters:[
      {
        id:'ch_lin',
        name:'Lâm Phong',
        fields:{
          status:[
            {id:'e1',value:'Đệ tử',chapter:'v1_c1_s1.md',confirmed:false,source:'ai'},
          ],
        },
        notes:[],
        unclassified:'',
      },
    ],
  };

  const state={project:'Demo',projectRevision:1,current:'v7_c11_s1.md',chapters:[{name:'v1_c1_s1.md'},{name:'v7_c11_s1.md'}]};
  const navigationCounts={characters:0};

  const feature=createCharactersFeature({
    api:async(url,options)=>{
      calls.push({url,body:options?JSON.parse(options.body):null});
      if(url.startsWith('/api/characters/snapshot')){
        return {
          chapter:'v7_c11_s1.md',
          markdown:'# Hồ Sơ Nhân Vật Liên Quan\n\n## Lâm Phong\n- **Địa vị / Chức vụ**: Đệ tử (từ v1_c1_s1.md)\n',
          matched_count:1,
          total_count:1,
          filtered_by_chapter_text:true,
          chapter_found:true,
        };
      }
      if(!options)return structuredClone(initialData);
      const body=JSON.parse(options.body);
      if(body.action==='restore_backup'){
        return {...structuredClone(initialData),revision:4};
      }
      return {...structuredClone(initialData),revision:3,characters:body.characters,count:body.characters.length};
    },
    copyPlainText:async()=>{},
    escapeHtml:String,
    markdownToHtml:text=>`<p>${text}</p>`,
    navigationCounts,
    requireProject:()=>Boolean(state.project),
    state,
    toast:msg=>messages.push(msg),
  });

  feature.bind();
  return {feature,state,get,calls,messages,navigationCounts};
}

// 1. Load structured profiles and verify counts/badges
{
  const t=setup();
  await t.feature.loadCharacters();
  assert.equal(t.navigationCounts.characters,1);
  assert.equal(t.state.characters.revision,2);
  assert.match(t.get('#characterList').innerHTML,/Lâm Phong/);

  // 2. Editing an AI entry automatically protects (confirms) it
  const detail=t.get('#characterDetail');
  detail.trigger('input',{
    target:{
      value:'Trưởng lão',
      dataset:{fieldKey:'status',entryIndex:'0',entryProp:'value'},
      classList:{toggle(){}},
      closest(){return null;},
    },
  });
  assert.equal(t.state.characterDirty,true);
  assert.equal(t.state.characters.characters[0].fields.status[0].confirmed,true);
  assert.equal(t.state.characters.characters[0].fields.status[0].source,'user');

  // 3. Invalid chapter code blocks save with clear message
  detail.trigger('input',{
    target:{
      value:'bad-chapter',
      dataset:{fieldKey:'status',entryIndex:'0',entryProp:'chapter'},
      classList:{toggle(){}},
      closest(){return null;},
    },
  });
  const callsBefore=t.calls.length;
  await t.feature.saveCharacters();
  assert.equal(t.calls.length,callsBefore);
  assert.match(t.messages.at(-1),/không hợp lệ/);

  // 4. Valid chapter code (without .md) normalizes to v7_c11_s1.md and saves with expected_revision
  detail.trigger('input',{
    target:{
      value:'v7_c11_s1',
      dataset:{fieldKey:'status',entryIndex:'0',entryProp:'chapter'},
      classList:{toggle(){}},
      closest(){return null;},
    },
  });
  await t.feature.saveCharacters();
  const saveCall=t.calls.at(-1);
  assert.equal(saveCall.url,'/api/characters?project=Demo');
  assert.equal(saveCall.body.expected_revision,2);
  assert.equal(saveCall.body.characters[0].fields.status[0].chapter,'v7_c11_s1.md');
  assert.equal(saveCall.body.characters[0].fields.status[0].confirmed,true);
  assert.equal(t.state.characterDirty,false);
  assert.equal(t.state.characters.revision,3);

  // 5. Snapshot preview modal requests /api/characters/snapshot with current chapter
  t.get('#characterSnapshotFilterText').checked=true;
  t.get('#openCharacterSnapshot').onclick();
  await new Promise(resolve=>setTimeout(resolve,10));
  const snapCall=t.calls.at(-1);
  assert.equal(snapCall.url,'/api/characters/snapshot?project=Demo');
  assert.equal(snapCall.body.chapter,'v7_c11_s1.md');
  assert.match(t.get('#characterSnapshotRaw').textContent,/Đệ tử/);

  // 6. Restore backup sends action=restore_backup
  await t.get('#restoreCharactersBackup').onclick();
  const restoreCall=t.calls.at(-1);
  assert.equal(restoreCall.body.action,'restore_backup');
  assert.equal(t.state.characters.revision,4);
}

// 7. Recovery mode shows recovery panel (not empty state), blocks dirtying, and restores cleanly
{
  const t=setup();
  t.state.characters={
    revision:0,
    exists:true,
    count:0,
    backup:true,
    recovery_required:true,
    characters:[],
    chapters:['v1_c1_s1.md'],
    content:'',
  };
  t.state.characterDirty=false;
  t.feature.renderCharacters();

  assert.equal(t.get('#characterEmpty').classList.contains('open'),false);
  assert.match(t.get('#characterDetail').innerHTML,/recoveryRestoreBackup/);
  assert.equal(t.get('#addCharacterButton').disabled,true);
  assert.equal(t.get('#saveCharacters').disabled,true);
  assert.equal(t.get('#restoreCharactersBackup').disabled,false);

  // Attempting to add a character while corrupt must not mark dirty (prevents project-switch lockup)
  t.get('#addCharacterButton').onclick();
  assert.equal(t.state.characterDirty,false);
  assert.equal(t.state.characters.characters.length,0);

  // Clicking the in-panel recovery button restores from .bak and re-enables editing
  t.get('#characterDetail').trigger('click',{
    target:{closest:sel=>sel==='#recoveryRestoreBackup'?{}:null},
  });
  await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(Boolean(t.state.characters.recovery_required),false);
  assert.equal(t.get('#addCharacterButton').disabled,false);
  assert.equal(t.get('#saveCharacters').disabled,false);
  assert.equal(t.state.characters.characters.length,1);
}

// 8. Stale save error from previous project must not toast into newly selected project
{
  let rejectSave;
  const elements=new Map();
  const get=selector=>{
    if(!elements.has(selector))elements.set(selector,createElement(selector.replace(/^#/,'')));
    return elements.get(selector);
  };
  globalThis.document={querySelector:get,querySelectorAll:()=>[]};
  const messages=[];
  const state={
    project:'OldProject',
    projectRevision:1,
    characterDirty:true,
    characters:{revision:1,exists:true,count:1,backup:false,characters:[{id:'ch_1',name:'Alice',fields:{},notes:[],unclassified:''}],chapters:[]},
  };
  const feature=createCharactersFeature({
    api:()=>new Promise((_res,rej)=>{rejectSave=rej;}),
    copyPlainText:async()=>{},
    escapeHtml:String,
    markdownToHtml:String,
    navigationCounts:{characters:1},
    requireProject:()=>true,
    state,
    toast:msg=>messages.push(msg),
  });
  feature.bind();
  const pending=feature.saveCharacters();
  state.project='NewProject';
  state.projectRevision=2;
  rejectSave(new Error('Old project failed'));
  await pending;
  assert.equal(messages.length,0);
}

console.log('character-editor-check-ok');
