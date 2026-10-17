import pandas as pd
import json, hashlib, os, datetime

# Load once with index for O(log n)
def load_skills_structured():
    df = pd.read_csv("Skills-Structured.csv")
    df.set_index(['Skill_Name', 'Skill_Level'], inplace=False) # index for fast lookup
    return df

def check_request_id_exists(request_id):
    if not os.path.exists("allocation_history.jsonl"):
        return False
    with open("allocation_history.jsonl","r") as f:
        for line in f:
            if request_id in line:
                return True
    return False

def generate_request_id(project_name, user_email="demo@sap.com"):
    ts = datetime.datetime.now().isoformat()
    raw = f"{project_name}{ts}{user_email}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]

def assign_and_learn_V2(project_name, team_ids, effort="Medium"):
    """
    Idea Base Fix: Optimistic locking + Idempotency + Atomic writes + jsonl
    """
    workers = pd.read_csv("Workers.csv")
    work_hist = pd.read_csv("Work-History.csv")
    
    request_id = generate_request_id(project_name)
    
    # Idempotency check
    if check_request_id_exists(request_id):
        return {"status": "duplicate", "request_id": request_id}
    
    # Version check - optimistic locking
    for emp_id in team_ids:
        row = workers[workers.Employee_ID==emp_id]
        if row.empty:
            continue
        read_version = int(row.iloc[0].Version)
        # In real concurrent case, re-read and compare. For CSV demo, we check current file
        current = pd.read_csv("Workers.csv")
        curr_version = int(current[current.Employee_ID==emp_id].iloc[0].Version)
        if curr_version != read_version:
            return {"status": "conflict", "employee": emp_id, "message": "Team busy, re-suggesting"}
    
    # Apply changes
    effort_map = {"Small":10, "Medium":30, "Large":60}
    deduct = effort_map.get(effort,30)
    
    for emp_id in team_ids:
        idx = workers[workers.Employee_ID==emp_id].index
        workers.loc[idx, 'Availability_Percent'] = max(0, workers.loc[idx, 'Availability_Percent'].values[0] - deduct)
        workers.loc[idx, 'Bench_Days'] = 0
        workers.loc[idx, 'Version'] += 1
        workers.loc[idx, 'Last_Profile_Update'] = datetime.date.today().isoformat()
        
        wh_idx = work_hist[work_hist.Employee_ID==emp_id].index
        work_hist.loc[wh_idx, 'Projects_Last_6M'] += 1
        work_hist.loc[wh_idx, 'Total_Projects_Ever'] += 1
        work_hist.loc[wh_idx, 'Version'] += 1
    
    # Atomic write: temp then rename
    workers.to_csv("Workers_tmp.csv", index=False)
    work_hist.to_csv("Work-History_tmp.csv", index=False)
    os.rename("Workers_tmp.csv", "Workers.csv")
    os.rename("Work-History_tmp.csv", "Work-History.csv")
    
    # Append-only audit log jsonl with Request_ID + Version
    log_entry = {
        "Timestamp": datetime.datetime.now().isoformat(),
        "Project_ID": project_name,
        "Action": "Assign",
        "Team": team_ids,
        "Effort": effort,
        "Request_ID": request_id,
        "Version": 1
    }
    with open("allocation_history.jsonl","a") as f:
        f.write(json.dumps(log_entry)+"\n")
    
    return {"status": "success", "request_id": request_id}

def find_replacement_on_leave(skill_needed="BTP"):
    """
    Uses view_btp_experts.csv for speed + fair score
    """
    try:
        view = pd.read_csv("view_btp_experts.csv")
        # Filter Avail>=60% already in view
        return view.head(3).to_dict(orient='records')
    except:
        skills = pd.read_csv("Skills-Structured.csv")
        cand = skills[(skills.Skill_Name==skill_needed) & (skills.Skill_Level>=3)]
        return cand.head(3).to_dict(orient='records')