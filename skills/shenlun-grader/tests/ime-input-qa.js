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
  await send('Page.navigate',{url:'file:///Users/moka/WorkBuddy/2026-10-28-17-07-26/%E7%94%B3%E8%AE%BA%E7%AD%94%E9%A2%98%E5%8D%A1.html'});
  await new Promise(r=>setTimeout(r,1500));
  await send('Runtime.evaluate',{expression:`localStorage.clear();location.reload()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,1600));
  const ev=async(e)=>{const r=await send('Runtime.evaluate',{expression:e,returnByValue:true});return r.result.value;};
  const txt=async()=>ev('SheetAPI.getText()');
  const key=async(k,code,vk,opt={})=>{
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk,isComposing:!!opt.isComposing});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk});
    await new Promise(r=>setTimeout(r,80));
  };

  // 模拟拼音 yue → 月：先按 y（此时还没开始组合），再走组合事件
  await ev(`SheetAPI.setText('');document.getElementById('sink').focus()`);
  await key('y','KeyY',89);                       // 拼音首字母
  check('按 y 不再直接落格', (await txt())==='', 'text='+JSON.stringify(await txt()));
  await ev(`(()=>{const s=document.getElementById('sink');
    s.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
    s.value='yue';
    s.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,data:'yue'}));
    s.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'月'}));
  })()`);
  await new Promise(r=>setTimeout(r,200));
  check('拼音 yue 上屏为「月」，没有 y', (await txt())==='月', 'text='+JSON.stringify(await txt()));

  // 数字仍需拦截
  await ev(`SheetAPI.setText('')`);
  await ev(`document.getElementById('sink').focus()`);
  await key('8','Digit8',56); await key('5','Digit5',53);
  check('85 仍直接落格', (await txt())==='85', 'text='+JSON.stringify(await txt()));
  await key('.','Period',190);
  check('数字后的 . 落格', (await txt())==='85.', 'text='+JSON.stringify(await txt()));
  await key('6','Digit6',54);
  check('85.6 连成', (await txt())==='85.6', 'text='+JSON.stringify(await txt()));
  await key(' ','Space',32);
  check('空格换格', (await txt())==='85.6 ', 'text='+JSON.stringify(await txt()));

  // 汉字后的标点不拦（交给输入法出中文标点）
  await ev(`SheetAPI.setText('我镇')`);
  await ev(`document.getElementById('sink').focus()`);
  await key('.','Period',190);
  check('汉字后的 . 不拦截', (await txt())==='我镇', 'text='+JSON.stringify(await txt()));

  // 组合中按数字（选词）不能拦
  await ev(`SheetAPI.setText('')`);
  await ev(`(()=>{const s=document.getElementById('sink');s.focus();
    s.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));s.value='yue';})()`);
  await key('3','Digit3',51);
  check('组合中按数字不拦（选词）', (await txt())==='', 'text='+JSON.stringify(await txt()));
  await ev(`(()=>{const s=document.getElementById('sink');
    s.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'月'}));})()`);
  await new Promise(r=>setTimeout(r,150));
  check('选词后正常上屏', (await txt())==='月', 'text='+JSON.stringify(await txt()));

  // 拼音组合中按退格 / Delete / 回车：都不能动格子里的字（按真实时序模拟）
  await ev(`SheetAPI.setText('我镇主要经济')`);
  await ev(`document.getElementById('sink').focus()`);
  const imeKey = async (k, code, vk) => {
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk,isComposing:true});
    // 输入法内部把拼音串删掉一个字母，并派发 isComposing 的 input
    await ev(`(()=>{const s=document.getElementById('sink');
      s.value='zh';
      s.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,data:null,inputType:'deleteContentBackward'}));})()`);
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:k,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk});
    await new Promise(r=>setTimeout(r,120));
  };
  await ev(`(()=>{const s=document.getElementById('sink');
    s.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));s.value='zhu';})()`);
  await imeKey('Backspace','Backspace',8);
  check('拼音组合中按退格不删格子里的字', (await txt())==='我镇主要经济', 'text='+JSON.stringify(await txt()));
  await imeKey('Delete','Delete',46);
  check('拼音组合中按 Delete 不删字', (await txt())==='我镇主要经济', 'text='+JSON.stringify(await txt()));
  await imeKey('Enter','Enter',13);
  check('拼音组合中按回车不换行', (await txt())==='我镇主要经济', 'text='+JSON.stringify(await txt()));
  await imeKey('ArrowLeft','ArrowLeft',37);
  check('拼音组合中按方向键不动光标', (await ev('SheetAPI.getCaret()'))===6, 'caret='+await ev('SheetAPI.getCaret()'));
  await ev(`(()=>{const s=document.getElementById('sink');s.value='';
    s.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'柱'}));})()`);
  await new Promise(r=>setTimeout(r,150));
  check('上屏只追加「柱」一个字', (await txt())==='我镇主要经济柱', 'text='+JSON.stringify(await txt()));
  await key('Backspace','Backspace',8);
  check('组合结束后退格正常', (await txt())==='我镇主要经济', 'text='+JSON.stringify(await txt()));

  check('无 JS 异常', errs.length===0, errs[0]);
  console.log(`\n${pass} 通过 / ${fail} 失败`);
  ws.close(); process.exit(fail?1:0);
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
