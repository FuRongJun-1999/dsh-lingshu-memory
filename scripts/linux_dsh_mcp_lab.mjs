/** Offline Docker lab using the actual DSH registry, native executor and MCP bridge. */
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolsService from '@deepseek-ai/dsh-tools';
import * as Native from '@deepseek-ai/dsh-tool-executor-native';
import * as Mcp from '@deepseek-ai/dsh-mcp-client';

const root = await mkdtemp('/tmp/lingshu-mcp-');
const ctx = new Context();
const marker = root + '/server.pid';
let seq = 0;
const launch = 'import os,pathlib,runpy,sys; pathlib.Path(sys.argv[1]).write_text(str(os.getpid()),encoding="utf-8"); sys.argv=sys.argv[1:]; runpy.run_module("shadow_runtime.mcp_lab",run_name="__main__")';
const conditions = { carrier: {state:'declared',text:'md'}, method:{state:'declared',text:'exact'}, existence:{state:'declared',text:'present'}, attributes:[] };
const interval={start:{state:'instant',value:'2024-01-01T00:00:00Z'},end:{state:'instant',value:'2024-01-10T00:00:00Z'}};
const request={kind:'Write.create',caller_token:'dsh-lab',content:'synthetic blue tile',declared_sensitivity:1,
  reader_ceiling:['alice'],source_edges:[],condition_space:conditions,bitemporal:{observed:interval,effective:interval},
  source_attribution:{source_kind:'document',source_id:'fixture'},durability_request:'process'};
const get={kind:'Read.get',node_id:'node-1',include_provenance:false,condition_query:conditions,time_axis:'effective',time_point:'2024-01-05T00:00:00Z'};

async function call(name, args) {
  const id = 'fixture-' + ++seq;
  const batch = await ctx.tools.execute({calls:[{type:'tool-call',id,name,arguments:JSON.stringify(args)}], signal:AbortSignal.timeout(10000)});
  assert.equal(batch.results.length,1);
  assert.equal(batch.results[0].callId,id);
  return batch.results[0].result;
}
async function invoke(name, request) {
  const r = await call(name,{request});
  assert.equal(r.isError,false,JSON.stringify(r.error ?? null));
  return JSON.parse(r.value.content[0].text);
}
function attach(name, principal, markerPath) {
  return ctx.plugin(Mcp, {transport:'stdio',serverName:name,command:'python3',cwd:'/exercise',env:{PYTHONUTF8:'1'},
    args:['-X','utf8','-B','-c',launch,markerPath,'--synthetic','--lab-root',root,'--principal',principal],
    startupTimeoutMs:12000,toolCallTimeoutMs:5000,closeTimeoutMs:4000,failOnStartupError:true,
    reconnect:{enabled:true,initialDelayMs:50,maxDelayMs:200,maxAttempts:6}});
}

const fibers=[];
async function installed(fiber) {
  fibers.push(fiber);
  await fiber;
  const status=Mcp.connectionStatusOf(fiber);
  assert.equal(status?.current().state,'connected');
  assert.equal(status.current().toolCount,1);
  return status;
}
try {
  await installedBase();
  const owner='mcp__fixture_owner__shadow_request', reader='mcp__fixture_reader__shadow_request';
  const aliceFiber=attach('fixture_owner','alice',marker);
  const status=await installed(aliceFiber);
  assert.ok(ctx.tools.get(owner));
  const created=await invoke(owner,request);
  assert.equal(created.outcome,'ok');
  const receipt=created.historical_receipt;
  const firstPid=Number(await readFile(marker,'utf8'));
  assert.ok(Number.isSafeInteger(firstPid)&&firstPid>1&&firstPid!==process.pid);
  const transitions=[];
  const unsub=status.onChange(s=>transitions.push(s.state));
  process.kill(firstPid,'SIGKILL');
  let secondPid;
  for(let i=0;i<120;i++){
    await delay(100);
    secondPid=Number(await readFile(marker,'utf8').catch(()=>''));
    if(secondPid>1&&secondPid!==firstPid&&status.current().state==='connected'&&transitions.includes('connected'))break;
  }
  unsub();
  assert.ok(secondPid>1&&secondPid!==firstPid&&status.current().state==='connected',JSON.stringify(transitions));
  assert.ok(transitions.includes('connecting')&&transitions.includes('connected'),JSON.stringify(transitions));
  assert.ok(ctx.tools.get(owner));
  assert.deepEqual((await invoke(owner,request)).historical_receipt,receipt);
  const after=await invoke(owner,get);
  assert.equal(after.records.length,1);
  assert.equal(after.records[0].body,request.content);
  assert.deepEqual(after.records[0].locator,{id:receipt.node_id,revision:1,content_sha:receipt.content_sha});
  assert.equal((await invoke(owner,{...request,content:'changed fixture'})).error_code,'TOKEN_PAYLOAD_CONFLICT');
  await installed(attach('fixture_reader','bob',root+'/reader.pid'));
  const denied=await invoke(reader,get);
  assert.equal(denied.error_code,'NOT_FOUND_OR_DENIED');
  assert.equal(denied.records,null);
  assert.equal((await call(reader,{request:get,context:{principal:'alice'}})).isError,true);
  assert.equal((await call(reader,{request})).isError,true);
  const rows=(await readFile(root+'/audit/audit.jsonl','utf8')).trimEnd().split('\n').map(line=>JSON.parse(line));
  assert.equal(rows.length,1);
  assert.equal(rows[0].writer_id,receipt.writer_id);
  assert.equal(rows[0].payload_sha,receipt.content_sha);
  console.log('LAB_RESULT '+JSON.stringify({owner_tool:owner,reader_tool:reader,client_pid:process.pid,first_server_pid:firstPid,
    reconnected_server_pid:secondPid,transitions,receipt_replay:'PASS',authorized_read:'PASS',foreign_read:'DENIED',
    audit_rows:rows.length,dsh_tool_pipeline:'PASS',dsh_model_loop:'NOT_RUN',production:'NOT_RUN'}));
} finally {
  for(const fiber of fibers.reverse()) await fiber.dispose();
  await rm(root,{recursive:true,force:true});
}
async function installedBase(){
  for(const plugin of [SystemPrompt,ToolsService,Native]){
    const fiber=ctx.plugin(plugin);
    fibers.push(fiber);
    await fiber;
  }
}
