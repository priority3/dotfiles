const http=require('http');
const P=Number(process.env.CDP_PORT||9241);
const g=p=>new Promise((r,j)=>http.get({host:'127.0.0.1',port:P,path:p},s=>{let d='';s.on('data',c=>d+=c);s.on('end',()=>r(JSON.parse(d)))}).on('error',j));
let pass=0, fail=0;
const check=(name,cond,detail)=>{ if(cond){pass++;console.log('  ✓ '+name);} else {fail++;console.log('  ✗ '+name+(detail?'  → '+detail:''));} };
(async()=>{
  const t=(await g('/json/list')).find(x=>x.type==='page');
  const ws=new WebSocket(t.webSocketDebuggerUrl);let id=0;const m=new Map();const errs=[];
  const send=(a,b={})=>new Promise((r,j)=>{const i=++id;m.set(i,{r,j});ws.send(JSON.stringify({id:i,method:a,params:b}))});
  await new Promise(r=>ws.addEventListener('open',r));
  ws.addEventListener('message',e=>{const x=JSON.parse(e.data);
    if(x.method==='Runtime.exceptionThrown') errs.push((x.params.exceptionDetails.exception&&x.params.exceptionDetails.exception.description||'').slice(0,100));
    if(x.id&&m.has(x.id)){const{r,j}=m.get(x.id);m.delete(x.id);x.error?j(new Error(x.error.message)):r(x.result)}});
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1100,height:950,deviceScaleFactor:2,mobile:false});
  await send('Page.navigate',{url:'https://shengkao.razet.me/sheet/?id=qa-grid&v='+Date.now()});
  await new Promise(r=>setTimeout(r,3200));

  const ev=async(e)=>{const r=await send('Runtime.evaluate',{expression:e,returnByValue:true});return r.result.value;};
  const txt=async()=>ev('SheetAPI.getText()');
  const cells=async()=>ev('SheetAPI.getStats().chars');
  const cur=async()=>ev(`(()=>{const c=document.querySelector('table.sheet td.cur');if(!c)return null;const rows=[...document.querySelectorAll('table.sheet tr')];return rows.indexOf(c.parentElement)+','+([...c.parentElement.children].indexOf(c)-1)})()`);
  const load=async(s)=>{await ev(`SheetAPI.setText(${JSON.stringify(s)})`);await new Promise(r=>setTimeout(r,200));await ev(`document.getElementById('sink').focus()`);};
  const type=async(s)=>{await send('Input.insertText',{text:s});await new Promise(r=>setTimeout(r,200));};
  async function key(k,code,vk,shift){
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk,modifiers:shift?8:0});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk,modifiers:shift?8:0});
    await new Promise(r=>setTimeout(r,70));
  }
  const clickCell=async(r,c)=>{
    const rc=await ev(`(()=>{const tr=document.querySelectorAll('table.sheet tr')[${r}];const td=tr.children[${c+1}];const b=td.getBoundingClientRect();return Math.round(b.left+b.width/2)+','+Math.round(b.top+b.height/2)})()`);
    const [x,y]=rc.split(',').map(Number);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
    await new Promise(r=>setTimeout(r,200));
  };

  console.log('版本:', await ev(`document.querySelector('.build').textContent`));
  await ev(`localStorage.removeItem('shenlun_sheet_space_migrated')`);

  console.log('\n一、打字');
  await load('');
  await type('我镇');
  check('中文两字 → 2 格', (await cells())===2, 'cells='+await cells());
  await key('1','Digit1',49); await key('3','Digit3',51);
  check('数字 13 → 合成 1 格', (await txt())==='我镇13' && (await cells())===3, 'text='+await txt()+' cells='+await cells());
  await key(' ','Space',32);
  check('空格只换格、不占格', (await cells())===3, 'cells='+await cells());
  await key('8','Digit8',56); await key('5','Digit5',53);
  check('85 落在新的一格', (await cells())===4, 'cells='+await cells());
  await key('.','Period',190); await key('6','Digit6',54);
  check('85.6 仍是一格', (await cells())===4, 'cells='+await cells());
  await type('，');
  check('中文标点独立一格', (await cells())===5, 'cells='+await cells());

  console.log('\n二、移动');
  await load('　　一二三四五六七八九十\n　　第二行');
  await ev(`SheetAPI.setCaret(SheetAPI.getText().indexOf('\\n'))`);
  check('光标停在行尾 = 第 1 行第 13 格', (await cur())==='0,12', 'cur='+await cur());
  await key('ArrowRight','ArrowRight',39);
  check('→ 留本行，不跳下一行', (await cur())==='0,13', 'cur='+await cur());
  await key('ArrowRight','ArrowRight',39);
  check('再 → 第 15 格', (await cur())==='0,14', 'cur='+await cur());
  await key('ArrowLeft','ArrowLeft',37);
  check('← 回第 14 格', (await cur())==='0,13', 'cur='+await cur());
  await key('ArrowDown','ArrowDown',40);
  check('↓ 下一行同列', (await cur())==='1,13', 'cur='+await cur());
  await key('ArrowUp','ArrowUp',38);
  check('↑ 回上一行同列', (await cur())==='0,13', 'cur='+await cur());
  await key('Home','Home',36);
  check('Home 到行首', (await cur())==='0,0', 'cur='+await cur());

  console.log('\n三、点击定位 + 打字');
  await load('　　一二三四五六七八九十\n　　第二行');
  await clickCell(0,5);
  check('点第 1 行第 6 格，光标到位', (await cur())==='0,5', 'cur='+await cur());
  await type('甲');
  check('字落在第 6 格', (await txt()).split('\n')[0][5]==='甲', JSON.stringify((await txt()).split('\n')[0]));
  await clickCell(0,20);
  const cBefore=await cells();
  check('点空白格不立刻加字数', (await cells())===cBefore && (await cur())==='0,20', 'cells='+await cells()+' cur='+await cur());
  await type('乙');
  const L=await txt();
  check('空白格打字不跑到最后一行', L.split('\n').length===2 && L.split('\n')[0].endsWith('乙'), JSON.stringify(L));

  console.log('\n四、删除');
  await load('　　甲乙丙丁');
  await ev(`SheetAPI.setCaret(3)`);
  await key('Backspace','Backspace',8);
  check('退格删光标前一个字', (await txt())==='　　乙丙丁', JSON.stringify(await txt()));
  await ev(`SheetAPI.setCaret(2)`);
  await key('Delete','Delete',46);
  check('Delete 删光标后一个字', (await txt())==='　　丙丁', JSON.stringify(await txt()));
  await ev(`SheetAPI.setCaret(SheetAPI.getText().length)`);
  for (let i=0;i<4;i++) await key('Backspace','Backspace',8);
  check('连按退格清空', (await txt())==='', JSON.stringify(await txt()));

  console.log('\n五、多行与折行');
  await load('　　第一段内容\n　　第二段内容');
  await ev(`SheetAPI.setCaret(6)`);
  await type('Z');
  check('第 1 段中间插字', (await txt()).split('\n')[0]==='　　第一段内Z容', JSON.stringify(await txt()));
  await load('　　这是一段很长很长很长很长的文字用来测试自动折行是否正常工作一二三四五六七八九十');
  await ev(`SheetAPI.setCaret(SheetAPI.getText().length)`);
  await key('ArrowUp','ArrowUp',38);
  const up=await cur();
  check('长段落折行后 ↑ 能上一行', up && Number(up.split(',')[0])===0, 'cur='+up);

  console.log('\n六、异常');
  check('全程无 JS 异常', errs.length===0, errs.slice(0,2).join(' | '));
  console.log(`\n合计：${pass} 通过 / ${fail} 失败`);
  ws.close();
  process.exit(fail?1:0);
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
