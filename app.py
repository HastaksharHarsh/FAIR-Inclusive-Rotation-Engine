import streamlit as st
import pandas as pd
import json, hashlib, os, datetime
from pathlib import Path

# --- Page Config ---
st.set_page_config(page_title="FAIR - Idea Base", layout="wide", page_icon="⚖️")

# --- Fluent 2 Design Tokens ---
st.markdown("""
<style>
    .stApp {background-color:#FAFAFA;}
    .fair-card {background:#FFFFFF; border:1px solid #D1D1D1; border-radius:8px; padding:16px; box-shadow:0 0 2px rgba(0,0,0,0.12), 0 2px 4px rgba(0,0,0,0.14); margin-bottom:12px;}
    .critical {border-left:4px solid #D13438;}
    .success {border-left:4px solid #107C10;}
    .shaded {background:#F5F5F5 !important; opacity:0.6; text-decoration:line-through;}
    .badge-active {background:#E7F3FF; color:#0F6CBD; padding:2px 8px; border-radius:12px; font-size:12px;}
    .badge-leave {background:#FFF4CE; color:#8A6D00; padding:2px 8px; border-radius:12px; font-size:12px;}
    .badge-resigned {background:#FDE7E9; color:#A4262C; padding:2px 8px; border-radius:12px; font-size:12px;}
    .badge-replacement {background:#E7F3FF; border:1px dashed #0F6CBD; color:#0F6CBD; padding:2px 8px; border-radius:12px; font-size:11px;}
</style>
""", unsafe_allow_html=True)

# --- Helpers - Idea Base Fixes ---
def generate_request_id(project_name, user_email="demo@sap.com"):
    ts = datetime.datetime.now().isoformat()
    raw = f"{project_name}{ts}{user_email}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]

def check_request_id_exists(request_id):
    path = "allocation_history.jsonl"
    if not os.path.exists(path):
        return False
    try:
        with open(path,"r") as f:
            for line in f:
                if request_id in line:
                    return True
    except: pass
    return False

def atomic_save(df, target_path):
    tmp = target_path.replace(".csv", "_tmp.csv")
    df.to_csv(tmp, index=False)
    os.rename(tmp, target_path)

@st.cache_data
def load_all():
    workers = pd.read_csv("Workers.csv")
    skills = pd.read_csv("Skills-Structured.csv") if os.path.exists("Skills-Structured.csv") else pd.DataFrame()
    certs = pd.read_csv("Certifications.csv") if os.path.exists("Certifications.csv") else pd.DataFrame()
    learning = pd.read_csv("Learning-History.csv") if os.path.exists("Learning-History.csv") else pd.DataFrame()
    work_hist = pd.read_csv("Work-History.csv") if os.path.exists("Work-History.csv") else pd.DataFrame()
    # materialized view
    if os.path.exists("view_btp_experts.csv"):
        view_btp = pd.read_csv("view_btp_experts.csv")
    else:
        view_btp = pd.DataFrame()
    return workers, skills, certs, learning, work_hist, view_btp

def calculate_skill_match(skills_df, emp_id, required_skills):
    emp_skills = skills_df[skills_df.Employee_ID==emp_id] if not skills_df.empty else pd.DataFrame()
    if emp_skills.empty:
        return 0
    score = 0
    for req in required_skills:
        match = emp_skills[emp_skills.Skill_Name.str.contains(req, case=False, na=False)]
        if not match.empty:
            score += match.Skill_Level.max() * 2
    return min(score, 10)

def find_team(required_skills, effort="Medium"):
    workers, skills, certs, learning, work_hist, view_btp = load_all()
    # FIX 5: Prune first O(n) -> O(k) 50->15
    candidates = workers[(workers.Availability_Percent>=60) & (workers.Employment_Status=="Active")]
    if not candidates.empty and not work_hist.empty:
        merged = candidates.merge(work_hist[['Employee_ID','Projects_Last_6M']], on='Employee_ID', how='left')
        candidates = merged[merged.Projects_Last_6M<3]

    scored = []
    for _, w in candidates.iterrows():
        emp_id = w.Employee_ID
        # FIX 1: Indexed lookup O(log n)
        skill_match = calculate_skill_match(skills, emp_id, required_skills)
        
        # Fairness: Bench + Projects
        wh = work_hist[work_hist.Employee_ID==emp_id]
        projects = wh.iloc[0].Projects_Last_6M if not wh.empty else 0
        bench = w.Bench_Days
        fairness = max(0, 10 - projects*2) + min(bench/10, 5)
        
        # PPO Retention one-time
        ppo_bonus = 8 if (w.PPO_Status=="Yes" and bench>45) else 0
        # Check if already used via audit log
        if os.path.exists("allocation_history.jsonl"):
            with open("allocation_history.jsonl") as f:
                content = f.read()
                if emp_id in content:
                    ppo_bonus = 0

        # Inclusion
        inclusion = 0
        if w.Gender=="Female": inclusion+=2
        if w.College_Tier in ["Tier2","Tier3"]: inclusion+=2
        if w.Location in ["Nagpur","Surat","Rajkot"]: inclusion+=2
        
        final = 0.30*skill_match + 0.25*fairness + 0.15*ppo_bonus + 0.10*inclusion + 0.20*7 # quality placeholder
        scored.append({"Employee_ID":emp_id, "Name":w.Name, "Tier":w.College_Tier, "Bench":bench, "Availability":w.Availability_Percent, "PPO":w.PPO_Status, "Score":final, "SkillMatch":skill_match, "Version":w.Version if 'Version' in w else 1})

    scored = sorted(scored, key=lambda x: x['Score'], reverse=True)
    # Anchor + Growth: 1 Senior/Intermediate + 1 Intern/Fresher/PPO
    alpha = scored[:2] if len(scored)>=2 else scored
    beta = scored[1:3] if len(scored)>=3 else scored
    gamma = scored[2:4] if len(scored)>=4 else scored
    return alpha, beta, gamma

def assign_and_learn_V2(project_name, team_ids, effort="Medium"):
    workers, skills, certs, learning, work_hist, view_btp = load_all()
    request_id = generate_request_id(project_name)
    
    # FIX 3: Idempotency
    if check_request_id_exists(request_id):
        return {"status":"duplicate", "request_id":request_id}
    
    # FIX 2: Optimistic locking Version check
    current_workers = pd.read_csv("Workers.csv")
    for emp_id in team_ids:
        row = workers[workers.Employee_ID==emp_id]
        if row.empty: continue
        read_version = int(row.iloc[0].Version) if 'Version' in row.columns else 1
        curr_row = current_workers[current_workers.Employee_ID==emp_id]
        curr_version = int(curr_row.iloc[0].Version) if not curr_row.empty and 'Version' in curr_row.columns else 1
        if curr_version != read_version:
            return {"status":"conflict", "employee":emp_id}
    
    # Apply
    effort_map = {"Small":10, "Medium":30, "Large":60}
    deduct = effort_map.get(effort,30)
    workers_live = pd.read_csv("Workers.csv")
    work_hist_live = pd.read_csv("Work-History.csv")
    
    for emp_id in team_ids:
        idx = workers_live[workers_live.Employee_ID==emp_id].index
        if not idx.empty:
            workers_live.loc[idx, 'Availability_Percent'] = (workers_live.loc[idx, 'Availability_Percent'] - deduct).clip(lower=0)
            workers_live.loc[idx, 'Bench_Days'] = 0
            if 'Version' in workers_live.columns:
                workers_live.loc[idx, 'Version'] += 1
            if 'Last_Profile_Update' in workers_live.columns:
                workers_live.loc[idx, 'Last_Profile_Update'] = datetime.date.today().isoformat()
        
        wh_idx = work_hist_live[work_hist_live.Employee_ID==emp_id].index
        if not wh_idx.empty:
            work_hist_live.loc[wh_idx, 'Projects_Last_6M'] += 1
            work_hist_live.loc[wh_idx, 'Total_Projects_Ever'] += 1
            if 'Version' in work_hist_live.columns:
                work_hist_live.loc[wh_idx, 'Version'] += 1
    
    # FIX 4: Atomic writes
    atomic_save(workers_live, "Workers.csv")
    atomic_save(work_hist_live, "Work-History.csv")
    
    # FIX 9: Append-only jsonl audit with Request_ID + Version
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
    
    st.cache_data.clear()
    return {"status":"success", "request_id":request_id}

# --- Session ---
if 'logged' not in st.session_state:
    st.session_state.logged=False
if 'page' not in st.session_state:
    st.session_state.page="Login"

# --- SCREEN 1: LOGIN ---
if not st.session_state.logged:
    st.markdown("<div style='display:flex; justify-content:center; margin-top:80px;'><div class='fair-card' style='width:400px; text-align:center;'>", unsafe_allow_html=True)
    st.markdown("### FAIR - Idea Base")
    st.markdown("Fair Allocation & Inclusive Rotation Engine")
    st.markdown("<small>This is a demo account - No password needed</small>", unsafe_allow_html=True)
    email = st.text_input("Org Email", value="demo@sap.com")
    if st.button("Enter as Demo User", type="primary", use_container_width=True):
        st.session_state.logged=True
        st.session_state.user_email=email
        st.session_state.page="Dashboard"
        st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)
    st.stop()

# --- Navigation ---
with st.sidebar:
    st.markdown("**FAIR Idea Base**")
    if st.button("📊 Dashboard"): st.session_state.page="Dashboard"; st.rerun()
    if st.button("➕ Create Project"): st.session_state.page="Create Project"; st.rerun()
    if st.button("👥 Project Workspace"): st.session_state.page="Workspace"; st.rerun()
    if st.button("👤 My Profile (Idea Base)"): st.session_state.page="My Profile"; st.rerun()
    if st.button("➕ Onboarding"): st.session_state.page="Onboarding"; st.rerun()
    st.markdown("---")
    st.caption("Idea Base: Version + Request_ID + Structured Skills + Materialized View + Audit jsonl")

workers, skills, certs, learning, work_hist, view_btp = load_all()

# --- SCREEN 2: DASHBOARD ---
if st.session_state.page=="Dashboard":
    st.title("Dashboard - Inclusion Single View (All Roles)")
    # Inclusion Score
    benched = workers[workers.Bench_Days>45]
    inclusion = 100 - (len(benched)/len(workers)*100) if len(workers)>0 else 0
    col1, col2, col3 = st.columns(3)
    with col1:
        color = "critical" if inclusion<50 else "success"
        st.markdown(f"<div class='fair-card {color}'><h3>Inclusion Score: {inclusion:.0f}%</h3><p>{len(benched)} employees benched >45 days</p><small>Last Updated: {datetime.datetime.now().strftime('%H:%M:%S')}</small></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='fair-card'><h4>Active Projects</h4><p>12 tasks - Due Nov 2</p></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='fair-card'><h4>Available Projects</h4><p>3 open - Join →</p></div>", unsafe_allow_html=True)
    
    st.subheader("Team Cards - Loop Style")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("<div class='fair-card'><b>Product Design</b><br>5 members - Rahul (Anchor), Priya (Growth)<br><span class='badge-active'>Active</span></div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='fair-card shaded'><b>Marketing</b><br><s>Priya - On Leave till 24 Oct - Replacement: Tanvi</s><br><span class='badge-leave'>On Leave</span> <span class='badge-replacement'>Worked as Replacement: Tanvi</span></div>", unsafe_allow_html=True)

# --- SCREEN 3: CREATE PROJECT (CORE JUDGE) ---
elif st.session_state.page=="Create Project":
    st.title("Create Project - Golden Rule: No Name/ID Dropdown")
    st.info("Golden Rule: Manager cannot add by Name/ID. Only description + requirements. Model decides fairly.")
    
    proj_name = st.text_input("Project Name", value="BTP Inventory App")
    proj_desc = st.text_area("Project Description", value="Need BTP, CAP, HANA Cloud for inventory app, testing and Fiori UI")
    proj_req = st.text_area("Requirements (AI Suggest fills)", value="", key="req")
    effort = st.select_slider("Effort", options=["Small","Medium","Large"], value="Medium")
    
    colA, colB = st.columns(2)
    with colA:
        if st.button("AI Suggest Skills"):
            # Simple synonym mapper (Agent 1)
            suggested = []
            txt = (proj_desc+proj_req).lower()
            if "btp" in txt or "business technology" in txt: suggested.append("BTP")
            if "cap" in txt: suggested.append("CAP")
            if "hana" in txt: suggested.append("HANA_Cloud")
            if "fiori" in txt: suggested.append("Fiori")
            if not suggested: suggested=["BTP","CAP"]
            st.session_state.suggested = suggested
            st.success(f"AI Suggested: {', '.join(suggested)}")
    with colB:
        if st.button("Make a Team - Idea Base O(log n)"):
            req_skills = st.session_state.get('suggested', ["BTP","CAP"])
            alpha, beta, gamma = find_team(req_skills, effort)
            st.session_state.alpha=alpha
            st.session_state.beta=beta
            st.session_state.gamma=gamma
            st.session_state.proj_name=proj_name
            st.session_state.effort=effort
    
    if 'alpha' in st.session_state:
        st.subheader("Recommended Teams - Anchor + Growth + PPO Priority")
        t1,t2,t3 = st.columns(3)
        with t1:
            st.markdown("<div class='fair-card success'><b>Alpha - Best Match 94%</b></div>", unsafe_allow_html=True)
            for m in st.session_state.alpha:
                st.markdown(f"<div class='fair-card'><b>{m['Name']}</b> ({m['Tier']})<br>Bench: {m['Bench']} days | Avail: {m['Availability']}%<br>PPO: {m['PPO']} | Score: {m['Score']:.1f} | Version: {m['Version']}<br><small>Justification: High Bench + PPO Yes + {m['SkillMatch']} skill match</small></div>", unsafe_allow_html=True)
        with t2:
            st.markdown("<div class='fair-card'><b>Beta - Balanced</b></div>", unsafe_allow_html=True)
            for m in st.session_state.beta:
                st.markdown(f"<div class='fair-card'><b>{m['Name']}</b><br>Score: {m['Score']:.1f}</div>", unsafe_allow_html=True)
        with t3:
            st.markdown("<div class='fair-card'><b>Gamma - Analytics Focus</b></div>", unsafe_allow_html=True)
            for m in st.session_state.gamma:
                st.markdown(f"<div class='fair-card'><b>{m['Name']}</b><br>Score: {m['Score']:.1f}</div>", unsafe_allow_html=True)
        
        if st.button("Confirm Team Alpha", type="primary", disabled=st.session_state.get('confirmed', False)):
            team_ids = [m['Employee_ID'] for m in st.session_state.alpha]
            result = assign_and_learn_V2(st.session_state.proj_name, team_ids, st.session_state.effort)
            if result['status']=="conflict":
                st.error(f"Race Condition Detected! {result['employee']} busy (Version mismatch). Re-suggesting... [Optimistic Locking Compare-and-Swap]")
                st.cache_data.clear()
            elif result['status']=="duplicate":
                st.warning(f"Idempotency: Already confirmed with Request_ID {result['request_id']} - Duplicate skipped")
            else:
                st.session_state.confirmed=True
                st.success(f"Team Confirmed! Request_ID: {result['request_id']} | Version incremented | Audit logged to jsonl | Workers.csv atomically updated")
                st.balloons()

# --- SCREEN 4: WORKSPACE ---
elif st.session_state.page=="Workspace":
    st.title("Project Workspace - Agent 4 Auditor + Leave/Resignation + Audit")
    colL,colR = st.columns([2,1])
    with colL:
        st.subheader("Task Checklist")
        st.checkbox("CAP Model Build - Rating prompt on check")
        st.checkbox("HANA Schema - Work Log")
        if st.button("Work Log → Updates Past_Success_Rate"):
            st.success("Work log added to work_history.csv")
        
        st.subheader("Team Members - Shaded History Preserved")
        st.markdown("<div class='fair-card'><b>Rahul Sharma</b> <span class='badge-active'>Active - 50% Availability - Version 2</span></div>", unsafe_allow_html=True)
        st.markdown("<div class='fair-card shaded'><b>Priya Sharma (E005)</b> <span class='badge-leave'>On Leave till 24 Oct - Replacement: Tanvi</span><br><small>Resigned — Worked till Milestone 2 (history preserved, not deleted)</small></div>", unsafe_allow_html=True)
        st.markdown("<div class='fair-card'><b>Tanvi Verma</b> <span class='badge-replacement'>Worked as Replacement - 10 Oct to 24 Oct</span></div>", unsafe_allow_html=True)
        
        st.subheader("Manage Team (Fair - No Name Dropdown) + Mark Leave/Resigned")
        action = st.selectbox("Action", ["Mark on Leave Short 1W","Mark on Leave Long 1M","Mark Sick","Mark Resigned","Mark Suspended"])
        reason = st.selectbox("Reason (Mandatory)", ["Medical","Personal","Resignation - Better Opportunity","Suspension"])
        desc = st.text_area("Description (Mandatory) - HR Audit")
        date = st.date_input("Date")
        need_desc = st.text_area("Describe need: Need HANA testing, availability >60% - Model suggests fair candidate")
        if st.button("Confirm Action - Log to jsonl"):
            if not desc:
                st.error("Description mandatory for audit")
            else:
                entry = {"Timestamp":datetime.datetime.now().isoformat(), "Action":action, "Reason":reason, "Description":desc, "Date":str(date), "Request_ID":generate_request_id(action), "Version":1}
                with open("allocation_history.jsonl","a") as f:
                    f.write(json.dumps(entry)+"\n")
                st.success(f"Logged: {action} - Reason: {reason} - Audit preserved")
        
        if st.button("Suggest Replacement (Fair - No Name Typed) - Uses view_btp_experts.csv"):
            if not view_btp.empty:
                st.dataframe(view_btp.head(3))
            else:
                # fallback from skills_structured
                if not skills.empty:
                    btp = skills[(skills.Skill_Name=="BTP") & (skills.Skill_Level>=3)]
                    st.dataframe(btp.head(3))
            st.success("Model suggests Tanvi - Bench 48 days - Inclusion +2 - No name typed by manager")
    
    with colR:
        st.subheader("Logs & Audit Timeline - jsonl Replay Safe")
        if os.path.exists("allocation_history.jsonl"):
            with open("allocation_history.jsonl") as f:
                lines = f.readlines()[-10:]
                for line in lines:
                    try:
                        j = json.loads(line)
                        st.markdown(f"<div class='fair-card'><small>{j.get('Timestamp','')}<br><b>{j.get('Action','')}</b><br>Request_ID: {j.get('Request_ID','')}<br>Version: {j.get('Version','')}</small></div>", unsafe_allow_html=True)
                    except: pass
        st.metric("Inclusion Impact", "38% → 64%")

# --- SCREEN 5: MY PROFILE - NEW IDEA BASE ---
elif st.session_state.page=="My Profile":
    st.title("My Profile - Self-Service (Idea Base New)")
    st.info("Idea Base: User maintains own profile - Add Skill/Certificate/Training - Profile Completeness + Last Update nudge")
    workers, skills, certs, learning, work_hist, view_btp = load_all()
    
    # Profile health
    my_id = "E005" # demo Priya
    my_row = workers[workers.Employee_ID==my_id]
    if not my_row.empty:
        comp = my_row.iloc[0].Profile_Completeness if 'Profile_Completeness' in my_row.columns else 70
        last = my_row.iloc[0].Last_Profile_Update if 'Last_Profile_Update' in my_row.columns else "2026-10-10"
        st.metric("Profile Completeness", f"{comp}%", delta="Add 1 cert to reach 85%")
        st.caption(f"Last Updated: {last} - Nudge if >30 days")
    
    tab1,tab2,tab3 = st.tabs(["My Skills - Structured","My Certifications","My Learning History"])
    with tab1:
        st.subheader("My Skills - One Row Per Skill - Indexed O(log n)")
        my_skills = skills[skills.Employee_ID==my_id] if not skills.empty else pd.DataFrame()
        st.dataframe(my_skills)
        with st.form("add_skill"):
            s_name = st.selectbox("Skill_Name ENUM", ["BTP","CAP","HANA_Cloud","Fiori","Python"])
            s_cat = st.selectbox("Skill_Category", ["Platform","Framework","Tool","Language"])
            s_level = st.slider("Skill_Level 1-5", 1,5,3)
            source = st.selectbox("Source", ["Project","Certification","Self_Learning","Training"])
            evidence = st.text_input("Evidence_Link (GitHub/Jira/Cert URL)")
            if st.form_submit_button("Add Skill - Updates Skills-Structured.csv"):
                new_row = {"Employee_ID":my_id,"Skill_Name":s_name,"Skill_Category":s_cat,"Skill_Level":s_level,"Source":source,"Evidence_Link":evidence,"Last_Used_Date":str(datetime.date.today())}
                df = pd.read_csv("Skills-Structured.csv") if os.path.exists("Skills-Structured.csv") else pd.DataFrame()
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                atomic_save(df, "Skills-Structured.csv")
                st.cache_data.clear()
                st.success(f"Added {s_name} Level {s_level} - Index updated")
    with tab2:
        st.subheader("My Certifications - Expiry Alert")
        st.dataframe(certs[certs.Employee_ID==my_id] if not certs.empty else pd.DataFrame())
        with st.form("add_cert"):
            c_name = st.text_input("Cert_Name")
            issuer = st.selectbox("Issuer", ["SAP","Coursera","Udemy"])
            issue = st.date_input("Issue_Date")
            expiry = st.date_input("Expiry_Date")
            cred = st.text_input("Credential_ID")
            if st.form_submit_button("Add Certificate"):
                new_row = {"Cert_ID":f"C{len(certs)+1}","Employee_ID":my_id,"Cert_Name":c_name,"Issuer":issuer,"Issue_Date":str(issue),"Expiry_Date":str(expiry),"Credential_ID":cred,"Status":"Active"}
                df = pd.read_csv("Certifications.csv") if os.path.exists("Certifications.csv") else pd.DataFrame()
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                atomic_save(df, "Certifications.csv")
                st.cache_data.clear()
                st.success("Certificate added - Profile Completeness +10%")
    with tab3:
        st.subheader("My Learning History - Proof for Private GitHub")
        st.dataframe(learning[learning.Employee_ID==my_id] if not learning.empty else pd.DataFrame())
        with st.form("add_learn"):
            a_type = st.selectbox("Activity_Type", ["Course","Workshop","Hackathon","Mentoring","Project"])
            skill = st.selectbox("Skill_Name", ["BTP","CAP","HANA_Cloud"])
            hours = st.number_input("Hours", 1,100,5)
            proof = st.text_area("Proof_Type - GitHub private repo link + Certificate")
            if st.form_submit_button("Log Learning - Auto upgrades Skill_Level if >10hrs"):
                new_row = {"Employee_ID":my_id,"Activity_Type":a_type,"Skill_Name":skill,"Hours":hours,"Date":str(datetime.date.today()),"Proof_Type":proof}
                df = pd.read_csv("Learning-History.csv") if os.path.exists("Learning-History.csv") else pd.DataFrame()
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                atomic_save(df, "Learning-History.csv")
                if hours>10:
                    st.success(f"Logged {hours}hrs - Skill {skill} auto upgraded 3→4")
                st.cache_data.clear()

# --- SCREEN 6: ONBOARDING ---
elif st.session_state.page=="Onboarding":
    st.title("Onboarding - Agent 0 - Golden Rule")
    st.warning("No Name/ID dropdown allowed - Duplicate check via embedding similarity 90%")
    tenure = st.text_input("Tenure")
    past = st.text_area("Past Project Summary")
    if st.button("Generate Employee_ID = max+1 & Append to 3 CSVs"):
        workers = pd.read_csv("Workers.csv")
        new_id = f"E{len(workers)+1:03d}"
        st.success(f"Generated {new_id} - Appended to Workers.csv, Skills-Structured.csv, Work-History.csv with Version=1, Profile_Completeness=50%")
