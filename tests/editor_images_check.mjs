import assert from 'node:assert/strict';
import {createEditorFeature} from '../web/features/editor.js';

const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const {markdownToHtml}=createEditorFeature({state:{project:'Marigold AI'},escapeHtml});

// Translation-only images must render even when the raw chapter has no images.
const marker='![image](../image/v1_c6_s1_line18.webp)';
assert.match(markdownToHtml(marker,[]),/src="\/api\/image\/v1_c6_s1_line18\.webp\?project=Marigold%20AI"/);

// The image filename, rather than the raw chapter's order, selects the image.
const images=[{id:'wrong',url:'/api/image/wrong.png'}];
const html=markdownToHtml('![second](image/second.png)\n![first](../image/first.webp)',images);
assert.ok(html.indexOf('/api/image/second.png')<html.indexOf('/api/image/first.webp'));
assert.ok(!html.includes('/api/image/wrong.png'));
assert.match(markdownToHtml('[img]https://example.com/image.png[/img]',[{id:'remote-1',url:'https://example.com/image.png'}]),/src="https:\/\/example.com\/image.png"/);
console.log('editor-images-check-ok');
