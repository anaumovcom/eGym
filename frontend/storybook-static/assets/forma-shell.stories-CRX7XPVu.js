import{j as e}from"./iframe-Bd_hAZ-r.js";import{L as o,T as n,m as s,E as t,F as i}from"./forma-shell-Crep7I2c.js";import"./preload-helper-PPVm8Dsz.js";import"./cn-BHwzA9XM.js";import"./status-components-CsbB3DRZ.js";import"./triangle-alert-BTEFwDcb.js";const h={title:"Shared/Forma Shell",parameters:{layout:"fullscreen"},tags:["autodocs"]},r={render:()=>e.jsxs("div",{className:"grid gap-6 xl:grid-cols-[260px_1fr]",children:[e.jsx(o,{}),e.jsxs("div",{className:"space-y-6",children:[e.jsx(n,{userName:"Алексей",machine:s.ready,onStop:()=>{}}),e.jsx(t,{onClick:()=>{}})]})]})},a={render:()=>e.jsx(i,{userName:"Алексей",machine:s.ready,onStop:()=>{},children:e.jsx("section",{className:"glass-panel rounded-[32px] p-8 text-white/75",children:"В Storybook shell уже доступен с верхней системной панелью и левым меню."})})};r.parameters={...r.parameters,docs:{...r.parameters?.docs,source:{originalSource:`{
  render: () => <div className="grid gap-6 xl:grid-cols-[260px_1fr]">\r
      <LeftNavigationMenu />\r
      <div className="space-y-6">\r
        <TopSystemBar userName="Алексей" machine={machineScenarios.ready} onStop={() => undefined} />\r
        <EmergencyStopButton onClick={() => undefined} />\r
      </div>\r
    </div>
}`,...r.parameters?.docs?.source}}};a.parameters={...a.parameters,docs:{...a.parameters?.docs,source:{originalSource:`{
  render: () => <FormaShell userName="Алексей" machine={machineScenarios.ready} onStop={() => undefined}>\r
      <section className="glass-panel rounded-[32px] p-8 text-white/75">В Storybook shell уже доступен с верхней системной панелью и левым меню.</section>\r
    </FormaShell>
}`,...a.parameters?.docs?.source}}};const S=["Components","FullShell"];export{r as Components,a as FullShell,S as __namedExportsOrder,h as default};
