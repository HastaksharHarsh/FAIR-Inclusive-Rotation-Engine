# FAIR - Fair Allocation & Inclusive Rotation Engine
### SAP Labs Hackfest Bangalore 2026 | Theme 2 - Inclusive Workforce

**Tagline:** We don't filter resumes. We fix who gets the next chance.

#### Problem
After hiring, opportunity distribution is biased. 10% (Tier1, Senior, Male, Bangalore) hoard 80% projects. 90% (Tier3, Interns, PPO, Female, Non-Metro) with same SAP BTP skills get 0 projects.

#### Solution - 4 AI Agents
- **Agent 1 Skill Miner:** Real GitHub API check, handles public/private inclusive
- **Agent 2 Hoarding Detector:** Calculates Inclusion Score 38% CRITICAL
- **Agent 3 Opportunity Matcher (Main):** Forms balanced team Anchor + Growth, PPO Priority, Fairness >3 skip, Inclusion Tier3/Female/Private GitHub
- **Agent 4 Inclusion Auditor:** Business impact, dynamic learning loop

#### Dataset
`workforce.csv` - 50 rows inclusive: 10 Seniors, 15 Intermediate, 8 Interns (3-8 mo), 6 Intern_PPO (6 mo, PPO Yes), 11 Fresher FTE. Columns: Gender, College Tier, Location, Github_Type public/private, Experience, Mentoring Score, PPO Status.

#### Dynamic Learning
When assignment confirmed, `assign_and_learn()` updates workforce.csv (Projects 0->1) and appends to allocation_history.json. Next recommendation differs. Proves AI learns.

#### Tech Stack
Streamlit, CrewAI, Gemini Flash, SAP BTP, HANA Cloud mock (CSV), Pyvis

#### Architecture
[Insert your 4 workflow images in assets/ folder]

#### How to Run
pip install -r requirements.txt
streamlit run app.py