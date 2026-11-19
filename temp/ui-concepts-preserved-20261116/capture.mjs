import { chromium } from '../../frontend/node_modules/playwright-core/index.mjs';
const browser = await chromium.launch({headless:true});
try {
  const context = await browser.newContext({viewport:{width:1920,height:1080}});
  await context.routeWebSocket('**/*', ws => ws.close());
  await context.route('**/*', async route => {
    if (new URL(route.request().url()).pathname.startsWith('/api/')) {
      await route.fulfill({status:200,contentType:'application/json',body:'null'});
    } else await route.continue();
  });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:5173/',{waitUntil:'networkidle'});
  const state = await page.evaluate(async () => {
    const {useAppStore} = await import('/src/stores/app-store.ts');
    const {useRuntimeStore} = await import('/src/stores/runtime-store.ts');
    useAppStore.setState({selectedUserId:'alexey'});
    useRuntimeStore.getState().initializeSession({source:'today',calibrationState:'saved'});
    useRuntimeStore.getState().startExercise();
    return {view:useRuntimeStore.getState().session?.view,exercise:useRuntimeStore.getState().session?.exercises[0]?.name};
  });
  console.log(JSON.stringify(state));
  await page.goto('http://127.0.0.1:5173/exercise-session?source=today&calibration=saved',{waitUntil:'networkidle'});
  await page.screenshot({path:'D:/eGym/temp/ui-concepts-preserved-20261116/reference-current.png'});
  console.log((await page.locator('body').innerText()).slice(0,5000));
} finally {await browser.close();}