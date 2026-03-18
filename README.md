# MCP Banking Demo

## Start
```
cd mcp-server-bankdemo && docker compose up --build
```

## LibreChat config (librechat.yaml)
```yaml
mcpSettings:
  allowedDomains:
    - "10.1.10.102"
mcpServers:
  observability:
    type: sse
    url: http://10.1.10.102:8001/sse
    timeout: 30000
  jira:
    type: sse
    url: http://10.1.10.102:8002/sse
    timeout: 30000
```

## Test
```
pip install websockets httpx
python test_mcp.py 10.1.10.102
```

# 📊 Demo Script: Incident Investigation with MCP + LibreChat

This demo walks through a realistic production incident using observability tools and Jira integration, orchestrated by an LLM.

---

## 🚀 Setup

1. Open a chat in **LibreChat**
2. Ensure **both MCP servers are enabled**
3. Send the prompts below **one at a time**

---

## 🧭 Step-by-Step Demo

### Step 1 — Set the scene

**Prompt**

We're getting customer complaints that card payments are failing in mobile banking. Can you check the latency on card-auth-service for the last 60 minutes?


**Expected behavior**
- Calls `metrics_query_range`
- Shows `card-auth-service` latency rising sharply over the last hour
- Peak latency reaches roughly **1.8–2.0s**

---

### Step 2 — Check error logs

**Prompt**

Search for ERROR logs on card-auth-service related to "timeout"


**Expected behavior**
- Calls `logs_search`
- Shows repeated timeout-related failures such as:
  - `timeout acquiring db connection`
  - `context deadline exceeded`

---

### Step 3 — Check the DB pool

**Prompt**

What does the DB connection pool look like? Query db_pool_active_connections for card-auth-service


**Expected behavior**
- Calls `metrics_query_range`
- Shows DB pool usage climbing from around **12** to **50/50**
- Confirms the pool is saturated

---

### Step 4 — Find root cause

**Prompt**

Were there any recent deployments that could have caused this?


**Expected behavior**
- Calls `deploys_list`
- Reveals a recent deploy of **fraud-engine v2.14.0-rc3**
- Shows the velocity threshold was lowered from **8** to **3 txns/min**
- The deploy occurred shortly before the incident spike

---

### Step 5 — Check the blast radius

**Prompt**

Show me the service dependency graph for payment-service


**Expected behavior**
- Calls `service_dependencies`
- Shows the immediate dependencies of `payment-service`:
  - `card-auth-service`
  - `fraud-engine`

---

### Step 6 — Find who's on call

**Prompt**

Who is on call for payment-service right now?


**Expected behavior**
- Calls `team_oncall_lookup`
- Returns **Raj Patel, Senior SRE**

---

### Step 7 — Create the incident

**Prompt**

Create a SEV-1 Jira incident: "Card payment failures — DB pool exhaustion after fraud rule deploy". Set it as Critical priority, type Incident, labels sev-1,payments,incident. Assign to raj.patel@bank.internal


**Expected behavior**
- Calls `issue_create`
- Creates the incident and returns **PAY-1043**

---

### Step 8 — Add evidence

**Prompt**

Add a comment to PAY-1043 with the root cause summary: fraud-engine deploy v2.14.0-rc3 lowered velocity threshold causing auth request surge, saturating the DB connection pool on postgres-primary. Latency spiked to around 1800ms.


**Expected behavior**
- Calls `issue_comment`
- Adds the investigation summary to the incident

---

### Step 9 — Transition to In Progress

**Prompt**

Move PAY-1043 to In Progress


**Expected behavior**
- Calls `issue_transition`
- Changes status from **To Do** to **In Progress**

---

### Step 10 — Verify the backlog

**Prompt**

Search Jira for all Critical priority issues


**Expected behavior**
- Calls `issue_search`
- Shows the newly created SEV-1 alongside other existing Critical issues

---

## ⚡ One-Prompt Version

You can also run the full demo in one prompt:


Customers are reporting card payment failures in mobile banking. Investigate the issue using observability tools — check metrics, logs, and recent deploys. Identify the root cause, find who's on call, create a SEV-1 incident in Jira, add your findings as a comment, and transition it to In Progress.


**Expected behavior**
- The LLM chains the full workflow automatically across observability and Jira tools

---

## 🧠 What This Demonstrates

- Multi-step reasoning across operational systems  
- Metrics and log correlation  
- Deployment-aware root cause investigation  
- Dependency analysis  
- On-call ownership discovery  
- Automated incident creation and workflow updates  

---

## 🏁 Outcome

By the end of this demo, you will have:

- Identified the likely source of the payment failure incident  
- Correlated latency, logs, DB saturation, and a recent deploy  
- Created and updated a Jira incident  
- Demonstrated autonomous tool chaining in a realistic incident-response workflow  

---
