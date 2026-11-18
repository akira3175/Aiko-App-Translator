import assert from 'node:assert/strict';
import {inlineDiff,highlightedText,reviewHunks} from '../web/features/polish-diff.js';

const pieces=(text,ranges)=>ranges.map(({from,to})=>text.slice(from,to));
const common=(text,ranges)=>{let end=0,result='';for(const {from,to} of ranges){assert.ok(from>=end&&to>from&&to<=text.length);result+=text.slice(end,from);end=to;}return result+text.slice(end);};
const old='Đây là đối sách an toàn nhưng quá thụ động.',next='Đây là phương án an toàn nhưng quá bị động.';
const diff=inlineDiff(old,next);
assert.deepEqual(pieces(old,diff.removed),['đối','sách','thụ']);
assert.deepEqual(pieces(next,diff.added),['phương','án','bị']);
for(const [a,b] of [[old,next],['Có hai lựa chọn.','Chỉ có hai lựa chọn.'],['“Xin chào!”','“Xin chào?”'],['','Thêm mới'],['Xóa',''],['Không đổi','Không đổi'],['👩‍💻 đọc sách.','👩‍💻 viết sách.'],['a\n\nb','a\nb'],['ma\u0301','ma\u0300'],['A A B A','A B B A']]){
  const {removed,added}=inlineDiff(a,b);
  assert.equal(common(a,removed),common(b,added));
}
assert.deepEqual(inlineDiff('Không đổi','Không đổi'),{removed:[],added:[]});
const longOld='Giữ '+('cũ '.repeat(10000))+'cuối',longNew='Giữ '+('mới '.repeat(10000))+'cuối';
const longDiff=inlineDiff(longOld,longNew);
assert.equal(common(longOld,longDiff.removed),common(longNew,longDiff.added));
assert.equal(longDiff.removed.length,1,'Large rewrites must use bounded diff work');
const escape=text=>text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
assert.equal(highlightedText('<script>',[{from:0,to:8}],'removed',escape),'<mark class="removed">&lt;script&gt;</mark>');
console.log('polish-diff checks passed: exact words, punctuation, Unicode offsets, whitespace, insertion/deletion, bounded long passages, safe HTML');

function checkHunks(original,current,proposed){
  const hunks=reviewHunks(original,current,proposed);
  for(const [key,expected] of [['old',original],['ai',proposed]]){
    let result=current;
    for(const hunk of [...hunks].reverse()){
      assert.equal(current.slice(hunk.from,hunk.to),hunk.value);
      result=result.slice(0,hunk.from)+hunk[key]+result.slice(hunk.to);
    }
    assert.equal(result,expected,`Restoring ${key} must reconstruct the whole document`);
  }
}
for(const args of [
  ['a\nb\nc\n','a\ncustom\nc\n','a\nAI\nc\n'],
  ['a\nb\nc\n','a\nc\n','a\nB\nextra\nc\n'],
  ['a\nb\nc\n','a\nmanual\nb\nc\n','a\nb\nAI\nc\n'],
  ['same','same','same\nadded'],['old\n','', 'AI\n'],['','new','AI'],
  ['A\nB\nC\nD\n','A\nB\nC\nmanual\n','A\nAI B\nAI C\nD\n'],
])checkHunks(...args);
let seed=5721;
const random=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n;};
for(let i=0;i<300;i++){
  const original=Array.from({length:random(12)},()=>['a\n','b\n','\n','Chữ Việt\n'][random(4)]);
  const edit=()=>{const lines=[...original];for(let j=0;j<3;j++)lines.splice(random(lines.length+1),random(3),...Array.from({length:random(3)},()=>['thêm\n','a\n','\n'][random(3)]));return lines.join('');};
  checkHunks(original.join(''),edit(),edit());
}
console.log('inline review hunk checks passed: restore AI/old after cross-paragraph edits, insertions, deletions, EOF, 300 seeded cases');
