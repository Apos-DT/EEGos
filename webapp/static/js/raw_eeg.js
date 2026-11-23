(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const node = (tag,text,cls) => {const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
  const selected = name => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`), el=>Number(el.value));
  let catalog=null, running=false;
  document.querySelectorAll("[data-eeg-source]").forEach(button=>button.addEventListener("click",()=>{
    document.querySelectorAll("[data-eeg-source]").forEach(b=>b.classList.toggle("active",b===button));
    $("seedRawWorkspace").hidden=button.dataset.eegSource!=="seed";$("eeglabWorkspace").hidden=button.dataset.eegSource!=="eeglab";
  }));
  function error(message) {$("rawError").textContent=message||"";$("rawError").hidden=!message;}
  function sync() {
    const sessions=selected("rawSession"),subjects=selected("rawSubject");
    const files=catalog?.files.filter(f=>sessions.includes(f.session)&&subjects.includes(f.subject))||[];
    $("rawScopeHint").textContent=`已选 ${sessions.length} 个会话 × ${subjects.length} 名被试 · ${files.length} 个本机文件 · ${files.length*24} 个 trial`;
    $("rawRunSummary").textContent=`本次：${files.length} 个文件；${$("rawWindow").value} 秒窗 / ${$("rawStep").value} 秒步长；${$("rawReject").value==="0"?"不做峰峰值拒绝":`峰峰值上限 ${$("rawReject").value} µV`}。`;
    $("rawRun").disabled=running||!sessions.length||!subjects.length||!files.length;
    const apply=$("rawICA").value==="apply";
    $("rawComponents").disabled=$("rawICA").value!=="review";
    $("rawSeed").disabled=$("rawICA").value!=="review";
    document.querySelectorAll("[data-ica-apply]").forEach(el=>{el.hidden=!apply;el.querySelector("input, select").disabled=!apply;});
    $("rawICAReference").required=apply;$("rawExclude").required=apply;
  }
  document.querySelectorAll('input[name="rawSession"], input[name="rawSubject"]').forEach(el=>el.addEventListener("change",sync));
  $("seedRawForm").addEventListener("input",sync);$("seedRawForm").addEventListener("change",sync);
  $("seedRawForm").addEventListener("invalid",event=>{const d=event.target.closest("details");if(d)d.open=true;},true);
  for (const [id,checked] of [["rawAllSubjects",true],["rawClearSubjects",false]]) $(id).addEventListener("click",()=>{document.querySelectorAll('input[name="rawSubject"]').forEach(el=>el.checked=checked);sync();});
  $("rawPreset").addEventListener("change",()=>{
    const baseline=$("rawPreset").value==="baseline";
    $("rawLow").value="1";$("rawHigh").value="75";$("rawNotch").value=baseline?"0":"50";$("rawReference").value=baseline?"none":"car";
    $("rawWindow").value="4";$("rawStep").value="4";$("rawEdge").value=baseline?"0":"1";$("rawReject").value=baseline?"0":"200";$("rawFlat").value=baseline?"0":"0.1";$("rawICA").value="off";sync();
  });
  function signalPreview(preview) {
    const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");svg.setAttribute("viewBox","0 0 820 220");svg.setAttribute("role","img");svg.setAttribute("aria-label","首个 trial 的前4通道原始波形，20秒");
    preview.values.forEach((values,i)=>{
      const amp=Math.max(1,...values.map(Math.abs)),middle=25+i*48;
      const line=document.createElementNS(ns,"line");for(const [k,v] of Object.entries({x1:90,x2:810,y1:middle,y2:middle,stroke:"#dfe8e8"}))line.setAttribute(k,v);svg.append(line);
      const label=document.createElementNS(ns,"text");label.setAttribute("x","0");label.setAttribute("y",middle+4);label.setAttribute("font-size","12");label.textContent=preview.channels[i];svg.append(label);
      const poly=document.createElementNS(ns,"polyline");poly.setAttribute("fill","none");poly.setAttribute("stroke","#138677");poly.setAttribute("stroke-width","1");poly.setAttribute("points",values.map((v,j)=>`${90+720*j/(values.length-1)},${middle-v/amp*19}`).join(" "));svg.append(poly);
    });
    $("rawSignalPreview").replaceChildren(svg,node("p","首个 trial 前 20 秒；各导独立缩放，仅供波形检查。幅值单位与采样率在处理参数中确认。","hint"));
  }
  $("rawInspect").addEventListener("click",async()=>{
    error("");const sessions=selected("rawSession"),subjects=selected("rawSubject");if(!sessions.length||!subjects.length){error("至少选择一个会话和一名被试");return;}
    EEG.setBusy($("rawInspect"),true,"读取文件…");
    try {
      const data=await EEG.api(`/api/eeg/raw/inspect?session=${sessions[0]}&subject=${subjects[0]}`);
      $("rawInspectInfo").textContent=`${data.filename} · ${data.n_channels} 通道 · ${data.n_trials} trial · ${data.duration_seconds} 秒`;
      $("rawInspectBasis").textContent=data.metadata_basis;signalPreview(data.preview);$("rawTrialDetails").hidden=false;
      $("rawTrialBody").replaceChildren(...data.variables.map(v=>{const tr=node("tr");[v.name,v.trial,v.shape.join(" × "),`${v.duration_seconds} s`,`${v.label} · ${data.class_names[v.label]}`].forEach(value=>tr.append(node("td",value)));return tr;}));
    } catch(e){error(e.message);} finally{EEG.setBusy($("rawInspect"),false);}
  });
  async function history() {
    try {
      const data=await EEG.api("/api/eeg/raw/runs");const container=$("rawHistory");container.replaceChildren();
      const reference=$("rawICAReference"),value=reference.value;reference.replaceChildren(node("option","选择成功的 ICA 审阅任务…"));reference.firstChild.value="";
      for (const r of data.runs) {
        const row=node("div",undefined,"raw-history-row"),description=node("div");row.dataset.recordResource="eeg_runs";row.dataset.recordId=r.run_id;description.append(node("strong",r.display_name||r.run_id),node("p",`${({success:"已完成",running:"处理中",failed:"失败"})[r.status]||r.status} · ${r.started_at||""} · ${r.n_samples??"—"} 窗口`,"hint"));
        const button=node("button","查看结果","btn btn-soft btn-sm");button.type="button";button.addEventListener("click",async()=>{try{renderResult(await EEG.api(`/api/eeg/raw/runs/${r.run_id}`));}catch(e){error(e.message);}});row.append(description,button);container.append(row);
        if(r.status==="success"&&r.ica?.mode==="review") {const option=node("option",r.run_id);option.value=r.run_id;reference.append(option);}
      }
      reference.value=value;
      if(!data.runs.length)container.append(node("p","还没有原始 MAT 处理记录。","hint"));
    }catch(e){$("rawHistory").textContent=e.message;}
  }
  function renderResult(r) {
    $("rawResults").hidden=false;$("rawResultSummary").textContent=`${r.run_id} · ${r.status==="success"?"已完成":r.status} · ${r.elapsed_seconds||0} 秒 · ${r.finished_at||""}`;
    const metrics=[["有效窗口",r.n_samples??0],["剔除窗口",r.n_rejected??0],["原始 trial",r.n_trials??r.trials?.length??0],["输出通道",r.n_channels??"—"]];
    $("rawResultMetrics").replaceChildren(...metrics.map(([label,v])=>{const box=node("div");box.append(node("span",label),node("strong",v));return box;}));
    const base=`/files/eeg/${encodeURIComponent(r.run_id)}/`;
    $("rawWaveform").src=base+"waveform.png";$("rawSpectrum").src=base+"spectrum.png";
    $("rawWaveform").closest("figure").hidden=!r.files?.includes("waveform.png");$("rawSpectrum").closest("figure").hidden=!r.files?.includes("spectrum.png");
    const files=[["features.npz","DE 特征"],["features.manifest.json","数据版本清单"],["raw.npz","清洗窗口"],["channel_qc.csv","通道质量明细"],["eeg_report.json","完整质量报告"],["window_index.npz","窗口原始位置"],["review-ica.fif","固定 ICA 分解"]];
    $("rawArtifacts").replaceChildren(...files.filter(([name])=>r.files?.includes(name)||name==="eeg_report.json").map(([name,label])=>{const a=node("a",label,"btn btn-soft btn-sm");a.href=base+name;a.target="_blank";return a;}));
    if(r.status==="success" || r.status==="failed") {const reportLink=node("a","处理报告","btn btn-soft btn-sm");reportLink.href=`/api/eeg/raw/runs/${encodeURIComponent(r.run_id)}/report`;reportLink.target="_blank";$("rawArtifacts").prepend(reportLink);}
    $("rawGoTrain").hidden=!r.dataset_id;
    $("rawGoTrain").href=r.n_subjects>=2?`/training?dataset=${encodeURIComponent(r.dataset_id)}`:"/datasets?tab=eeg";
    $("rawGoTrain").textContent=r.n_subjects>=2?"使用特征训练":"查看特征数据集";
    $("rawQualityBody").replaceChildren(...(r.trials||[]).map(t=>{const tr=node("tr");[`${t.session} / S${String(t.subject).padStart(2,"0")}`,t.trial,r.class_names[t.label],t.windows_total,t.windows_kept,t.windows_rejected].forEach(v=>tr.append(node("td",v)));return tr;}));
    const ica=$("rawICAResult");ica.replaceChildren();
    if(r.ica) {
      ica.append(node("p",r.ica.mode==="review"?`已保存 ${r.ica.components} 个成分。审阅任务 ID：${r.run_id}；未移除任何成分。收敛：${r.ica.converged?"是":"否，请复核"}`:`已复用 ${r.ica.reference} 的分解，移除成分 ${r.ica.excluded.join(", ")}。`,"hint"));
      if(r.ica.mode==="review") {const img=node("img");img.src=base+"ica_components.png";img.alt="ICA 成分波形";img.className="raw-result-image";ica.append(img);}
    }
    if(r.error)ica.append(node("p",r.error,"form-error"));
    $("rawResults").scrollIntoView({behavior:"smooth",block:"start"});
  }
  function watch(job) {
    running=true;sync();EEG.renderJob(job,"rawEEGConsole");
    EEG.pollJob(job.id,{consoleId:"rawEEGConsole",timeout:24*60*60*1000,
      onSuccess:done=>{running=false;sync();sessionStorage.removeItem("eegRawJob");const r=done.result.report;r.dataset_id=done.result.dataset_id;renderResult(r);history();},
      onFail:failed=>{running=false;sync();sessionStorage.removeItem("eegRawJob");error(failed.error||"任务未完成，查看处理记录与日志。");history();}});
  }
  $("seedRawForm").addEventListener("submit",async event=>{
    event.preventDefault();if(running)return;error("");
    const names={rawFs:"fs",rawLow:"low",rawHigh:"high",rawNotch:"notch",rawTargetFs:"target_fs",rawWindow:"window",rawStep:"step",rawEdge:"edge",rawReject:"reject_uv",rawFlat:"flat_uv",rawComponents:"ica_components",rawSeed:"seed"};
    const payload={sessions:selected("rawSession"),subjects:selected("rawSubject"),unit:$("rawUnit").value,reref:$("rawReference").value,bad_channels:$("rawBadChannels").value.toUpperCase().split(/[,，\s]+/).filter(Boolean),save_windows:$("rawSaveWindows").checked,ica_mode:$("rawICA").value,ica_reference:$("rawICA").value==="apply"?$("rawICAReference").value:"",ica_exclude:$("rawICA").value==="apply"?$("rawExclude").value.split(/[,，\s]+/).filter(Boolean).map(Number):[]};
    for(const [id,key] of Object.entries(names))payload[key]=Number($(id).value);
    running=true;sync();
    try{const result=await EEG.api("/api/eeg/raw/process",{method:"POST",body:JSON.stringify(payload)});sessionStorage.setItem("eegRawJob",result.job.id);watch(result.job);}
    catch(e){running=false;sync();error(e.message);}
  });
  (async()=>{
    try{catalog=await EEG.api("/api/eeg/raw/catalog");$("rawCatalogCount").textContent=`${catalog.files.length} 个文件`;sync();}
    catch(e){error(e.message);$("rawCatalogCount").textContent="读取失败";}
    await history();
    const id=sessionStorage.getItem("eegRawJob");
    if(id){try{watch(await EEG.api(`/api/jobs/${id}`));}catch(e){sessionStorage.removeItem("eegRawJob");error("上次任务不在当前服务中，请从处理记录查看结果。");}}
  })();
})();
