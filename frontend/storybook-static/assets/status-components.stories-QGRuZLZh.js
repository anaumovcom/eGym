import{j as e}from"./iframe-Bd_hAZ-r.js";import{M as s,D as t,S as n,R as r,W as i,B as d,P as c}from"./status-components-CsbB3DRZ.js";import"./preload-helper-PPVm8Dsz.js";import"./cn-BHwzA9XM.js";import"./triangle-alert-BTEFwDcb.js";const x={title:"Shared/Status Components",parameters:{layout:"padded"},tags:["autodocs"]},a={render:()=>e.jsxs("div",{className:"grid gap-6",children:[e.jsxs("div",{className:"flex flex-wrap gap-3",children:[e.jsx(s,{label:"Тренажёр готов",tone:"success"}),e.jsx(t,{label:"Правый привод: требует проверки",tone:"warning"}),e.jsx(n,{label:"Аварийная остановка: активна",tone:"danger"})]}),e.jsxs("div",{className:"flex gap-6",children:[e.jsx(r,{value:78}),e.jsx(r,{value:84,accent:"green"})]}),e.jsx(i,{title:"Нужно внимание",description:"Перед стартом требуется подтвердить готовность оборудования."}),e.jsx(d,{title:"Старт заблокирован",description:"Ошибка правого привода не позволяет начать тренировку."}),e.jsx(c,{children:e.jsx("div",{className:"text-sm text-white/70",children:"PrimaryActionBar используется как контейнер для закреплённого блока действий и краткой аналитики."})})]})};a.parameters={...a.parameters,docs:{...a.parameters?.docs,source:{originalSource:`{
  render: () => <div className="grid gap-6">\r
      <div className="flex flex-wrap gap-3">\r
        <MachineStatusBadge label="Тренажёр готов" tone="success" />\r
        <DriveStatusBadge label="Правый привод: требует проверки" tone="warning" />\r
        <SafetyStatusBadge label="Аварийная остановка: активна" tone="danger" />\r
      </div>\r
      <div className="flex gap-6">\r
        <ReadinessIndicator value={78} />\r
        <ReadinessIndicator value={84} accent="green" />\r
      </div>\r
      <WarningBanner title="Нужно внимание" description="Перед стартом требуется подтвердить готовность оборудования." />\r
      <BlockingAlert title="Старт заблокирован" description="Ошибка правого привода не позволяет начать тренировку." />\r
      <PrimaryActionBar>\r
        <div className="text-sm text-white/70">PrimaryActionBar используется как контейнер для закреплённого блока действий и краткой аналитики.</div>\r
      </PrimaryActionBar>\r
    </div>
}`,...a.parameters?.docs?.source}}};const v=["Overview"];export{a as Overview,v as __namedExportsOrder,x as default};
