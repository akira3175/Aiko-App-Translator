// UTF-16 offsets match CodeMirror's document positions; marks never alter text.
export function inlineDiff(oldText,newText) {
  const tokenize=text=>[...text.matchAll(/[\p{L}\p{M}\p{N}_]+|\s+|[^\p{L}\p{M}\p{N}_\s]/gu)].map(match=>({text:match[0],start:match.index,end:match.index+match[0].length}));
  const old=tokenize(oldText), next=tokenize(newText);
  let start=0,endOld=old.length,endNew=next.length;
  while(start<endOld&&start<endNew&&old[start].text===next[start].text)start++;
  while(endOld>start&&endNew>start&&old[endOld-1].text===next[endNew-1].text){endOld--;endNew--;}
  const removed=[],added=[];
  function add(ranges,token) {
    const last=ranges.at(-1);
    if(last&&last.to===token.start)last.to=token.end;
    else ranges.push({from:token.start,to:token.end});
  }
  const n=endOld-start,m=endNew-start;
  // Bound work for very long, entirely rewritten passages. Retain common edges.
  if(n*m>250000){
    if(n)removed.push({from:old[start].start,to:old[endOld-1].end});
    if(m)added.push({from:next[start].start,to:next[endNew-1].end});
    return {removed,added};
  }
  const width=m+1,table=new Uint32Array((n+1)*width);
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--){
    table[i*width+j]=old[start+i].text===next[start+j].text
      ?1+table[(i+1)*width+j+1]:Math.max(table[(i+1)*width+j],table[i*width+j+1]);
  }
  let i=0,j=0;
  while(i<n||j<m){
    if(i<n&&j<m&&old[start+i].text===next[start+j].text){i++;j++;}
    else if(i<n&&(j===m||table[(i+1)*width+j]>=table[i*width+j+1]))add(removed,old[start+i++]);
    else add(added,next[start+j++]);
  }
  return {removed,added};
}

export function highlightedText(text,ranges,className,escapeHtml) {
  let end=0;
  const parts=ranges.map(range=>{
    const html=escapeHtml(text.slice(end,range.from))+`<mark class="${className}">${escapeHtml(text.slice(range.from,range.to))}</mark>`;
    end=range.to;return html;
  });
  return parts.join('')+escapeHtml(text.slice(end));
}

export function lineChanges(original,modified) {
  const lines=text=>text.match(/[^\n]*\n|[^\n]+$/g)||[];
  const old=lines(original),next=lines(modified);
  const offsets=items=>{const result=[0];for(const line of items)result.push(result.at(-1)+line.length);return result;};
  const a=offsets(old),b=offsets(next);
  let start=0,oldEnd=old.length,newEnd=next.length;
  while(start<oldEnd&&start<newEnd&&old[start]===next[start])start++;
  while(oldEnd>start&&newEnd>start&&old[oldEnd-1]===next[newEnd-1]){oldEnd--;newEnd--;}
  const n=oldEnd-start,m=newEnd-start,width=m+1;
  if(!n&&!m)return [];
  const range=(i,j,k,l)=>({oldFrom:a[i],oldTo:a[j],newFrom:b[k],newTo:b[l]});
  if(n*m>2000000)return [range(start,oldEnd,start,newEnd)];
  const table=new Uint32Array((n+1)*width);
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)table[i*width+j]=old[start+i]===next[start+j]?1+table[(i+1)*width+j+1]:Math.max(table[(i+1)*width+j],table[i*width+j+1]);
  const changes=[];
  let i=0,j=0,pending=null;
  const finish=()=>{if(pending){changes.push(range(start+pending.i,start+i,start+pending.j,start+j));pending=null;}};
  while(i<n||j<m){
    if(i<n&&j<m&&old[start+i]===next[start+j]){finish();i++;j++;}
    else{
      pending??={i,j};
      if(i<n&&(j===m||table[(i+1)*width+j]>=table[i*width+j+1]))i++;else j++;
    }
  }
  finish();return changes;
}

// Merge the AI and current edits in original coordinates. Every resulting range
// contains complete edits from both versions, so restore never duplicates text
// when the user splits, joins, inserts or deletes paragraphs across old blocks.
export function reviewHunks(original,current,proposed) {
  const edited=lineChanges(original,current),suggested=lineChanges(original,proposed);
  const groups=[];
  for(const change of [...edited,...suggested].sort((a,b)=>a.oldFrom-b.oldFrom||a.oldTo-b.oldTo)){
    const previous=groups.at(-1);
    if(previous&&change.oldFrom<=previous.oldTo)previous.oldTo=Math.max(previous.oldTo,change.oldTo);
    else groups.push({oldFrom:change.oldFrom,oldTo:change.oldTo});
  }
  function boundary(offset,changes,end) {
    let delta=0;
    for(const change of changes){
      if(!end&&change.oldFrom===offset)return change.newFrom;
      if(change.oldTo<=offset)delta=change.newTo-change.oldTo;
      else break;
    }
    return offset+delta;
  }
  return groups.map(group=>{
    const from=boundary(group.oldFrom,edited,false),to=boundary(group.oldTo,edited,true);
    const aiFrom=boundary(group.oldFrom,suggested,false),aiTo=boundary(group.oldTo,suggested,true);
    return {...group,from,to,old:original.slice(group.oldFrom,group.oldTo),value:current.slice(from,to),ai:proposed.slice(aiFrom,aiTo)};
  });
}
