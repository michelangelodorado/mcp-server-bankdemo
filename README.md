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

This demo walks through a realistic production incident using observability tools, deployments data, and Jira integration — all orchestrated by an LLM.

---

## 🚀 Setup

1. Open a chat in **LibreChat**
2. Ensure **both MCP servers are enabled**
3. Run the steps below one message at a time

---

## 🧭 Step-by-Step Demo

### **Step 1 — Set the Scene**

**Prompt:**

We're getting customer complaints that card payments are failing in mobile banking. Can you check the latency on card-auth-service for the last 60 minutes?


**Expected Behavior:**
- Calls `metrics.query_range`
- Shows latency spike from ~45ms → ~1800ms

---

### **Step 2 — Check Error Logs**

**Prompt:**

Search for ERROR logs on card-auth-service related to "timeout"


**Expected Behavior:**
- Calls `logs.search`
- Returns errors like:
  - `timeout acquiring db connection`
  - `context deadline exceeded`

---

### **Step 3 — Check the DB Pool**

**Prompt:**

What does the DB connection pool look like? Query db_pool_active_connections for card-auth-service


**Expected Behavior:**
- Calls `metrics.query_range`
- Shows pool usage rising from 12 → 50/50 (saturated)

---

### **Step 4 — Find Root Cause**

**Prompt:**

Were there any recent deployments that could have caused this?


**Expected Behavior:**
- Calls `deploys.list`
- Identifies:
  - `fraud-engine v2.14.0-rc3`
  - Lowered velocity threshold from **8 → 3 txns/min**
  - Deploy occurred just before latency spike

---

### **Step 5 — Check Blast Radius**

**Prompt:**

Show me the service dependency graph for payment-service


**Expected Behavior:**
- Calls `service.dependencies`
- Displays chain:


mobile-app → checkout → payment → card-auth → postgres


---

### **Step 6 — Find Who's On Call**

**Prompt:**

Who is on call for payment-service right now?


**Expected Behavior:**
- Calls `team.oncall_lookup`
- Returns:
  - **Raj Patel (Senior SRE)**

---

### **Step 7 — Create the Incident**

**Prompt:**

Create a SEV-1 Jira incident: "Card payment failures — DB pool exhaustion after fraud rule deploy". Set it as Critical priority, type Incident, labels sev-1,payments,incident. Assign to raj.patel@bank.internal


**Expected Behavior:**
- Calls `issue.create`
- Returns:
  - `PAY-1043`

---

### **Step 8 — Add Evidence**

**Prompt:**

Add a comment to PAY-1043 with the root cause summary: fraud-engine deploy v2.14.0-rc3 lowered velocity threshold causing auth request surge, saturating the DB connection pool on postgres-primary. Latency spiked to 1800ms, error rate hit 31%.


**Expected Behavior:**
- Calls `issue.comment`
- Attaches investigation summary

---

### **Step 9 — Transition to In Progress**

**Prompt:**

Move PAY-1043 to In Progress


**Expected Behavior:**
- Calls `issue.transition`
- Status changes:
  - `To Do → In Progress`

---

### **Step 10 — Verify the Backlog**

**Prompt:**

Search Jira for all Critical priority issues


**Expected Behavior:**
- Calls `issue.search` (JQL)
- Shows:
  - Newly created SEV-1
  - Other critical issues

---

## ⚡ One-Prompt Version (Fast Demo)

You can also run the entire flow in a single prompt:


Customers are reporting card payment failures in mobile banking. Investigate the issue using observability tools — check metrics, logs, and recent deploys. Identify the root cause, find who's on call, create a SEV-1 incident in Jira, add your findings as a comment, and transition it to In Progress.


**Expected Behavior:**
- The LLM chains all 10 tool calls automatically

---

## 🧠 What This Demonstrates

- Multi-step reasoning across systems
- Observability-driven debugging (metrics + logs)
- Deployment correlation
- Ownership discovery (on-call lookup)
- Automated incident management
- End-to-end workflow orchestration via LLM

---

## 🏁 Outcome

By the end of this demo, you will have:

- Identified the root cause of a production incident
- Created and updated a Jira ticket
- Demonstrated autonomous tool chaining in a real-world scenario

---
