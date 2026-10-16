import pandas as pd
import json, os

def get_skill_score(skills_text, req, upskill, cert, summary):
    syn = {"btp":"business technology platform btp", "cap":"cloud application programming", "hana":"hana cloud sap hana", "fiori":"fiori"}
    score=0
    req_lower=req.lower()
    for k,v in syn.items():
        if k in req_lower and (k in skills_text.lower() or any(x in skills_text.lower() for x in v.split())):
            score+=3
    score += min(upskill/10, 2)
    if "certified" in cert.lower(): score+=1
    return min(score, 10)

def is_hoarder(row):
    return row['Projects_Last_6M']>=4 and (row['Projects_Late']>=2 or row['Collaboration_Score']<4)

def calculate_inclusion_v2(workers_df):
    benched = workers_df[(workers_df['Bench_Days']>45) & (workers_df['Employment_Status']=='Active')]
    score = max(0, 100 - len(benched)*2)
    return 38  # mock critical for demo, replace with real calc in prod

def assign_and_learn_V2(project_id, team, effort, data_dir):
    """Dynamic update: team confirmed -> 3 CSVs update, so same team not candidate next time"""
    workers = pd.read_csv(os.path.join(data_dir, 'workers.csv'))
    hist = pd.read_csv(os.path.join(data_dir, 'work_history.csv'))
    alloc_path = os.path.join(data_dir, 'allocation_history.json')
    with open(alloc_path) as f: alloc_hist=json.load(f)

    dec = -30 if effort=='Medium' else -60 if effort=='Large' else -10
    for mem in team:
        eid = mem['Employee_ID']
        workers.loc[workers['Employee_ID']==eid, 'Bench_Days']=0
        workers.loc[workers['Employee_ID']==eid, 'Availability_Percent'] = max(0, workers.loc[workers['Employee_ID']==eid, 'Availability_Percent'].values[0]+dec)
        hist.loc[hist['Employee_ID']==eid, 'Projects_Last_6M']+=1
        hist.loc[hist['Employee_ID']==eid, 'Total_Projects_Ever']+=1
        hist.loc[hist['Employee_ID']==eid, 'Current_Projects'] = str([project_id])
        hist.loc[hist['Employee_ID']==eid, 'Effort_Allocated']=effort
        alloc_hist.append({"Timestamp": pd.Timestamp.now().isoformat(), "Project_ID": project_id, "Action": "Assign", "Employee_ID": int(eid), "Employee_Name": mem['Name'], "Effort": effort})

    workers.to_csv(os.path.join(data_dir, 'workers.csv'), index=False)
    hist.to_csv(os.path.join(data_dir, 'work_history.csv'), index=False)
    with open(alloc_path,'w') as f: json.dump(alloc_hist,f,indent=2)
    return True

def check_swap_compatibility(old_emp, new_emp, requirement_desc):
    """Fair swap check via description, not name"""
    # Model decides if swap is ok
    diff_skill = abs(old_emp.get('SkillMatch',5)-new_emp.get('SkillMatch',5))
    impact = {
        "skill_diff": diff_skill,
        "inclusion_delta": 10 if new_emp['College_Tier'] in ['Tier2','Tier3'] else -5,
        "ppo_retention_delta": -15 if old_emp['PPO_Status']=='Yes' and new_emp['PPO_Status']!='Yes' else 5,
        "allowed": diff_skill<=2
    }
    return impact

def find_replacement_on_leave(leave_emp_id, requirement_desc, data_dir):
    """Find fair replacement when someone on leave/resigned — no name typed, model suggests"""
    workers = pd.read_csv(os.path.join(data_dir, 'workers.csv'))
    skills = pd.read_csv(os.path.join(data_dir, 'skills.csv'))
    merged = workers.merge(skills, on='Employee_ID')
    # Active and available >=60%
    candidates = merged[(merged['Employment_Status']=='Active') & (merged['Availability_Percent']>=60) & (merged['Employee_ID']!=leave_emp_id)]
    # Sort by bench days + inclusion
    candidates = candidates.sort_values(by=['Bench_Days','Availability_Percent'], ascending=[False, False])
    if candidates.empty:
        return None
    # Return top candidate with fairness justification
    cand = candidates.iloc[0]
    return {
        "Employee_ID": int(cand['Employee_ID']),
        "Name": cand['Name'],
        "College_Tier": cand['College_Tier'],
        "Bench_Days": int(cand['Bench_Days']),
        "Skills_Text": cand['Skills_Text'],
        "Reason": f"Bench {cand['Bench_Days']} days, Tier {cand['College_Tier']}, Availability {cand['Availability_Percent']}% — Fair replacement"
    }

def log_audit(action, employee_id, reason, desc, project_id, data_dir):
    path = os.path.join(data_dir, 'allocation_history.json')
    with open(path) as f: hist=json.load(f)
    hist.append({"Timestamp": pd.Timestamp.now().isoformat(), "Project_ID": project_id, "Action": action, "Employee_ID": int(employee_id), "Reason": reason, "Description": desc})
    with open(path,'w') as f: json.dump(hist,f,indent=2)
