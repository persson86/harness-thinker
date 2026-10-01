"use strict";
const $ = (q) => document.querySelector(q);
let data = {tasks: [], attention: []}, view = "resume", selected = null;
let loadEpoch = 0, unavailable = false;
const token = location.hash.slice(1);
const views = {
  resume: ["CONTINUE DE ONDE PAROU", "Retomar trabalho", "Objetivo, correções e próximos passos, juntos na tarefa."],
  attention: ["SUA ATENÇÃO, COM CONTEXTO", "Precisa de mim", "Perguntas, fontes alteradas e entregas que ainda precisam de revisão."],
  deliveries: ["PROPOSTAS E EVIDÊNCIAS", "Entregas", "Uma entrega disponível ainda precisa ser lida e avaliada."]
};
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = String(text); if (cls) n.className = cls; return n; }
function taskId(t) { return t.task_id || t.id; }
function textOf(x) { return typeof x === "string" ? x : x?.text || x?.message || x?.path || "Sem descrição"; }
function activeCheckpoint(t) { return t.checkpoint || t.latest_checkpoint || {}; }
function currentItems(cp, group) {
  const corrections=Array.isArray(cp.corrections) ? cp.corrections : [];
  const superseded=new Set(corrections.map(c=>c.supersedes).filter(Boolean));
  return (Array.isArray(cp[group]) ? cp[group] : []).filter(item=>!superseded.has(item?.id));
}
function pendingFor(t) { return data.attention.filter(a => a.task_id === taskId(t)); }
function links(t) { return Array.isArray(t.links) ? t.links : []; }
function deliveries(t) { return links(t).filter(l=>l.kind === "artifact"); }
function dateText(value) { const d = new Date(value); return Number.isNaN(+d) ? "instante desconhecido" : d.toLocaleString("pt-BR"); }
function toast(text) { $("#toast").textContent=text; $("#toast").hidden=false; setTimeout(()=>$("#toast").hidden=true,2500); }
function listSection(root, title, rows) {
  if (!Array.isArray(rows) || !rows.length) return;
  root.append(el("h3", title)); const ul=el("ul");
  for (const row of rows) { const li=el("li",textOf(row)); if (row.status) li.append(el("small",`Estado registrado: ${row.status}`)); if (row.origin) li.append(el("small",`Origem: ${row.origin}`)); ul.append(li); }
  root.append(ul);
}
function renderDetail(t) {
  const root=$("#detail"); root.replaceChildren();
  if(unavailable){const empty=el("div",undefined,"empty");empty.append(el("h2","Estado desconhecido"),el("p","A projeção de tarefas não pôde ser consultada."));root.append(empty);return;}
  if(!t){const empty=el("div",undefined,"empty");empty.append(el("h2","Escolha uma tarefa"),el("p","Veja o que já está decidido e o que falta conferir."));root.append(empty);return;}
  const cp=activeCheckpoint(t), attention=pendingFor(t);
  root.append(el("span",t.state === "closed" ? "Encerrada" : t.state === "paused" ? "Pausada" : "Tarefa aberta","tag"),el("h2",t.title),el("p",t.objective,"objective"));
  if(attention.length) root.append(el("div",`${attention.length} pendência(s) associada(s). Leia os detalhes antes de retomar.`,"notice"));
  if(cp.state) {root.append(el("h3","Último estado registrado"),el("p",cp.state));}
  const corrections = currentItems(cp,"corrections");
  for(const c of corrections){const box=el("div",undefined,"correction");box.append(el("strong","CORREÇÃO A PRESERVAR"),el("span",textOf(c)));root.append(box);}
  listSection(root,"Decisões",currentItems(cp,"decisions"));
  listSection(root,"Próximos passos",cp.pending);
  listSection(root,"Limites registrados",cp.constraints || cp.authorization);
  listSection(root,"Precisa de atenção",attention);
  listSection(root,"Artefatos vinculados",deliveries(t).map(l=>({text:l.external_id || l.path,status:"Referência registrada; utilidade não avaliada"})));
  const sources=t.sources || t.evidence_status || cp.evidence || [];
  if(sources.length){root.append(el("h3","Fontes para conferir"));const ul=el("ul");for(const s of sources){const li=el("li",s.path || textOf(s));li.append(el("small",s.status || "Referência registrada; confira a fonte"));ul.append(li);}root.append(ul);}
  if(!Object.keys(cp).length) root.append(el("p","Esta tarefa ainda não tem um checkpoint. Registre o estado antes da próxima troca de sessão.","notice"));
  const detail=el("details");detail.append(el("summary","Identidade, proveniência e histórico"));const record={task_id:taskId(t),revision:t.revision,generation:t.generation,updated_at:t.updated_at,links:links(t),checkpoint_history:{decisions:cp.decisions || [],corrections:cp.corrections || []}};detail.append(el("pre",JSON.stringify(record,null,2)));root.append(detail);
  const footer=el("footer");const copy=el("button","Copiar ID da tarefa","secondary");copy.onclick=async()=>{try{await navigator.clipboard.writeText(taskId(t));toast("ID copiado");}catch{toast("Selecione o ID em Identidade e proveniência");}};footer.append(copy);
  if(t.resume?.ready && t.resume?.text){const button=el("button","Copiar contexto de retomada","primary");button.onclick=async()=>{try{await navigator.clipboard.writeText(t.resume.text);toast("Contexto copiado. Confira as fontes ao retomar.");}catch{toast("Não foi possível copiar o contexto");}};footer.prepend(button);}
  root.append(footer);
}
function render(){
  const [eyebrow,title,description]=views[view];$("#view-label").textContent=eyebrow;$("#view-title").textContent=title;$("#view-description").textContent=description;
  document.querySelectorAll("[data-view]").forEach(b=>{if(b.dataset.view===view)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
  $("#task-count").textContent=unavailable ? "?" : data.tasks.filter(t=>t.state!=="closed").length;$("#attention-count").textContent=unavailable ? "?" : data.attention.length;$("#delivery-count").textContent=unavailable ? "?" : data.tasks.reduce((n,t)=>n+deliveries(t).length,0);
  const query=$("#search").value.toLocaleLowerCase("pt-BR");
  let tasks=data.tasks.filter(t=>`${t.title} ${t.objective}`.toLocaleLowerCase("pt-BR").includes(query));
  if(view==="attention")tasks=tasks.filter(t=>pendingFor(t).length);
  if(view==="deliveries")tasks=tasks.filter(t=>deliveries(t).length);
  const items=$("#items");items.replaceChildren();
  if(unavailable){const empty=el("div",undefined,"empty");empty.append(el("h2","Leitura indisponível"),el("p","Não foi possível consultar as tarefas e pendências. Atualize a leitura para tentar novamente."));items.append(empty);}
  else if(!tasks.length){const empty=el("div",undefined,"empty");empty.append(el("h2",query ? "Nenhuma correspondência" : view==="attention" ? "Nenhuma pendência nesta leitura" : "Nada por aqui ainda"),el("p",query ? "Tente outro nome ou objetivo." : "A lista mostra apenas tarefas e vínculos registrados."));items.append(empty);}
  for(const t of tasks){const button=el("button",undefined,"task");button.setAttribute("aria-pressed",String(selected===taskId(t)));const n=pendingFor(t).length;const label=n ? `${n} para conferir` : t.state === "closed" ? "Encerrada" : !Object.keys(activeCheckpoint(t)).length ? "Sem checkpoint" : t.resume?.ready ? "Retomável" : "Contexto a conferir";button.append(el("span",label,`tag${n ? " warn" : ""}`),el("h2",t.title),el("p",t.objective));button.onclick=()=>{selected=taskId(t);render();};items.append(button);}
  renderDetail(tasks.find(t=>taskId(t)===selected));
}
async function load(){
  const epoch=++loadEpoch;
  try{
    const response=await fetch("/snapshot",{headers:{"X-Thinker-Token":token},cache:"no-store"});
    if(epoch!==loadEpoch)return;
    if(!response.ok)throw new Error();
    const next=await response.json();
    if(epoch!==loadEpoch)return;
    if(next.schema!==1 || !Array.isArray(next.tasks) || !Array.isArray(next.attention))throw new Error();
    data=next;unavailable=false;$("#alert").hidden=true;$("#freshness").textContent=`Leitura de ${dateText(data.generated_at)}. Sem acompanhamento em tempo real.`;$("#environment").textContent=data.demo ? "LABORATÓRIO · DADOS SINTÉTICOS" : "TAREFAS · CONSULTA LOCAL";render();
  }
  catch{
    if(epoch!==loadEpoch)return;
    data={tasks:[],attention:[]};selected=null;unavailable=true;render();$("#alert").textContent="A leitura está indisponível. Abra o endereço completo recebido ao iniciar a superfície e confira a projeção de tarefas.";$("#alert").hidden=false;$("#freshness").textContent="Estado desconhecido. Nenhuma tarefa está sendo apresentada como atual.";
  }
}
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});$("#search").addEventListener("input",render);$("#refresh").onclick=load;load();
$(".brand").onclick=(event)=>{event.preventDefault();view="resume";render();};
