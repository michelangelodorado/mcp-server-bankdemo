"""Observability MCP Server with SSE + WebSocket transports."""
import asyncio, json, logging, math, random, sys, uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stderr)
logger = logging.getLogger("observability_mcp")

NOW = datetime.now(timezone.utc)
INCIDENT_START = NOW - timedelta(minutes=48)
DEPLOY_TIME = INCIDENT_START - timedelta(minutes=1)
WINDOW_START = NOW - timedelta(minutes=60)
TRACE_IDS = [uuid.uuid4().hex[:16] for _ in range(40)]

DEPENDENCY_MAP = {
    "mobile-app": {"calls": ["checkout-service"]},
    "checkout-service": {"calls": ["payment-service", "inventory-service"]},
    "payment-service": {"calls": ["card-auth-service", "fraud-engine"]},
    "card-auth-service": {"calls": ["postgres-primary", "redis-cache"]},
    "fraud-engine": {"calls": ["ml-model-store"]},
    "postgres-primary": {"calls": []}, "redis-cache": {"calls": []},
    "inventory-service": {"calls": ["postgres-primary"]}, "ml-model-store": {"calls": []},
}

def _gen_ts(service, metric, start_ts, end_ts, step):
    points, t = [], start_ts
    while t <= end_ts:
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        mi = (dt - INCIDENT_START).total_seconds() / 60.0
        if metric in ("latency_p99_ms", "latency_p50_ms"):
            base = 45.0 if "p99" in metric else 12.0
            value = base + (min(mi*80,1800) if "p99" in metric else min(mi*20,400)) * max(0,1-mi/120) if mi>0 else base
            if service=="card-auth-service": value*=2.2
            value += random.gauss(0, base*0.05)
        elif metric=="error_rate":
            base=0.002; value = base + min(mi*0.02,0.35)*max(0,1-mi/90) if mi>0 else base
            if service in ("card-auth-service","payment-service"): value*=3
            value = max(0, value+random.gauss(0,0.001))
        elif metric=="db_pool_active_connections":
            value = min(50,12+int(mi*1.5)) if mi>2 else 12; value+=random.randint(-1,1)
        elif metric=="db_pool_wait_time_ms":
            value = 2+min(mi*15,800) if mi>2 else 2.0; value+=random.gauss(0,1)
        elif metric=="requests_per_second":
            value = 420*(1+0.3*math.sin(dt.hour*math.pi/12)); value*=max(0.4,1-mi*0.008) if mi>5 else 1; value+=random.gauss(0,10)
        elif metric=="cpu_percent":
            value = min(92,35+mi*1.2) if mi>0 else 35.0; value+=random.gauss(0,2)
        else: value=random.uniform(10,50)
        points.append([t,round(value,3)]); t+=step
    return points

def _gen_topk(tp):
    if tp=="endpoints":
        return [{"endpoint":"/api/v2/card/authorize","service":"card-auth-service","p99_ms":1842.3,"error_rate":0.312},{"endpoint":"/api/v1/payment/process","service":"payment-service","p99_ms":1203.7,"error_rate":0.287},{"endpoint":"/api/v1/checkout/submit","service":"checkout-service","p99_ms":956.2,"error_rate":0.194},{"endpoint":"/api/v1/fraud/score","service":"fraud-engine","p99_ms":412.8,"error_rate":0.021},{"endpoint":"/api/v1/inventory/reserve","service":"inventory-service","p99_ms":87.1,"error_rate":0.003}]
    return [{"dependency":"postgres-primary","avg_latency_ms":823.4,"timeout_rate":0.28},{"dependency":"card-auth-service","avg_latency_ms":1842.3,"timeout_rate":0.31},{"dependency":"redis-cache","avg_latency_ms":4.2,"timeout_rate":0.0},{"dependency":"fraud-engine","avg_latency_ms":412.8,"timeout_rate":0.02}]

ERR_TMPLS = [("ERROR","timeout acquiring db connection from pool after {w}ms pool exhausted (active={a}/50)"),("ERROR","context deadline exceeded: card authorization timed out after 5000ms"),("ERROR","db pool wait exceeded threshold: waited {w}ms, max allowed 200ms"),("ERROR","payment processing failed: upstream card-auth-service returned 504"),("WARN","connection pool saturation alert: {a}/50 connections in use"),("WARN","retry attempt 3/3 for card-auth-service giving up"),("ERROR","transaction rollback: payment {p} failed after db timeout"),("INFO","circuit breaker OPEN for card-auth-service failure threshold exceeded 85%"),("ERROR","mobile-app checkout returned 500 root cause: payment-service timeout"),("WARN","postgres connection lease time exceeded 4s possible lock contention")]

def _gen_logs(service, level, limit, search):
    logs, t, idx = [], INCIDENT_START+timedelta(seconds=30), 0
    while t<NOW and len(logs)<200:
        mi=(t-INCIDENT_START).total_seconds()/60.0
        for _ in range(random.randint(1, max(1,int(8-mi*0.1)))):
            if len(logs)>=200: break
            lv,tmpl=ERR_TMPLS[idx%len(ERR_TMPLS)]
            if level and level.upper()!="ALL" and lv!=level.upper(): idx+=1; continue
            a=min(50,12+int(mi*1.5)); w=int(200+mi*15); p=f"PAY-{random.randint(100000,999999)}"
            msg=tmpl.format(w=w,a=a,p=p)
            if search and search.lower() not in msg.lower(): idx+=1; continue
            svc=service if service else random.choice(["card-auth-service","payment-service","checkout-service"])
            logs.append({"timestamp":t.isoformat(),"level":lv,"service":svc,"trace_id":random.choice(TRACE_IDS),"message":msg}); idx+=1
        t+=timedelta(seconds=random.randint(3,15))
    if service: logs=[l for l in logs if l["service"]==service]
    return logs[:limit]

def _gen_deploys():
    return [{"id":"deploy-4471","service":"fraud-engine","version":"2.14.0-rc3","description":"Updated fraud rule: lowered velocity threshold from 8 to 3 txns/min for high-risk MCCs","deployed_by":"sarah.chen@bank.internal","timestamp":DEPLOY_TIME.isoformat(),"status":"completed","change_ticket":"CHG-8834"},{"id":"deploy-4470","service":"card-auth-service","version":"5.2.1","description":"Routine dependency bump no logic changes","deployed_by":"ci-pipeline","timestamp":(DEPLOY_TIME-timedelta(hours=3)).isoformat(),"status":"completed","change_ticket":"CHG-8820"},{"id":"deploy-4469","service":"mobile-app","version":"4.17.0","description":"UI polish for card management screen","deployed_by":"ci-pipeline","timestamp":(DEPLOY_TIME-timedelta(hours=8)).isoformat(),"status":"completed","change_ticket":"CHG-8815"}]

TOOLS = [
    {"name":"metrics_query_range","description":"Query time-series metrics for a service. Metrics: latency_p99_ms, latency_p50_ms, error_rate, db_pool_active_connections, db_pool_wait_time_ms, requests_per_second, cpu_percent","inputSchema":{"type":"object","properties":{"service":{"type":"string","description":"Service name e.g. card-auth-service"},"metric":{"type":"string","description":"Metric name"},"start":{"type":"string","description":"Start time ISO-8601 or -60m"},"end":{"type":"string","description":"End time or now"},"step_seconds":{"type":"integer","default":60}},"required":["service","metric"]}},
    {"name":"metrics_topk","description":"Top slow endpoints or dependencies","inputSchema":{"type":"object","properties":{"type":{"type":"string","default":"endpoints"},"k":{"type":"integer","default":5}}}},
    {"name":"logs_search","description":"Search structured logs. Find DB timeouts, connection pool errors, payment failures.","inputSchema":{"type":"object","properties":{"service":{"type":"string","default":""},"level":{"type":"string","default":"ALL"},"search":{"type":"string","default":""},"limit":{"type":"integer","default":30}}}},
    {"name":"deploys_list","description":"List recent deployments. Correlate incidents with rollouts.","inputSchema":{"type":"object","properties":{"service":{"type":"string","default":""},"limit":{"type":"integer","default":10}}}},
    {"name":"service_dependencies","description":"Service dependency graph showing call chains.","inputSchema":{"type":"object","properties":{"service":{"type":"string","default":""}}}},
]

def _parse_time(val, default):
    if not val or val=="now": return NOW
    if val.startswith("-") and val.endswith("m"):
        try: return NOW-timedelta(minutes=int(val[1:-1]))
        except: pass
    try: return datetime.fromisoformat(val.replace("Z","+00:00"))
    except: return default

def handle_tool(name, args):
    args=args or {}
    if name=="metrics_query_range":
        svc=args.get("service","card-auth-service"); m=args.get("metric","latency_p99_ms")
        s=_parse_time(args.get("start","-60m"),WINDOW_START); e=_parse_time(args.get("end","now"),NOW); step=int(args.get("step_seconds",60))
        pts=_gen_ts(svc,m,s.timestamp(),e.timestamp(),step)
        return {"service":svc,"metric":m,"start":s.isoformat(),"end":e.isoformat(),"step_seconds":step,"datapoints":pts,"summary":{"count":len(pts),"min":round(min(p[1] for p in pts),3) if pts else 0,"max":round(max(p[1] for p in pts),3) if pts else 0,"avg":round(sum(p[1] for p in pts)/len(pts),3) if pts else 0}}
    if name=="metrics_topk": return {"type":args.get("type","endpoints"),"results":_gen_topk(args.get("type","endpoints"))[:int(args.get("k",5))]}
    if name=="logs_search": return {"total_matched":0,"entries":_gen_logs(args.get("service",""),args.get("level","ALL"),int(args.get("limit",30)),args.get("search",""))}
    if name=="deploys_list":
        d=_gen_deploys(); svc=args.get("service","")
        if svc: d=[x for x in d if x["service"]==svc]
        return {"deploys":d[:int(args.get("limit",10))]}
    if name=="service_dependencies":
        svc=args.get("service","")
        return {"root":svc,"graph":{svc:DEPENDENCY_MAP[svc]}} if svc and svc in DEPENDENCY_MAP else {"graph":DEPENDENCY_MAP}
    return {"error":f"Unknown tool: {name}"}

SERVER_INFO={"name":"observability-mcp","version":"1.0.0"}
CAPS={"tools":{}}

def rpc_ok(rid,result): return {"jsonrpc":"2.0","id":rid,"result":result}
def rpc_err(rid,code,msg): return {"jsonrpc":"2.0","id":rid,"error":{"code":code,"message":msg}}

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

app = FastAPI(title="Observability MCP Server")
sse_sessions = {}

@app.get("/health")
async def health():
    return {"status":"ok","server":SERVER_INFO["name"],"timestamp":datetime.now(timezone.utc).isoformat()}

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
