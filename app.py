import streamlit as st
import pandas as pd
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
import json

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Program Feedback Dashboard", page_icon="📊", layout="wide")
st.title("📊 Program Feedback Dashboard")

# --- 2. CONNECT TO GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet="PF Raw Data")
    df = df.dropna(how="all") # Clean up empty rows
except Exception as e:
    st.error("Could not connect to Google Sheets. Check your Secrets.")
    st.stop()

if len(df) < 2:
    st.warning("No data found in PF Raw Data.")
    st.stop()

# --- 3. CALCULATE METRICS ---
headers = [str(h).lower().strip() for h in df.columns]

# Helper function to find columns dynamically
def find_col(keywords):
    for i, h in enumerate(headers):
        if any(k in h for k in keywords):
            return df.columns[i]
    return None

sis_col = find_col(["sis_id", "sis id"])
nps_col = find_col(["nps", "recommendation"])

unique_learners = df[sis_col].nunique() if sis_col else len(df)

if nps_col:
    nps_data = pd.to_numeric(df[nps_col], errors='coerce').dropna()
    promoters = len(nps_data[nps_data >= 9])
    neutral = len(nps_data[(nps_data >= 7) & (nps_data < 9)])
    detractors = len(nps_data[nps_data <= 6])
    valid_nps_count = len(nps_data)
    
    nps_score = round(((promoters - detractors) / valid_nps_count) * 100, 2) if valid_nps_count > 0 else 0.0
else:
    promoters, detractors, nps_score = 0, 0, 0.0

# Build Metric Cards
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Unique Learners", unique_learners)
col2.metric("Overall NPS Score", nps_score)
col3.metric("Promoters (9-10)", promoters)
col4.metric("Detractors (0-6)", detractors)

st.divider()

# --- 4. AI ANALYSIS & DRILL-DOWNS ---
st.subheader("Key Insights & Action Items")

if st.button("Generate AI Insights"):
    with st.spinner("Aggregating and clubbing themes with Gemini..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Convert Data to String for the AI
        data_string = df.to_csv(index=False)
        
        prompt = f"""
        You are an expert Data Analyst evaluating educational program feedback. 
        TASK: Analyze the dataset and output a strict JSON format response.

        1. INSIGHTS: Provide 3 to 4 extremely brief, objective bullet points summarizing major trends and critical red flags. Use emojis.
        2. AGGRESSIVE THEME CLUBBING (CRITICAL): You MUST group and merge similar feedback into overarching parent themes. DO NOT list individual, slightly varying complaints separately. 
           - Example: Combine "audio issues", "video lagging", and "platform slow" into ONE theme called "Technical & Platform Issues". 
           - LIMIT your entire output to a MAXIMUM of 4 to 6 broad themes.
        3. TEAM BUCKETING: Categorize actionables strictly into one of these buckets:
           - "Program Office", "Acad ops", "Guru Ops", "Career Team", "Tech Team", or "Product team".
        4. SIS IDs: Extract the EXACT "sis_id" for EVERY learner associated with the clubbed theme. Combine all their IDs into the "Associated_SIS_IDs" array.

        You MUST return valid JSON matching EXACTLY this structure:
        {{
          "Overall_Insights": "• 🚀 [Brief objective insight 1]\\n• ⚠️ [Brief objective insight 2]\\n• 📉 [Brief objective insight 3]",
          "Actionables": [
            {{
              "Team": "Team Name",
              "Issue_Summary": "Brief objective description of the clubbed feedback",
              "Associated_SIS_IDs": ["id1", "id2", "id3"],
              "Potential_Actionables": "Clear, direct actionable step"
            }}
          ]
        }}

        Dataset:
        {data_string}
        """
        
        try:
            response = model.generate_content(prompt, generation_config={"temperature": 0.1})
            ai_text = response.text.replace('```json', '').replace('```', '').strip()
            ai_data = json.loads(ai_text)
            
            st.markdown(ai_data.get("Overall_Insights", "No insights generated."))
            st.write("")
            
            st.subheader("Action Items by Team (Drill-downs)")
            actionables = ai_data.get("Actionables", [])
            
            # This replaces your hidden sheets with sleek dropdown menus
            for item in actionables:
                learner_count = len(item.get('Associated_SIS_IDs', []))
                with st.expander(f"📁 {item['Team']} — {item['Issue_Summary']} ({learner_count} Learners)"):
                    st.write(f"**Action Plan:** {item['Potential_Actionables']}")
                    
                    affected_ids = item.get('Associated_SIS_IDs', [])
                    if affected_ids and sis_col:
                        # Filter the raw data just for these IDs
                        affected_df = df[df[sis_col].astype(str).isin([str(i) for i in affected_ids])]
                        st.dataframe(affected_df)
                    else:
                        st.write("No specific learner IDs found for this issue.")
                        
        except Exception as e:
            st.error(f"Error communicating with Gemini: {e}")
