import {chromium} from "@playwright/test";
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const root=fileURLToPath(new URL('../..',import.meta.url));
const jobs=[["assets/intpot-lockup.svg", ["intpot_image.webp", "website/src/assets/intpot_image.webp"], 1200, 900], ["website/public/social-card.svg", ["website/public/social-card-v2.png"], 1200, 630]];
const check=process.argv.includes('--check');
const browser=await chromium.launch();
try {
 const page=await browser.newPage({deviceScaleFactor:1});
 for(const [source,targets,width,height]of jobs){
  await page.setViewportSize({width,height});
  const svg=await readFile(resolve(root,source),'utf8');
  assert.match(svg, /<text[^>]*fill="#F4F2EA"[^>]*>int<tspan fill="#F2B84B">pot<\/tspan><\/text>/);
  if(!check){
   await page.setContent('<style>html,body{margin:0;padding:0}</style>'+svg);
   await page.evaluate(()=>document.fonts.ready);
   const png=await page.screenshot();
   for(const target of targets){
    if(target.endsWith('.webp')){
     const data=await page.evaluate(async data=>{const im=new Image();im.src='data:image/png;base64,'+data;await im.decode();const c=document.createElement('canvas');c.width=im.naturalWidth;c.height=im.naturalHeight;c.getContext('2d').drawImage(im,0,0);return c.toDataURL('image/webp',.92).split(',')[1]},png.toString('base64'));
     await writeFile(resolve(root,target),Buffer.from(data,'base64'));
    }else await writeFile(resolve(root,target),png);
   }
  }
  for(const target of targets){
   const bytes=await readFile(resolve(root,target));
   const data='data:image/'+(target.endsWith('.webp')?'webp':'png')+';base64,'+bytes.toString('base64');
   const counts=await page.evaluate(async data=>{const im=new Image();im.src=data;await im.decode();const c=document.createElement('canvas');c.width=im.naturalWidth;c.height=im.naturalHeight;const ctx=c.getContext('2d');ctx.drawImage(im,0,0);const{data:rgba}=ctx.getImageData(0,0,c.width,c.height);const social=c.height===630,left=social?470:510,top=social?235:330,bottom=social?360:470;let white=0,gold=0;for(let y=top;y<bottom;y++)for(let x=left;x<1120;x++){const k=(y*c.width+x)*4;if(x<left+100&&Math.abs(rgba[k]-244)<14&&Math.abs(rgba[k+1]-242)<14&&Math.abs(rgba[k+2]-234)<14)white++;if(x>left+200&&Math.abs(rgba[k]-242)<14&&Math.abs(rgba[k+1]-184)<14&&Math.abs(rgba[k+2]-75)<14)gold++;}return{width:c.width,height:c.height,white,gold}},data);
   assert.equal(counts.width,width);assert.equal(counts.height,height);assert.ok(counts.white>100,target+': off-white prefix required');assert.ok(counts.gold>100,target+': amber pot pixels required within wordmark bounds');console.log(target,JSON.stringify(counts));
  }
 }
}finally{await browser.close()}
