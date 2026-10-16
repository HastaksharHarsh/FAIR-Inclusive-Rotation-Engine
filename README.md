## FAIR - Fair Allocation & Inclusive Rotation Engine V3.2
Tagline: We don't replace Jira. We fix who Jira assigns to.
SAP Labs Hackfest Bangalore 2026 | Theme 2: Inclusive Workforce

## Golden Rule
⚖️ No manager or employee can directly add/remove/swap by Name/ID. Model decides. Justice preserved.

## What's New in V3.2 vs V2
V2: Single workforce.csv 50 rows, 2 tabs Worker/Management
V3.2: 3 CSVs (workers, skills, work_history) proxy for SuccessFactors + TechWolf + Jira, 5 Agents, 5 Screens Fluent 2, dynamic CSV update, shaded leave/resign history, fair replacement rerouting, no name dropdown
Architecture
Data: workers.csv (HR), skills.csv (Learning), work_history.csv (Delivery), allocation_history.json (audit), project_tasks.json
Agents: Agent 0 Onboarding (append 3 CSVs), Agent 1 Skill Miner (synonym + embedding, private GitHub fallback via upskilling), Agent 2 Hoarding Detector (Hoarder vs High Performer), Agent 3 Matcher (FinalScore 0.30Skill+0.25Fairness+0.20Quality+0.15PPO+0.10*Inclusion + 6 Rules), Agent 4 Auditor (dynamic update + leave/resign + replacement rerouting + shaded UI + logs)
Screens: Login (mock), Onboarding (3 CSV upload + sample template), Dashboard (Inclusion 38% CRITICAL, My Projects, Available Projects, Team Cards Loop style), Create Project (Description -> AI Suggest Skills -> Make Team -> 3 Teams -> Confirm triggers dynamic update), Workspace (Task checklist + Work Log + Team with shaded Resigned/On Leave + Replacement badge + Manage Team via description + View Details timeline + Audit)
Key Fixes
Loose 1 Skill exact match → synonym dict + embedding
Loose 2 Leave abuse → Reason mandatory + model-only replacement + shaded history + audit log
Loose 3 Availability static → Effort -10/-30/-60% + auto +20% after 7 days
Loose 4 PPO bias → One-time boost + Bench>45
Loose 5 ID mismatch → Document mock, prod uses MDM
New: Resignation/Leave → Shaded #F5F5F5, history preserved, replacement downshift, employee self-service dropdown, HR audit
Design
Fluent 2 Tokens: Background #FAFAFA, Card #FFFFFF, Border #D1D1D1, Primary #0F6CBD, Radius 8px card / 4px controls, Shadow 0 0 2px rgba(0,0,0,0.12), 0 2px 4px rgba(0,0,0,0.14), Font Segoe UI

## Run
python -m pip install streamlit pandas --only-binary=:all:
python -m streamlit run app.py


## Demo Story
Login mock → Dashboard 38% CRITICAL, Priya PPO bench 55 days
Create Project BTP Inventory App → AI Suggest Skills → Make Team → Rejects Arjun hoarder low quality, picks Rahul Anchor + Priya Growth
Confirm → CSVs dynamic update, availability low, bench 0, Projects +1, next similar project Priya not candidate
Workspace → Mark Priya on Leave (Reason Sick, 1 Week) → Replacement rerouting suggests Tanvi → Confirm → Priya shaded On Leave, Tanvi badge Worked as Replacement
View Details timeline shows all logs
GitHub Push
Copy this folder to HastaksharHarsh/FAIR-Inclusive-Rotation-Engine, commit "V3.2 - 3 CSVs + Golden Rule + Dynamic + Leave Rerouting + Fluent 2"

