"""Exercise asynchronous UI state without a browser or network listener."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


APP = Path(__file__).resolve().parents[1] / "payload/harness/task-surface/app.js"
NODE = shutil.which("node")
CLIENT = r"""
const fs = require("fs");
const vm = require("vm");
class Element {
  constructor(tag="div") {
    this.tag=tag; this.children=[]; this.hidden=false; this.textContent="";
    this.value=""; this.dataset={}; this.attributes={};
  }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; }
  setAttribute(name,value) { this.attributes[name]=value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener() {}
}
function deferred() {
  let resolve, reject;
  const promise=new Promise((a,b)=>{resolve=a; reject=b;});
  return {promise,resolve,reject};
}
const flush=()=>new Promise(setImmediate);
function snapshot(id) {
  return {schema:1,generated_at:"2026-09-30T12:00:00Z",tasks:[{
    task_id:id,title:id,objective:"Continue explicitly",state:"open",
    checkpoint:{state:"recorded"},resume:{ready:true,text:id+" context"}
  }],attention:[]};
}
const ok=(id)=>({ok:true,json:async()=>snapshot(id)});
function textTree(node) {
  return [String(node.textContent),...node.children.map(textTree)].join(" ");
}
function harness() {
  const elements=new Map(), requests=[];
  const get=(q)=>{if(!elements.has(q))elements.set(q,new Element()); return elements.get(q);};
  const document={querySelector:get,querySelectorAll:()=>[],createElement:(tag)=>new Element(tag)};
  const context=vm.createContext({document,location:{hash:"#test-token"},
    navigator:{clipboard:{writeText:async()=>{}}},Date,JSON,String,Object,Array,Number,
    setTimeout:()=>{},fetch:()=>{const r=deferred();requests.push(r);return r.promise;}});
  vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),context);
  const inspect=()=>({tasks:vm.runInContext("data.tasks.map(taskId)",context),
    selected:vm.runInContext("selected",context),alertHidden:get("#alert").hidden,
    freshness:get("#freshness").textContent,
    counts:["#task-count","#attention-count","#delivery-count"].map(q=>String(get(q).textContent)),
    items:textTree(get("#items")),detail:textTree(get("#detail")),
    currentDetail:get("#detail").children.filter(n=>n.tag!=="details").map(textTree).join(" "),
    history:get("#detail").children.filter(n=>n.tag==="details").map(textTree).join(" ")});
  return {context,requests,get,inspect};
}
(async()=>{
  const results={};
  for (const newer of ["failure","success"]) {
    const h=harness(), oldBody=deferred();
    h.requests[0].resolve({ok:true,json:()=>oldBody.promise});
    await flush(); // The older request has already passed the fetch await.
    vm.runInContext("load()",h.context);
    h.requests[1].resolve(newer==="failure" ? {ok:false} : ok("new"));
    await flush();
    oldBody.resolve(snapshot("old"));
    await flush();
    results["old_success_new_"+newer]=h.inspect();
  }
  {
    const h=harness();
    vm.runInContext("load()",h.context);
    h.requests[1].resolve(ok("new"));
    await flush();
    h.requests[0].reject(new Error("older transport error"));
    await flush();
    results.old_failure_new_success=h.inspect();
  }
  {
    const h=harness();
    vm.runInContext('view="attention"',h.context);
    h.requests[0].resolve({ok:false});
    await flush();
    results.unavailable_attention=h.inspect();
  }
  {
    const h=harness();
    h.requests[0].resolve(ok("first"));
    await flush();
    results.explicit_selection=h.inspect();
    h.get("#items").children[0].onclick();
    results.after_selection=h.inspect();
  }
  {
    const h=harness(), value=snapshot("chain");
    value.tasks[0].checkpoint={state:"recorded",decisions:[
      {id:"d1",text:"DECISION_OLD",status:"accepted"},
      {id:"d2",text:"DECISION_CURRENT",status:"proposed"}
    ],corrections:[
      {id:"c1",text:"CORRECTION_OLD",supersedes:"d1"},
      {id:"c2",text:"CORRECTION_CURRENT",supersedes:"c1"},
      {id:"scope-correction",text:"SCOPE_CURRENT",supersedes:"scope"}
    ],constraints:[{id:"scope",text:"SCOPE_OLD",critical:true}],evidence:[{path:"source-new.md",replaces:"source-old.md",replacement_reason:"Moved by owner",status:"unchanged"}]};
    h.requests[0].resolve({ok:true,json:async()=>value});
    await flush();
    h.get("#items").children[0].onclick();
    results.correction_chain=h.inspect();
  }
  console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


@unittest.skipUnless(NODE, "Node.js required for the offline JavaScript regression")
class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([NODE, "-e", CLIENT, str(APP)], capture_output=True,
                                text=True, check=True, timeout=10)
        cls.results = json.loads(result.stdout)

    def test_older_success_does_not_hide_newer_failure(self):
        state = self.results["old_success_new_failure"]
        self.assertEqual(state["tasks"], [])
        self.assertFalse(state["alertHidden"])
        self.assertIn("Estado desconhecido", state["freshness"])

    def test_older_success_does_not_replace_newer_success(self):
        self.assertEqual(self.results["old_success_new_success"]["tasks"], ["new"])

    def test_older_failure_does_not_clear_newer_success(self):
        state = self.results["old_failure_new_success"]
        self.assertEqual(state["tasks"], ["new"])
        self.assertTrue(state["alertHidden"])

    def test_unavailable_attention_has_unknown_counts(self):
        state = self.results["unavailable_attention"]
        self.assertEqual(state["counts"], ["?", "?", "?"])
        self.assertIn("Leitura indisponível", state["items"])
        self.assertNotIn("Nenhuma pendência", state["items"])
        self.assertIn("Estado desconhecido", state["detail"])

    def test_copy_context_requires_explicit_task_selection(self):
        state = self.results["explicit_selection"]
        self.assertIsNone(state["selected"])
        self.assertIn("Escolha uma tarefa", state["detail"])
        self.assertNotIn("Copiar contexto de retomada", state["detail"])
        chosen = self.results["after_selection"]
        self.assertEqual(chosen["selected"], "first")
        self.assertIn("Copiar contexto de retomada", chosen["detail"])

    def test_superseded_decisions_and_corrections_only_appear_in_history(self):
        state = self.results["correction_chain"]
        self.assertIn("CORRECTION_CURRENT", state["currentDetail"])
        self.assertIn("DECISION_CURRENT", state["currentDetail"])
        self.assertIn("SCOPE_CURRENT", state["currentDetail"])
        self.assertIn("Substitui source-old.md: Moved by owner", state["currentDetail"])
        for old in ("DECISION_OLD", "CORRECTION_OLD", "SCOPE_OLD"):
            self.assertNotIn(old, state["currentDetail"])
            self.assertIn(old, state["history"])


if __name__ == "__main__":
    unittest.main()
