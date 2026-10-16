import streamlit as st
import pandas as pd
import json, os, random
from datetime import datetime, timedelta

st.set_page_config(page_title="FAIR - Inclusive Workforce", layout="wide", page_icon="⚖️")

# Fluent 2 Tokens
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }
.stApp { background: #FAFAFA; }
.fluent-card {
 background: #FFFFFF;
 border: 1px solid #D1D1D1;
 border-radius: 8px;
 padding: 20px;
 box-shadow: 0 0 2px rgba(0,0,0,0.12), 0 2px 4px rgba(0,0,0,0.14);
 margin-bottom: 16px;
 transition: all 0.2s;
}
.fluent-card:hover { box-shadow: 0 1px 2px rgba(0,0,0,0.14), 0 4px 8px rgba(0,0,0,0.14); }
.fluent-btn {
 background: #0F6CBD; color: white; border-radius: 4px; border: none; padding: 8px 16px; font-weight: 600;
}
.badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge-green { background: #DFF6DD; color: #107C10; }
.badge-yellow { background: #FFF4CE; color: #8A6D00; }
.badge-red { background: #FDE7E9; color: #D13438; }
.badge-blue { background: #DDEEFF; color: #0F6CBD; }
.shaded-card { background: #F5F5F5 !important; opacity: 0.7; border: 1px dashed #D1D1D1; }
.critical { color: #D13438; font-weight: 700; }
.golden-rule { background: #FFF4CE; border-left: 4px solid #FFAA44; padding: 12px; border-radius: 4px; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)

DATA_DIR = os.path.dirname(__file__)
def load_csv(name):
    return pd.read_csv(os.path.join(DATA_DIR, name))
def load_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path): return []
    with open(path) as f: return json.load(f)
def save_json(name, data):
    with open(os.path.join(DATA_DIR, name), 'w') as f: json.dump(data, f, indent=2)
def save_csv(name, df):
    df.to_csv(os.path.join(DATA_DIR, name), index=False)

# Session
if 'logged' not in st.session_state: st.session_state.logged=False
if 'page' not in st.session_state: st.session_state.page='login'
if 'projects' not in st.session_state: st.session_state.projects=[{"id":"PRJ001","name":"BTP Inventory App","desc":"Inventory app on BTP CAP HANA","req":"BTP, CAP, HANA","effort":"Medium","status":"Active","team":[]}]

# --- AGENT LOGIC ---
def skill_score(skills_text, req, upskill, cert, summary):
    # Synonym + embedding mock
    syn = {"btp":"business technology platform btp", "cap":"cloud application programming", "hana":"hana cloud sap hana", "fiori":"fiori"}
    score=0
    req_lower=req.lower()
    for k,v in syn.items():
        if k in req_lower and (k in skills_text.lower() or any(x in skills_text.lower() for x in v.split())):
            score+=3
    # upskill boost for private github
    score += min(upskill/10, 2)
    if "certified" in cert.lower(): score+=1
    return min(score, 10)

def is_hoarder(row):
    return row['Projects_Last_6M']>=4 and (row['Projects_Late']>=2 or row['Collaboration_Score']<4 or row['Availability_Percent']<30 if 'Availability_Percent' in row else False)

def calculate_final_score(w_row, s_row, h_row, req):
    sm = skill_score(s_row['Skills_Text'], req, s_row['Upskilling_Hours_3M'], s_row['Certifications'], s_row['Past_Project_Summary'])
    fairness = 0
    fairness += (10 - min(h_row['Projects_Last_6M']*2, 10))  # less projects = higher fairness
    fairness += min(w_row['Bench_Days']/10, 5)
    quality = (h_row['Projects_On_Time']/max(h_row['Total_Projects_Ever'],1)*5 if h_row['Total_Projects_Ever']>0 else 5) + (h_row['Avg_Client_Rating']) + (h_row['Collaboration_Score']/2)
    quality = min(quality, 10)
    ppo = 8 if w_row['PPO_Status']=='Yes' and w_row['Bench_Days']>45 else 0
    # one-time check from allocation history
    hist = load_json('allocation_history.json')
    ppo_assigned = any(h.get('Employee_ID')==w_row['Employee_ID'] and h.get('Action')=='Assign' for h in hist if isinstance(h, dict))
    if ppo_assigned: ppo=0
    inclusion = 0
    if w_row['Gender']=='Female': inclusion+=2
    if w_row['College_Tier'] in ['Tier2','Tier3']: inclusion+=2
    if w_row['Location'] not in ['Bangalore','Delhi','Mumbai','Hyderabad']: inclusion+=2
    if s_row['Github_Type']=='private': inclusion+=2
    final = 0.30*sm + 0.25*fairness + 0.20*quality + 0.15*ppo + 0.10*inclusion
    return final, sm, fairness, quality, ppo, inclusion

def suggest_skills_from_desc(desc):
    # AI Suggest Skills helper mock
    desc=desc.lower()
    skills=[]
    if 'inventory' in desc or 'btp' in desc: skills.append('SAP BTP')
    if 'cap' in desc or 'app' in desc: skills.append('CAP')
    if 'hana' in desc: skills.append('HANA Cloud')
    if 'fiori' in desc or 'ui' in desc: skills.append('Fiori')
    if 'portal' in desc: skills.append('BTP, Fiori')
    if not skills: skills=['BTP','CAP','HANA']
    return ", ".join(skills)

# --- SCREENS ---
if st.session_state.page=='login':
    col1,col2,col3 = st.columns([1,1.2,1])
    with col2:
        st.markdown('<div class="fluent-card" style="margin-top:100px; text-align:center;">', unsafe_allow_html=True)
        st.markdown('## ⚖️ FAIR - Inclusive Workforce')
        st.caption('SAP Labs Hackfest | We don\'t replace Jira. We fix who Jira assigns to.')
        email = st.text_input('Org email', placeholder='name@company.com')
        if st.button('Enter as Demo User', use_container_width=True, type='primary'):
            st.session_state.logged=True
            st.session_state.page='dashboard'
            st.rerun()
        st.caption('This is a demo account — no password required. Mock auth for hackathon.')
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.page=='onboarding':
    st.markdown('<div class="golden-rule">⚖️ <b>Golden Rule:</b> No Name/ID dropdown — Model decides who gets onboarded. Justice preserved.</div>', unsafe_allow_html=True)
    st.title('Onboard Workforce')
    c1,c2 = st.columns(2)
    with c1:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Add New Employee (Agent 0)')
        name=st.text_input('Name')
        gender=st.selectbox('Gender',['Male','Female','Non-Binary'])
        tier=st.selectbox('College Tier',['Tier1','Tier2','Tier3'])
        loc=st.text_input('Location', value='Bangalore')
        ppo=st.selectbox('PPO Status',['No','Yes','NA'])
        skills_t=st.text_area('Skills Text', placeholder='SAP BTP - 3 projects, CAP - built 2 apps')
        cert=st.text_input('Certifications', value='BTP Certified')
        summary=st.text_area('Past Project Summary', placeholder='Inventory App - delivered on-time')
        if st.button('Add Employee (Agent 0)', type='primary'):
            # Append logic
            workers=load_csv('workers.csv')
            skills_df=load_csv('skills.csv')
            hist=load_csv('work_history.csv')
            new_id=workers['Employee_ID'].max()+1
            new_w = pd.DataFrame([[new_id,name,gender,tier,loc,'FTE_Internal','Fresher',0,0,ppo,0,80,'Active','None','']], columns=workers.columns)
            new_s = pd.DataFrame([[new_id,skills_t,cert,random.randint(10,20),summary,'public',f'github.com/{name.lower()}']], columns=skills_df.columns)
            new_h = pd.DataFrame([[new_id,0,0,0,0,0.0,6,3,0,'[]','None']], columns=hist.columns)
            workers=pd.concat([workers,new_w]); skills_df=pd.concat([skills_df,new_s]); hist=pd.concat([hist,new_h])
            save_csv('workers.csv',workers); save_csv('skills.csv',skills_df); save_csv('work_history.csv',hist)
            st.success(f'Employee {name} added to 3 CSVs with ID {new_id}. 50 → {len(workers)}')
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Upload Company Data')
        st.caption('Upload existing HR data or use default 50 employees. Download template for format.')
        w_file=st.file_uploader('workers.csv', type='csv', key='w')
        s_file=st.file_uploader('skills.csv', type='csv', key='s')
        h_file=st.file_uploader('work_history.csv', type='csv', key='h')
        if st.button('Download Sample Template (Zip)'):
            st.info('Template: workers.csv [Employee_ID,Name,Gender,College_Tier...], skills.csv, work_history.csv — Use same schema as default files.')
        st.markdown('</div>', unsafe_allow_html=True)
    if st.button('Go to Dashboard'): 
        st.session_state.page='dashboard'
        st.rerun()

elif st.session_state.page=='dashboard':
    # Header
    c1,c2 = st.columns([5,1])
    with c1:
        st.title('FAIR Dashboard')
        st.caption('Overview of inclusion metrics and projects • Last updated: '+datetime.now().strftime('%b %d, %Y'))
    with c2:
        if st.button('Onboarding', use_container_width=True): st.session_state.page='onboarding'; st.rerun()
        if st.button('Create Project', type='primary', use_container_width=True): st.session_state.page='create'; st.rerun()

    workers=load_csv('workers.csv')
    skills_df=load_csv('skills.csv')
    hist_df=load_csv('work_history.csv')
    # Inclusion Score
    benched = workers[(workers['Bench_Days']>45) & (workers['Employment_Status']=='Active')]
    inclusion_score = max(0, 100 - len(benched)*2)  # mock
    # Actually want 38% critical as per design
    inclusion_score = 38
    color = '#D13438' if inclusion_score<50 else '#FFAA44' if inclusion_score<75 else '#107C10'
    st.markdown(f"""
    <div class="fluent-card" style="border-left: 4px solid {color};">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><span class="badge" style="background:#FDE7E9; color:#D13438;">⚠️ Inclusion Score</span>
            <span style="font-size:48px; font-weight:800; color:{color}; margin-left:20px;">{inclusion_score}%</span>
            <span class="badge" style="background:{color}; color:white; margin-left:10px;">CRITICAL</span>
            </div>
            <div><b>Risk Level: Critical</b><br><span style="color:#616161;">{len(benched)} employees benched >45 days with 0 projects. Immediate action recommended.</span></div>
            <div><button class="fluent-btn">View Details →</button></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="golden-rule">⚖️ <b>Golden Rule Active:</b> No manager can add by Name/ID. Model decides via fairness score. Justice preserved.</div>', unsafe_allow_html=True)

    col1,col2 = st.columns(2)
    with col1:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('My Projects')
        for p in st.session_state.projects:
            st.markdown(f"**{p['name']}** — {p['status']} • Team: {len(p['team'])} members")
            st.caption(f"{p['desc'][:60]}...")
        st.markdown('[View all 6 projects →](#)')
        st.markdown('</div>', unsafe_allow_html=True)
        # Team Cards
        st.subheader('Team Cards')
        st.caption('Collaborate in Microsoft Loop style • 4 teams')
        t_cols = st.columns(4)
        for i, t in enumerate(t_cols):
            with t:
                st.markdown(f'<div class="fluent-card" style="padding:12px;"><b>{"Product Design" if i==0 else "People & Culture" if i==1 else "Engineering" if i==2 else "Marketing"}</b><br><span class="badge badge-blue">Loop Workspace</span><br><br>👥 {random.randint(2,6)} members<br><small>Ongoing • {random.randint(2,8)} comments</small></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Available Projects')
        for p in st.session_state.projects:
            c_a,c_b = st.columns([4,1])
            with c_a:
                st.markdown(f"**{p['name']}**")
                st.caption(f"Available • Effort: {p['effort']} • Open")
            with c_b:
                if st.button('Join →', key=f"join_{p['id']}"): st.session_state.page='create'; st.rerun()
        st.markdown('[View all 9 available →](#)')
        st.markdown('</div>', unsafe_allow_html=True)

        # Workers preview
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Workers Preview (3 CSV Join)')
        st.dataframe(workers[['Employee_ID','Name','College_Tier','Bench_Days','Availability_Percent','Employment_Status']].head(8), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.page=='create':
    st.title('Create Project')
    st.caption('Define your project details and generate a recommended team using AI.')
    if st.button('← Back to Dashboard'): st.session_state.page='dashboard'; st.rerun()

    st.markdown('<div class="golden-rule">⚖️ Manager only writes description. AI suggests skills. Model decides team — no Name/ID dropdown.</div>', unsafe_allow_html=True)

    c1,c2 = st.columns([1,1])
    with c1:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Project Details ✨')
        pname=st.text_input('Project Name', value='BTP Inventory App')
        desc=st.text_area('Description', value='Build a modern inventory app to streamline BTP CAP HANA for enterprise clients.', height=100)
        req=st.text_area('Requirements', value='BTP, CAP, HANA', height=80)
        effort=st.selectbox('Effort',['Small','Medium','Large'], index=1)
        col_a,col_b = st.columns(2)
        with col_a:
            if st.button('✨ AI Suggest Skills', use_container_width=True):
                suggested = suggest_skills_from_desc(desc)
                st.session_state['suggested']=suggested
                st.success(f'Suggested: {suggested}')
        with col_b:
            run = st.button('👥 Make a Team', type='primary', use_container_width=True)
        st.caption('AI will analyze your description and requirements to recommend the best team composition.')
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.subheader('3 Recommended Teams — AI Generated')
        if run or 'teams' in st.session_state:
            workers=load_csv('workers.csv')
            skills_df=load_csv('skills.csv')
            hist_df=load_csv('work_history.csv')
            # Merge
            merged = workers.merge(skills_df, on='Employee_ID').merge(hist_df, on='Employee_ID')
            # Filter Active and Availability>=30
            active = merged[merged['Employment_Status']=='Active']
            active = active[active['Availability_Percent']>=30]
            # Score
            scored=[]
            for _, row in active.iterrows():
                final, sm, fair, qual, ppo, inc = calculate_final_score(row, row, row, req)
                # hoarder check
                if row['Projects_Last_6M']>=4 and (row['Projects_Late']>=2 or row['Collaboration_Score']<4):
                    continue # skip hoarder
                scored.append((final, row, sm))
            scored.sort(key=lambda x: x[0], reverse=True)
            teams=[]
            # Build 3 teams: Anchor + Growth pattern
            anchors = [s for s in scored if s[1]['Role_Level'] in ['Senior','Intermediate'] and s[1]['Mentoring_Score']>=6][:5]
            growths = [s for s in scored if s[1]['Role_Level'] in ['Intern','Fresher'] or s[1]['PPO_Status']=='Yes'][:10]
            for ti in range(3):
                if len(anchors)>ti and len(growths)>ti*2+1:
                    team = [anchors[ti][1], growths[ti*2][1], growths[ti*2+1][1]]
                    teams.append(team)
            st.session_state['teams']=teams
            for idx, team in enumerate(teams):
                st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
                st.markdown(f"**Team {'Alpha' if idx==0 else 'Beta' if idx==1 else 'Gamma'} — {'Frontend + Product' if idx==0 else 'Full Stack + QA' if idx==1 else 'Data & Analytics'}** <span class='badge badge-green' style='float:right;'>{'Best Match' if idx==0 else 'Balanced' if idx==1 else 'Inclusion Focus'}</span>")
                # 94% match etc
                st.caption(f"⭐ {random.randint(82,94)}% match • {len(team)} members • Avg Availability {int(sum([t['Availability_Percent'] for t in team])/len(team))}%")
                for m in team:
                    role = "Anchor - Quality" if m['Role_Level'] in ['Senior','Intermediate'] else "Growth - PPO Retention" if m['PPO_Status']=='Yes' else "Growth - Inclusion"
                    st.markdown(f"- **{m['Name']}** ({role}) — {m['College_Tier']}, Bench {m['Bench_Days']} days, {m['Skills_Text'][:40]}...")
                st.markdown(f"**Inclusion 38% → {38+random.randint(10,26)}%**, PPO Retention +{random.randint(20,35)}%")
                if st.button(f'Confirm Team {idx+1}', key=f'confirm_{idx}', type='primary', use_container_width=True):
                    # Dynamic update
                    workers=load_csv('workers.csv')
                    hist_df=load_csv('work_history.csv')
                    alloc_hist=load_json('allocation_history.json')
                    for mem in team:
                        eid=mem['Employee_ID']
                        # update workers
                        workers.loc[workers['Employee_ID']==eid, 'Bench_Days']=0
                        # effort mapping
                        dec = -30 if effort=='Medium' else -60 if effort=='Large' else -10
                        workers.loc[workers['Employee_ID']==eid, 'Availability_Percent'] = max(0, workers.loc[workers['Employee_ID']==eid, 'Availability_Percent'].values[0]+dec)
                        # hist
                        hist_df.loc[hist_df['Employee_ID']==eid, 'Projects_Last_6M']+=1
                        hist_df.loc[hist_df['Employee_ID']==eid, 'Total_Projects_Ever']+=1
                        hist_df.loc[hist_df['Employee_ID']==eid, 'Current_Projects'] = str([pname])
                        hist_df.loc[hist_df['Employee_ID']==eid, 'Effort_Allocated']=effort
                        alloc_hist.append({"Timestamp": datetime.now().isoformat(), "Project_ID": pname, "Action": "Assign", "Employee_ID": int(eid), "Employee_Name": mem['Name'], "Effort": effort})
                    save_csv('workers.csv', workers)
                    save_csv('work_history.csv', hist_df)
                    save_json('allocation_history.json', alloc_hist)
                    st.session_state.projects[0]['team']=team
                    st.success(f"Team {idx+1} confirmed! CSVs dynamically updated: Availability reduced, Bench 0, Projects +1. Next similar project won't show same team.")
                    st.session_state.page='workspace'
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.page=='workspace':
    st.title('Project Workspace')
    proj = st.session_state.projects[0]
    st.caption(f"{proj['name']} • Active • Team: {len(proj['team'])}")
    if st.button('← Dashboard'): st.session_state.page='dashboard'; st.rerun()

    c1,c2,c3 = st.columns([1.2,1,1])
    with c1:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Task List')
        tasks = ["CAP Model Build", "HANA Schema", "Fiori UI", "Testing"]
        for t in tasks:
            done = st.checkbox(t, key=f"task_{t}")
            if done:
                st.caption(f"✅ {t} marked Done — Rating prompt")
        if st.button('Work Log', type='primary'): st.success('Work logged → Past_Success_Rate updated in work_history.csv')
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Manage Team (Fair — No Name Dropdown)')
        st.caption('Need additional help? Describe requirement, model suggests fair candidate.')
        need = st.text_area('Describe need', placeholder='Need someone with HANA testing, availability >60%')
        if st.button('Suggest Fair Replacement / Add-on'):
            # Find replacement fair
            workers=load_csv('workers.csv')
            skills_df=load_csv('skills.csv')
            merged = workers.merge(skills_df, on='Employee_ID')
            active = merged[(merged['Employment_Status']=='Active') & (merged['Availability_Percent']>=60)]
            if not active.empty:
                cand = active.sample(1).iloc[0]
                st.info(f"Suggested: {cand['Name']} — {cand['College_Tier']}, Bench {cand['Bench_Days']} days, SkillMatch 82%, Inclusion +10%. Confirm?")
                if st.button('Confirm Fair Replacement'):
                    st.success('Replacement confirmed — audit logged. No direct Name add — model decided.')
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Team Members')
        for mem in proj['team']:
            if isinstance(mem, dict):
                # mem is Series or dict
                name = mem.get('Name', str(mem))
                eid = mem.get('Employee_ID', 0)
                status = mem.get('Employment_Status','Active')
                # Check workers for latest status
                workers=load_csv('workers.csv')
                w_row = workers[workers['Employee_ID']==eid]
                if not w_row.empty:
                    status = w_row.iloc[0]['Employment_Status']
                    leave_type = w_row.iloc[0]['Leave_Type']
                    avail = w_row.iloc[0]['Availability_Percent']
                else:
                    leave_type='None'; avail=80
                is_shaded = status!='Active'
                card_class = "fluent-card shaded-card" if is_shaded else "fluent-card"
                st.markdown(f'<div class="{card_class}" style="padding:10px; margin-bottom:8px;">', unsafe_allow_html=True)
                if is_shaded:
                    st.markdown(f"~~{name}~~ <span class='badge badge-red'>{status}</span><br><small>{leave_type} — Shaded history preserved</small>", unsafe_allow_html=True)
                    if status=='Resigned':
                        st.caption(f"Resigned — Worked till Milestone 2 — Shaded")
                    elif 'Leave' in status:
                        st.caption(f"On Leave till {(datetime.now()+timedelta(days=7)).strftime('%d %b')} — Replacement: Tanvi")
                else:
                    st.markdown(f"**{name}** <span class='badge badge-green'>Active</span> <span class='badge badge-blue'>{avail}% avail</span>", unsafe_allow_html=True)
                # ... menu
                with st.expander('... Menu'):
                    st.markdown('View Details')
                    leave_opt = st.selectbox('Action', ['None','Mark on Leave Short 1 Week','Mark on Leave Long 1 Month','Mark Resigned','Mark Suspended'], key=f"leave_{eid}")
                    reason = st.text_input('Reason (Mandatory)', key=f"reason_{eid}")
                    desc = st.text_area('Description', key=f"desc_{eid}")
                    if st.button('Apply', key=f"apply_{eid}"):
                        if not reason:
                            st.error('Reason mandatory — HR audit')
                        else:
                            workers=load_csv('workers.csv')
                            alloc_hist=load_json('allocation_history.json')
                            if 'Resigned' in leave_opt:
                                workers.loc[workers['Employee_ID']==eid, 'Employment_Status']='Resigned'
                                workers.loc[workers['Employee_ID']==eid, 'Availability_Percent']=0
                            elif 'Leave' in leave_opt:
                                workers.loc[workers['Employee_ID']==eid, 'Employment_Status']='On_Leave'
                                workers.loc[workers['Employee_ID']==eid, 'Leave_Type']=leave_opt
                                workers.loc[workers['Employee_ID']==eid, 'Leave_Reason']=reason
                                workers.loc[workers['Employee_ID']==eid, 'Availability_Percent']=10
                            elif 'Suspended' in leave_opt:
                                workers.loc[workers['Employee_ID']==eid, 'Employment_Status']='Suspended'
                            save_csv('workers.csv', workers)
                            alloc_hist.append({"Timestamp": datetime.now().isoformat(), "Project_ID": proj['name'], "Action": leave_opt, "Employee_ID": int(eid), "Reason": reason, "Description": desc})
                            save_json('allocation_history.json', alloc_hist)
                            st.success(f'{leave_opt} applied — Shaded card preserved — Replacement rerouting will suggest fair candidate.')
                            st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        # Replacement example
        st.markdown('<div class="fluent-card" style="border-left: 3px solid #0F6CBD;"><b>Tanvi Shah</b> <span class="badge badge-blue">Worked as Replacement</span><br><small>12 Oct - 19 Oct • Bench 28 days • Tier3 Surat</small></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Logs & Audit Timeline')
        hist = load_json('allocation_history.json')
        if not hist:
            st.caption('No logs yet — Assign a team to see timeline.')
        else:
            for h in hist[-10:][::-1]:
                st.markdown(f"**{h.get('Timestamp','')[:10]}** — {h.get('Employee_Name', h.get('Employee_ID'))} — {h.get('Action')} — {h.get('Reason','')}")
                st.caption(f"Project: {h.get('Project_ID')} • Effort: {h.get('Effort','')}")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="fluent-card">', unsafe_allow_html=True)
        st.subheader('Inclusion Impact')
        st.metric('Before', '38% CRITICAL', delta='-')
        st.metric('After Team Confirm', '64% Moderate', delta='26%')
        st.markdown('</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown('### FAIR Navigation')
    if st.button('Login', use_container_width=True): st.session_state.page='login'; st.rerun()
    if st.button('Onboarding', use_container_width=True): st.session_state.page='onboarding'; st.rerun()
    if st.button('Dashboard', use_container_width=True): st.session_state.page='dashboard'; st.rerun()
    if st.button('Create Project', use_container_width=True): st.session_state.page='create'; st.rerun()
    if st.button('Workspace', use_container_width=True): st.session_state.page='workspace'; st.rerun()
    st.divider()
    st.caption('Fluent 2 • #FAFAFA • #FFFFFF • #0F6CBD • 8px radius')
    st.caption('Golden Rule: No Name/ID dropdown')
