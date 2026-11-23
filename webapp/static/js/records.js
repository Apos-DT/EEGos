/* The same list manager, editor, recycle bin and creation adapter on every page. */
(function () {
  "use strict";
  let definitions = {}, definitionRequest;
  const pages = {surveys:["surveys"], survey_data:["responses","imports"], media:["media"],
    datasets:["features","raw_data"], eeg:["eeg_runs","eeg_uploads"], training:["training_tasks","experiments","jobs"],
    experiments:["experiments"], documents:["documents"], system:["jobs"], audit:["responses","imports","media"]};
  const $ = id => document.getElementById(id);
  let resource, page = 1, definition, item, pendingDelete, requestNumber = 0, editNumber = 0, dirty = false, searchTimer;
  function element(tag, text, cls) { const el=document.createElement(tag); if(text!=null) el.textContent=text; if(cls)el.className=cls; return el; }
  function message(id, text) { $(id).textContent=text || ""; $(id).hidden=!text; }
  function errorText(error) { return error.status===404 ? "当前服务尚未加载记录管理接口，请使用更新后的 Web 服务。" : error.message; }
  function button(text, action) { const b=element("button",text,"btn btn-soft btn-sm");b.type="button";b.addEventListener("click",async()=>{if(b.disabled)return;b.disabled=true;try{await action();}finally{b.disabled=false;}});return b; }
  async function ensureDefinitions() {
    if(Object.keys(definitions).length)return;
    if(!definitionRequest)definitionRequest=EEG.api("/api/records").then(data=>{
      definitions=data.resources;$("recordResource").replaceChildren();
      for(const [key,value] of Object.entries(definitions)){const option=element("option",value.label);option.value=key;$("recordResource").append(option);}
    }).catch(error=>{definitionRequest=null;throw error;});
    await definitionRequest;
  }
  async function load() {
    const ticket=++requestNumber;
    message("recordLibraryError","");
    try {
      const params=new URLSearchParams({q:$("recordSearch").value,view:$("recordView").value,page:String(page),page_size:"10"});
      const data=await EEG.api(`/api/records/${resource}?${params}`);
      if(ticket!==requestNumber)return;
      definition=data.definition;page=data.page;
      $("recordLibraryTitle").textContent=`${definition.label}管理`;
      $("recordCreate").textContent=definition.upload ? "上传新增" : "新增";
      $("recordUpload").accept=definition.accept || "";
      $("recordRows").replaceChildren();
      for(const row of data.items) {
        const tr=element("tr"), name=element("td"), meta=element("td"), actions=element("td");
        name.append(element("strong",row.title),element("small",row.id));
        meta.append(element("span",row.metadata.tags.join(" · ") || "—"),element("small",row.metadata.notes || ""));
        if(row.metadata.deleted_at)actions.append(button("恢复",()=>mutate(row,"restore")));
        else {
          if(row.url){const link=element("a","查看","mini-link");link.href=row.url;link.target="_blank";link.rel="noopener";actions.append(link);}
          actions.append(button("编辑",()=>edit(resource,row.id)));
          const remove=button("移入回收站",()=>confirmDelete(row));remove.disabled=row.busy;
          if(row.busy)remove.title="任务仍在运行";
          actions.append(remove);
        }
        tr.append(name,meta,actions);$("recordRows").append(tr);
      }
      $("recordNoItems").hidden=!!data.items.length;
      $("recordPageInfo").textContent=`共 ${data.total} 条 · ${data.page} / ${data.pages} 页 · 回收站 ${data.trash_count}`;
      $("recordPrevious").disabled=page<=1;$("recordNext").disabled=page>=data.pages;
    } catch(error) { if(ticket===requestNumber)message("recordLibraryError",errorText(error)); }
  }
  async function open(name) {
    try{await ensureDefinitions();}catch(error){EEG.toast(errorText(error),"error");return;}
    resource=name;page=1;$("recordResource").value=name;$("recordSearch").value="";$("recordView").value="active";
    $("recordRows").replaceChildren();$("recordPageInfo").textContent="加载中…";
    if(!$("recordLibrary").open)$("recordLibrary").showModal();
    await load();
  }
  async function edit(name,id) {
    const ticket=++editNumber;
    try {
      await ensureDefinitions();
      const loaded=await EEG.api(`/api/records/${name}/item?${new URLSearchParams({id})}`);
      if(ticket!==editNumber)return;
      item=loaded;
      item.resource=name;
      $("recordEditorTitle").textContent=`编辑${definitions[name]?.label || "记录"}`;
      $("recordIdentity").textContent=item.id;
      $("recordTitle").value=item.metadata.title || item.title;
      $("recordTags").value=item.metadata.tags.join(", ");$("recordNotes").value=item.metadata.notes;
      $("recordSource").textContent=JSON.stringify(item.source,null,2);
      $("recordEditorDelete").disabled=item.busy;
      message("recordEditError","");if(!$("recordEditor").open)$("recordEditor").showModal();
    } catch(error) { EEG.toast(errorText(error),"error"); }
  }
  function confirmDelete(row) {
    pendingDelete={...row,resource:row.resource||resource};$("recordDeleteName").textContent=row.title;message("recordDeleteError","");$("recordDelete").showModal();
  }
  async function mutate(row,operation) {
    const name=row.resource || resource;
    try {
      await EEG.api(`/api/records/${name}/${operation}`,{method:"POST",body:JSON.stringify({id:row.id,revision:row.metadata.revision})});
      dirty=true;
      if(operation==="delete"){$("recordDelete").close();if($("recordEditor").open)$("recordEditor").close();}
      EEG.toast(operation==="restore" ? "记录已恢复" : "已移入回收站","success");
      if($("recordLibrary").open)await load();
    } catch(error) { message(operation==="delete" ? "recordDeleteError" : "recordLibraryError",errorText(error)); }
  }
  document.addEventListener("DOMContentLoaded",async()=>{
    // Legacy running processes can serve new static files before a restart.
    // Expose management controls only when the corresponding API is present.
    try{await ensureDefinitions();}catch(error){return;}
    document.body.dataset.recordsReady="true";
    const currentPage=document.body.dataset.page;
    const available=currentPage==="datasets" && !$("featureForm") ? [] : pages[currentPage] || [];
    if(available.length){const b=button("",()=>open(available[0]));b.append(element("span","记录管理","record-entry-full"),element("span","管理","record-entry-short"));b.setAttribute("aria-label","记录管理");b.classList.add("record-manager-entry");document.querySelector(".page-actions")?.prepend(b);}
    document.querySelectorAll("[data-close-record]").forEach(b=>b.addEventListener("click",()=>$(b.dataset.closeRecord).close()));
    ["recordLibrary","recordEditor","recordDelete"].forEach(id=>{
      $(id).addEventListener("click",event=>{if(event.target!==$(id))return;const r=$(id).getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$(id).close();});
    });
    $("recordLibrary").addEventListener("close",()=>{if(dirty)location.reload();});
    $("recordEditor").addEventListener("close",()=>{if(dirty&&!$("recordLibrary").open)location.reload();});
    $("recordResource").addEventListener("change",()=>{resource=$("recordResource").value;page=1;load();});
    $("recordView").addEventListener("change",()=>{page=1;load();});
    $("recordSearch").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{page=1;load();},200);});
    $("recordPrevious").addEventListener("click",()=>{page--;load();});$("recordNext").addEventListener("click",()=>{page++;load();});
    $("recordDeleteConfirm").addEventListener("click",async()=>{const b=$("recordDeleteConfirm");EEG.setBusy(b,true);try{await mutate(pendingDelete,"delete");}finally{EEG.setBusy(b,false);}});
    $("recordEditorDelete").addEventListener("click",()=>confirmDelete(item));
    $("recordEditForm").addEventListener("submit",async event=>{
      event.preventDefault();const b=$("recordSave");EEG.setBusy(b,true,"保存中…");
      try {
        await EEG.api(`/api/records/${item.resource}/item`,{method:"PATCH",body:JSON.stringify({id:item.id,revision:item.metadata.revision,title:$("recordTitle").value,notes:$("recordNotes").value,tags:$("recordTags").value.split(/[,，]/).map(s=>s.trim()).filter(Boolean)})});
        dirty=true;EEG.toast("管理信息已保存","success");$("recordEditor").close();if($("recordLibrary").open)await load();
      } catch(error){message("recordEditError",errorText(error));}
      finally{EEG.setBusy(b,false);}
    });
    $("recordCreate").addEventListener("click",()=>{if(!definition)return;if(definition.upload)$("recordUpload").click();else location.assign(definition.create_url);});
    $("recordUpload").addEventListener("change",async()=>{
      const file=$("recordUpload").files[0];if(!file)return;const b=$("recordCreate");EEG.setBusy(b,true,"上传中…");
      try{await EEG.api(`${definition.upload}?${new URLSearchParams({filename:file.name})}`,{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file});dirty=true;$("recordSearch").value="";$("recordView").value="active";page=1;await load();EEG.toast("文件已接入","success");}
      catch(error){message("recordLibraryError",errorText(error));}finally{$("recordUpload").value="";EEG.setBusy(b,false);}
    });
    function mount(root=document){root.querySelectorAll("[data-record-resource][data-record-id]:not([data-record-mounted])").forEach(row=>{
      row.dataset.recordMounted="1";const b=button("管理",()=>edit(row.dataset.recordResource,row.dataset.recordId));b.classList.add("record-inline-action");
      const target=row.querySelector("[data-record-actions]") || (row.tagName==="TR" ? row.lastElementChild : row);target.append(b);
    });}
    mount();new MutationObserver(()=>mount()).observe(document.body,{childList:true,subtree:true});
  });
  EEG.records={open,edit};
})();
