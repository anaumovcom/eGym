import{r as o,j as e}from"./iframe-Bd_hAZ-r.js";import{B as t}from"./button-C3AxX0-N.js";import{M as s,C as n,P as c,S as d,A as l,T as p,E as m}from"./surface-components-z0s6F6sO.js";import"./preload-helper-PPVm8Dsz.js";import"./cn-BHwzA9XM.js";import"./index-9k8OnwZp.js";const j={title:"Shared/Surface Components",parameters:{layout:"padded"},tags:["autodocs"]},r={render:()=>{const[i,a]=o.useState(!1);return e.jsxs("div",{className:"grid gap-6 xl:grid-cols-2",children:[e.jsxs("div",{className:"space-y-4",children:[e.jsxs("div",{className:"flex flex-wrap gap-3",children:[e.jsx(t,{onClick:()=>a(!0),children:"Открыть EmergencyStopOverlay"}),e.jsx(s,{title:"Модалка",description:"Базовая модальная поверхность.",trigger:e.jsx(t,{variant:"secondary",children:"Открыть Modal"})}),e.jsx(n,{trigger:e.jsx(t,{variant:"secondary",children:"Открыть ConfirmDialog"})}),e.jsx(c,{trigger:e.jsx(t,{variant:"ghost",children:"Открыть Popover"}),content:e.jsx("div",{children:"Содержимое popover."})})]}),e.jsx(d,{title:"SidePanel",children:e.jsx("div",{className:"text-sm text-white/70",children:"Контент боковой панели."})}),e.jsx(l,{title:"ActionSheet",items:["Диагностика","Настройки","Сервис"]})]}),e.jsx("div",{className:"space-y-4",children:e.jsx(p,{title:"ToastNotification",description:"Системное сообщение отображается поверх layout-компонентов."})}),e.jsx(m,{open:i,onOpenChange:a})]})}};r.parameters={...r.parameters,docs:{...r.parameters?.docs,source:{originalSource:`{
  render: () => {
    const [open, setOpen] = useState(false);
    return <div className="grid gap-6 xl:grid-cols-2">\r
        <div className="space-y-4">\r
          <div className="flex flex-wrap gap-3">\r
            <Button onClick={() => setOpen(true)}>Открыть EmergencyStopOverlay</Button>\r
            <Modal title="Модалка" description="Базовая модальная поверхность." trigger={<Button variant="secondary">Открыть Modal</Button>} />\r
            <ConfirmDialog trigger={<Button variant="secondary">Открыть ConfirmDialog</Button>} />\r
            <PopoverCard trigger={<Button variant="ghost">Открыть Popover</Button>} content={<div>Содержимое popover.</div>} />\r
          </div>\r
          <SidePanel title="SidePanel">\r
            <div className="text-sm text-white/70">Контент боковой панели.</div>\r
          </SidePanel>\r
          <ActionSheet title="ActionSheet" items={['Диагностика', 'Настройки', 'Сервис']} />\r
        </div>\r
        <div className="space-y-4">\r
          <ToastNotification title="ToastNotification" description="Системное сообщение отображается поверх layout-компонентов." />\r
        </div>\r
        <EmergencyStopOverlay open={open} onOpenChange={setOpen} />\r
      </div>;
  }
}`,...r.parameters?.docs?.source}}};const y=["Overview"];export{r as Overview,y as __namedExportsOrder,j as default};
