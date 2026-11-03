const http=require('http');
const P=Number(process.env.CDP_PORT||9241);
const g=p=>new Promise((r,j)=>http.get({host:'127.0.0.1',port:P,path:p},s=>{let d='';s.on('data',c=>d+=c);s.on('end',()=>r(JSON.parse(d)))}).on('error',j));
let pass=0,fail=0;
const check=(n,c,d)=>{if(c){pass++;console.log('  ✓ '+n);}else{fail++;console.log('  ✗ '+n+(d?'  → '+d:''));}};
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
  await send('Page.navigate',{url:'https://shengkao.razet.me/sheet/?id=qa-lastrow&v='+Date.now()});
  await new Promise(r=>setTimeout(r,3200));
  const ev=async(e)=>{const r=await send('Runtime.evaluate',{expression:e,returnByValue:true});return r.result.value;};
  const lines=async()=>(await ev('SheetAPI.getText()')).split('\n').length;
  const clickCell=async(r,c)=>{
    const rc=await ev(`(()=>{const tr=document.querySelectorAll('table.sheet tr')[${r}];const td=tr.children[${c+1}];const b=td.getBoundingClientRect();return Math.round(b.left+b.width/2)+','+Math.round(b.top+b.height/2)})()`);
    const [x,y]=rc.split(',').map(Number);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
    await new Promise(r2=>setTimeout(r2,200));
  };
  const back=async()=>{await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8,nativeVirtualKeyCode:8});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8,nativeVirtualKeyCode:8});await new Promise(r=>setTimeout(r,150));};

  // 一段刚好 25 格的行 + 后面的长行（用来触发行数偏移）
  await ev(`SheetAPI.setText('一二三四五六七八九十一二三四五六七八九十一二三四五\\n　　第二段内容比较长一些用来测试折行是否会影响行号计算一二三四五六七八九十')`);
  await new Promise(r=>setTimeout(r,300));
  const base=await lines();
  check('初始 2 行', base===2, 'lines='+base);

  // 点最后一行的最后内容行再打字，不应凭空多行
  const rowsBefore=await ev(`computeLayout(SheetAPI.getText()).rows.length`);
  await clickCell(rowsBefore-1, 3);
  const rowsAfterClick=await ev(`computeLayout(SheetAPI.getText()).rows.length`);
  check('点最后一行不改变行数', rowsAfterClick===rowsBefore, rowsBefore+'→'+rowsAfterClick);

  // 点内容下方第一行打字：只会多一行
  await clickCell(rowsBefore, 0);
  await send('Input.insertText',{text:'X'});
  await new Promise(r=>setTimeout(r,250));
  check('点下方空行打一个字只新增 1 行', (await lines())===base+1, 'lines='+await lines());

  // 一次退格连空行一起收掉
  await back();
  check('一次退格回到原行数', (await lines())===base, 'lines='+await lines());

  // 点到很下面（第 10 行）：吸附，不凭空造 8 个空行
  await clickCell(9, 0);
  await send('Input.insertText',{text:'Y'});
  await new Promise(r=>setTimeout(r,250));
  check('点很远的空行最多只新增 1 行', (await lines())<=base+1, 'lines='+await lines());

  check('无 JS 异常', errs.length===0, errs[0]);
  console.log(`\n${pass} 通过 / ${fail} 失败`);
  ws.close(); process.exit(fail?1:0);
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
