import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { mkdir } from 'node:fs/promises';
const out='D:/eGym/temp/broadcast-implementation';
await mkdir(out,{recursive:true});
const browser=await chromium.launch();
try {
 const context=await browser.newContext({viewport:{width:1920,height:1080}});
 await context.routeWebSocket('**/*', ws=>ws.close());
 await context.route('**/*',route=>new URL(route.request().url()).pathname.startsWith('/api/')?route.fulfill({status:503,json:{detail:'Isolated visual test'}}):route.continue());
 const page=await context.newPage();
 page.on('pageerror',error=>console.log('PAGE ERROR: '+error.stack));
 await page.goto('http://127.0.0.1:5173/',{waitUntil:'networkidle'});
 await page.evaluate(async()=>{
  const {useAppStore}=await import('/src/stores/app-store.ts');
  const {useRuntimeStore}=await import('/src/stores/runtime-store.ts');
  useAppStore.setState({selectedUserId:'alexey'});
  useRuntimeStore.getState().initializeSession({source:'today',calibrationState:'saved'});
  useRuntimeStore.getState().startExercise();
 });
 for(const route of ['exercise-session?source=today&calibration=saved','settings','profile','fatigue']){
  await page.goto('http://127.0.0.1:5173/'+route,{waitUntil:'networkidle'});
  const expected=route==='fatigue'?null:'broadcast-blue';
  const theme=await page.locator('html').getAttribute('data-forma-theme');
    if(theme!==expected){console.log(await page.locator('body').innerText());throw new Error('Theme mismatch '+route+': '+theme);}
  await page.screenshot({path:out+'/'+route.split('?')[0]+'.png'});
  console.log(JSON.stringify({route,theme,stop:await page.getByRole('button',{name:'Аварийная остановка',exact:true}).count()}));
 }
 await page.setViewportSize({width:1280,height:720});
 await page.goto('http://127.0.0.1:5173/exercise-session?source=today&calibration=saved',{waitUntil:'networkidle'});
 await page.screenshot({path:out+'/session-1280.png'});
}finally{await browser.close();}