"""Jira MCP Server with SSE + WebSocket transports."""
import asyncio, json, logging, random, re, sys, uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stderr)
logger = logging.getLogger("jira_mcp")
NOW = datetime.now(timezone.utc)

ONCALL = {
    "payment-service":{"name":"Raj Patel","email":"raj.patel@bank.internal","phone":"+1-555-0142","role":"Senior SRE"},
    "card-auth-service":{"name":"Raj Patel","email":"raj.patel@bank.internal","phone":"+1-555-0142","role":"Senior SRE"},
    "fraud-engine":{"name":"Sarah Chen","email":"sarah.chen@bank.internal","phone":"+1-555-0198","role":"ML Engineer"},
    "checkout-service":{"name":"Marcus Johnson","email":"marcus.johnson@bank.internal","phone":"+1-555-0167","role":"Staff Engineer"},
    "mobile-app":{"name":"Priya Sharma","email":"priya.sharma@bank.internal","phone":"+1-555-0123","role":"Mobile Lead"},
    "dba":{"name":"Tom Wilson","email":"tom.wilson@bank.internal","phone":"+1-555-0189","role":"Principal DBA"},
    "default":{"name":"NOC Duty Manager","email":"noc@bank.internal","phone":"+1-555-0100","role":"NOC Manager"},
}

NEXT_NUM=1043; ISSUES={}

def _seed():
    global NEXT_NUM
    for i in [
        {"key":"PAY-1031","summary":"[SEV-1] Payment processing outage card transactions failing","type":"Incident","priority":"Critical","status":"Resolved","assignee":"raj.patel@bank.internal","labels":["sev-1","payments","incident"],"created":(NOW-timedelta(days=14)).isoformat(),"updated":(NOW-timedelta(days=13)).isoformat(),"comments":[{"author":"raj.patel@bank.internal","body":"Root cause: connection pool exhaustion on postgres-primary.","created":(NOW-timedelta(days=14,hours=-2)).isoformat()}]},
        {"key":"PAY-1032","summary":"Increase postgres connection pool limits for card-auth-service","type":"Task","priority":"High","status":"In Progress","assignee":"tom.wilson@bank.internal","labels":["database","performance"],"created":(NOW-timedelta(days=10)).isoformat(),"updated":(NOW-timedelta(days=2)).isoformat(),"comments":[]},
        {"key":"PAY-1033","summary":"Fraud model v2.14 lower velocity threshold for high-risk MCCs","type":"Story","priority":"High","status":"Done","assignee":"sarah.chen@bank.internal","labels":["fraud","ml-model"],"created":(NOW-timedelta(days=7)).isoformat(),"updated":(NOW-timedelta(days=1)).isoformat(),"comments":[{"author":"sarah.chen@bank.internal","body":"Load test passed. Deploying to prod.","created":(NOW-timedelta(days=1)).isoformat()}]},
        {"key":"PAY-1034","summary":"Mobile app crash on payment confirmation (iOS 17.4)","type":"Bug","priority":"Medium","status":"To Do","assignee":"priya.sharma@bank.internal","labels":["mobile","ios","crash"],"created":(NOW-timedelta(days=5)).isoformat(),"updated":(NOW-timedelta(days=5)).isoformat(),"comments":[]},
        {"key":"PAY-1035","summary":"Add circuit breaker to payment-service card-auth call path","type":"Task","priority":"High","status":"In Progress","assignee":"marcus.johnson@bank.internal","labels":["reliability","circuit-breaker"],"created":(NOW-timedelta(days=12)).isoformat(),"updated":(NOW-timedelta(days=3)).isoformat(),"comments":[]},
        {"key":"PAY-1036","summary":"Evaluate pgBouncer for connection pooling","type":"Task","priority":"Medium","status":"To Do","assignee":"tom.wilson@bank.internal","labels":["database","infrastructure"],"created":(NOW-timedelta(days=9)).isoformat(),"updated":(NOW-timedelta(days=9)).isoformat(),"comments":[]},
        {"key":"PAY-1037","summary":"Payment retry sends duplicate settlement messages","type":"Bug","priority":"Critical","status":"In Progress","assignee":"raj.patel@bank.internal","labels":["payments","bug","data-integrity"],"created":(NOW-timedelta(days=6)).isoformat(),"updated":(NOW-timedelta(days=1)).isoformat(),"comments":[]},
        {"key":"PAY-1038","summary":"Update Grafana dashboards for payment SLOs","type":"Task","priority":"Low","status":"To Do","assignee":"raj.patel@bank.internal","labels":["observability","slo"],"created":(NOW-timedelta(days=15)).isoformat(),"updated":(NOW-timedelta(days=15)).isoformat(),"comments":[]},
        {"key":"PAY-1039","summary":"PCI-DSS compliance scan remediate findings","type":"Task","priority":"High","status":"In Progress","assignee":"marcus.johnson@bank.internal","labels":["compliance","pci-dss"],"created":(NOW-timedelta(days=20)).isoformat(),"updated":(NOW-timedelta(days=4)).isoformat(),"comments":[]},
        {"key":"PAY-1041","summary":"Graceful degradation for fraud-engine outages","type":"Story","priority":"Medium","status":"To Do","assignee":"sarah.chen@bank.internal","labels":["fraud","reliability"],"created":(NOW-timedelta(days=3)).isoformat(),"updated":(NOW-timedelta(days=3)).isoformat(),"comments":[]},
    ]:
        i.setdefault("description",""); ISSUES[i["key"]]=i
_seed()

TRANSITIONS={"To Do":["In Progress"],"In Progress":["In Review","Done","Resolved"],"In Review":["In Progress","Done"],"Done":["Closed","In Progress"],"Resolved":["Closed","In Progress"],"Closed":[]}

def _next():
    global NEXT_NUM; k=f"PAY-{NEXT_NUM}"; NEXT_NUM+=1; return k

def _create(a):
    k=_next(); labels=[l.strip() for l in a.get("labels","").split(",") if l.strip()] if isinstance(a.get("labels"),str) else a.get("labels",[])
    iss={"key":k,"summary":a.get("summary","New issue"),"description":a.get("description",""),"type":a.get("type","Task"),"priority":a.get("priority","Medium"),"status":"To Do","assignee":a.get("assignee",""),"labels":labels,"created":NOW.isoformat(),"updated":NOW.isoformat(),"comments":[]}
    ISSUES[k]=iss; return {"key":k,"self":f"https://jira.bank.internal/browse/{k}","status":"To Do","summary":iss["summary"]}

def _comment(a):
    k=a.get("issue_key","")
    if k not in ISSUES: return {"error":f"Issue {k} not found"}
    c={"id":uuid.uuid4().hex[:8],"author":a.get("author","mcp-agent@bank.internal"),"body":a.get("body",""),"created":NOW.isoformat()}
    ISSUES[k]["comments"].append(c); ISSUES[k]["updated"]=NOW.isoformat(); return {"issue_key":k,"comment_id":c["id"],"status":"added"}

def _transition(a):
    k=a.get("issue_key",""); tgt=a.get("status","")
    if k not in ISSUES: return {"error":f"Issue {k} not found"}
    cur=ISSUES[k]["status"]; ok=TRANSITIONS.get(cur,[])
    if tgt not in ok: return {"error":f"Cannot transition from '{cur}' to '{tgt}'. Allowed: {ok}"}
    ISSUES[k]["status"]=tgt; ISSUES[k]["updated"]=NOW.isoformat(); return {"issue_key":k,"previous_status":cur,"new_status":tgt}

def _search(a):
    jql=a.get("jql",""); lim=int(a.get("limit",20)); res=list(ISSUES.values()); jl=jql.lower()
    if "status =" in jl or "status=" in jl:
        for tok in jql.split("AND"):
            tok=tok.strip()
            if tok.lower().startswith("status"): v=tok.split("=",1)[-1].strip().strip("'\""); res=[r for r in res if r["status"].lower()==v.lower()]
    if "labels in" in jl:
        m=re.search(r"labels\s+in\s*\(([^)]+)\)",jql,re.I)
        if m: ls=[l.strip().strip("'\"") for l in m.group(1).split(",")]; res=[r for r in res if any(l in r.get("labels",[]) for l in ls)]
    if "priority =" in jl or "priority=" in jl:
        for tok in jql.split("AND"):
            tok=tok.strip()
            if tok.lower().startswith("priority"): v=tok.split("=",1)[-1].strip().strip("'\""); res=[r for r in res if r["priority"].lower()==v.lower()]
    return {"total":len(res[:lim]),"issues":[{"key":r["key"],"summary":r["summary"],"status":r["status"],"priority":r["priority"],"assignee":r["assignee"],"labels":r["labels"],"updated":r["updated"]} for r in res[:lim]]}

def _oncall(a):
    t=a.get("team","default"); return {"team":t,"oncall":ONCALL.get(t,ONCALL["default"]),"schedule":"follow-the-sun","escalation_minutes":15}

def handle_tool(name,args):
    args=args or {}
    return {"issue.create":_create,"issue.comment":_comment,"issue.transition":_transition,"issue.search":_search,"team.oncall_lookup":_oncall}.get(name,lambda a:{"error":f"Unknown tool: {name}"})(args)

TOOLS = [
    {"name":"issue.create","description":"Create a Jira issue in PAY project. Returns new issue key.","inputSchema":{"type":"object","properties":{"summary":{"type":"string"},"description":{"type":"string","default":""},"type":{"type":"string","default":"Task"},"priority":{"type":"string","default":"Medium"},"assignee":{"type":"string","default":""},"labels":{"type":"string","default":""}},"required":["summary"]}},
    {"name":"issue.comment","description":"Add comment to a Jira issue.","inputSchema":{"type":"object","properties":{"issue_key":{"type":"string"},"body":{"type":"string"},"author":{"type":"string","default":"mcp-agent@bank.internal"}},"required":["issue_key","body"]}},
    {"name":"issue.transition","description":"Transition issue status. Valid: To Do, In Progress, In Review, Done, Resolved, Closed.","inputSchema":{"type":"object","properties":{"issue_key":{"type":"string"},"status":{"type":"string"}},"required":["issue_key","status"]}},
    {"name":"issue.search","description":"Search issues with JQL. Supports: status=X, priority=X, labels in (a,b). Combine with AND.","inputSchema":{"type":"object","properties":{"jql":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["jql"]}},
    {"name":"team.oncall_lookup","description":"Look up on-call engineer for a service/team.","inputSchema":{"type":"object","properties":{"team":{"type":"string"}},"required":["team"]}},
]

SERVER_INFO={"name":"jira-mcp","version":"1.0.0"}; CAPS={"tools":{}}
def rpc_ok(rid,r): return {"jsonrpc":"2.0","id":rid,"result":r}
def rpc_err(rid,c,m): return {"jsonrpc":"2.0","id":rid,"error":{"code":c,"message":m}}

def handle_msg(raw):
    try: msg=json.loads(raw) if isinstance(raw,(str,bytes)) else raw
    except: return rpc_err(None,-32700,"Parse error")
    rid=msg.get("id"); method=msg.get("method",""); params=msg.get("params",{})
    logger.info("MCP: method=%s id=%s",method,rid)
    if method=="initialize": return rpc_ok(rid,{"protocolVersion":"2024-11-05","serverInfo":SERVER_INFO,"capabilities":CAPS})
    if method=="notifications/initialized": return None
    if method=="tools/list": return rpc_ok(rid,{"tools":TOOLS})
    if method=="tools/call":
        try:
            r=handle_tool(params.get("name",""),params.get("arguments",{}))
            return rpc_ok(rid,{"content":[{"type":"text","text":json.dumps(r,default=str)}]})
        except Exception as e:
            logger.exception("Tool failed"); return rpc_ok(rid,{"content":[{"type":"text","text":json.dumps({"error":str(e)})}],"isError":True})
    if method=="shutdown": return rpc_ok(rid,{})
    return rpc_err(rid,-32601,f"Method not found: {method}")

app = FastAPI(title="Jira MCP Server")
sse_sessions = {}

@app.get("/health")
async def health():
    return {"status":"ok","server":SERVER_INFO["name"],"issues_count":len(ISSUES),"timestamp":datetime.now(timezone.utc).isoformat()}

@app.get("/sse")
async def sse_ep(request: Request):
    sid=uuid.uuid4().hex; q=asyncio.Queue(); sse_sessions[sid]=q
    logger.info("SSE connect: %s",sid)
    async def gen():
        yield {"event":"endpoint","data":f"/messages?session_id={sid}"}
        try:
            while True:
                if await request.is_disconnected(): break
                try:
                    m=await asyncio.wait_for(q.get(),timeout=30); yield {"event":"message","data":json.dumps(m,default=str)}
                except asyncio.TimeoutError: yield {"comment":"keepalive"}
        finally: sse_sessions.pop(sid,None); logger.info("SSE disconnect: %s",sid)
    return EventSourceResponse(gen())

@app.post("/messages")
async def sse_msg(request: Request, session_id: str=""):
    body=await request.json(); resp=handle_msg(body); q=sse_sessions.get(session_id)
    if q and resp: await q.put(resp); return JSONResponse({"status":"ok"})
    if resp: return JSONResponse(resp)
    return JSONResponse({"status":"ok"})

@app.websocket("/")
async def ws_ep(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw=await ws.receive_text(); r=handle_msg(raw)
            if r: await ws.send_text(json.dumps(r,default=str))
    except WebSocketDisconnect: pass

@app.websocket("/ws")
async def ws_alt(ws: WebSocket): await ws_ep(ws)
