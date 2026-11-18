import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createSettingsFeature } from '../web/features/settings.js';
import { createChapterImportFeature } from '../web/features/chapter-import.js';

const items=JSON.parse(readFileSync(0,'utf8'));
const elements=new Map();
const element=selector=>{
  if(!elements.has(selector))elements.set(selector,{
    value:'',innerHTML:'',textContent:'',disabled:false,files:[],style:{},dataset:{},
    classList:{add(){},remove(){},toggle(){}},
  });
  return elements.get(selector);
};
let controls=[];
globalThis.document={querySelector:element,querySelectorAll:selector=>selector==='[data-python-setting]'?controls:[]};
const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const notices=[];
let saved;
const settings=createSettingsFeature({
  api:async(url,options)=>{
    if(options?.method==='POST'){saved=JSON.parse(options.body).values;return {items};}
    return {items};
  },escapeHtml,refreshUpdate:async()=>{},showView(){},toast:message=>notices.push(message),
});
settings.render(items);
settings.openGroup('import');
assert.match(element('#settingsTabs').innerHTML,/Nhập truyện/);
assert.match(element('#pythonSettingsFields').innerHTML,/pipeline_import_model/);
assert.match(element('#pythonSettingsFields').innerHTML,/data-pipeline-stage="import" open/);
assert.doesNotMatch(element('#pythonSettingsFields').innerHTML,/data-pipeline-stage="translate"/);
controls=[{dataset:{pythonSetting:'pipeline_import_provider'},value:'openai-api'},
  {dataset:{pythonSetting:'pipeline_import_model'},value:'chosen-model'},
  {dataset:{pythonSetting:'pipeline_import_thinking'},value:'high'}];
settings.bind();
await element('#savePythonSettings').onclick();
assert.equal(saved.pipeline_import_model,'chosen-model');
assert.equal(saved.pipeline_import_provider,'openai-api');
controls=[];

let request,fail=false;
const feature=createChapterImportFeature({
  api:async(url,options)=>{
    request={url,options};
    assert.equal(element('#analyzeChapterImport').disabled,true);
    assert.equal(element('#cancelChapterImport').disabled,true);
    if(fail)throw Error('AI lỗi thử nghiệm');
    return {source_from:0,source_to:0,target_volume:1,target_start:0,anchors:0,
      chapters:[{source_index:0,title:'Chương <một>',selected:true,source_line:12,end_line:50,
        characters:300,excerpt:'Nội dung <gốc>',warning:'Kiểm tra'}]};
  },escapeHtml,getProject:()=> 'Demo',loadChapters:async()=>{},openChapter:async()=>{},
  toast:message=>notices.push(message),
});
feature.bind();
element('#chapterImportFile').files=[{name:'sample.txt'}];
element('#chapterImportSegmentLimit').value='5000';
element('#chapterImportSplitMethod').value='ai';
await element('#analyzeChapterImport').onclick();
assert.equal(new URL(request.url,'http://localhost').searchParams.get('split_method'),'ai');
assert.match(element('#chapterImportRows').innerHTML,/Dòng 12–50/);
assert.match(element('#chapterImportRows').innerHTML,/Nội dung &lt;gốc>/);
assert.equal(element('#cancelChapterImport').disabled,false);
element('#chapterImportFile').files=[{name:'sample.epub'}];
await element('#analyzeChapterImport').onclick();
assert.equal(new URL(request.url,'http://localhost').searchParams.get('split_method'),'auto');
fail=true;
await element('#analyzeChapterImport').onclick();
assert.equal(element('#analyzeChapterImport').disabled,false);
assert.equal(element('#cancelChapterImport').disabled,false);
assert.ok(notices.includes('AI lỗi thử nghiệm'));
console.log('ai-import-ui-ok');
