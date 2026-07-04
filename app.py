import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from fpdf import FPDF
import base64
import urllib.parse
import os
import json

load_dotenv()

from agents.planner import plan_research
from agents.summarizer import summarize
from agents.writer import write_report
from tools.search_tool import search_web

st.set_page_config(page_title="Multi-Agent Research Assistant", page_icon="🔬", layout="wide")

# ── SESSION STATE INIT ────────────────────────────────────────────────────────
defaults = {
    "history": [], "dark_mode": False, "current_report": "", "current_topic": "",
    "chat_messages": [], "report_ready": False, "page": "Research Assistant",
    "vision_messages": [], "uploaded_image": None, "uploaded_file_text": None,
    "quiz_data": None, "quiz_answers": {}, "quiz_submitted": False, "quiz_generated": False,
    "saved_reports": [], "topic_counts": {}, "user_level": "Beginner",
    "confidence_score": 0, "source_labels": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── GROQ KEY ──────────────────────────────────────────────────────────────────
def get_groq_key():
    try:
        return st.secrets["GROQ_API_KEY"]
    except:
        return os.getenv("GROQ_API_KEY")

# ── THEME ─────────────────────────────────────────────────────────────────────
def apply_theme(dark_mode):
    if dark_mode:
        st.markdown("""<style>
.stApp{background-color:#0e1117;color:#fafafa;}
.stTextInput>div>div>input{background-color:#1e2130;color:#fafafa;border:1px solid #444;}
.stExpander{background-color:#1e2130;border:1px solid #333;}
.stButton>button{background-color:#262940;color:#fff;border:1px solid #555;}
h1,h2,h3,h4{color:#e0e0ff!important;}
.card{background:#1e2130;border:1px solid #444;border-radius:12px;padding:16px;margin:8px 0;}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:bold;}
</style>""", unsafe_allow_html=True)
    else:
        st.markdown("""<style>
.stApp{background-color:#f8f9ff;}
.card{background:#ffffff;border:1px solid #e0e0e0;border-radius:12px;padding:16px;margin:8px 0;}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:bold;}
</style>""", unsafe_allow_html=True)

apply_theme(st.session_state.dark_mode)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/bot.png", width=80)
    st.title("Research Assistant")
    st.markdown("### Navigation")
    page = st.radio("", ["Research Assistant", "Dashboard", "Vision AI Chat"], label_visibility="collapsed")
    st.session_state.page = page
    st.divider()
    st.markdown("**Settings:**")
    dark_toggle = st.toggle("Dark Mode", value=st.session_state.dark_mode)
    if dark_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_toggle
        st.rerun()
    st.divider()
    if st.session_state.page == "Research Assistant":
        st.header("Research History")
        history_search = st.text_input("Filter:", placeholder="Search topics...")
        if st.session_state.history:
            filtered = [i for i in st.session_state.history
                        if history_search.lower() in i['topic'].lower()] if history_search else st.session_state.history
            for item in reversed(filtered):
                with st.expander(f"{item['topic'][:22]}..."):
                    st.write(f"🕐 {item['time']}")
                    st.write(f"📝 {item['words']} words")
                    st.write(f"🎓 Level: {item.get('level','Beginner')}")
                    st.write(f"⭐ Confidence: {item.get('confidence',0)}%")
        else:
            st.info("No history yet!")

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_level_prompt(level):
    prompts = {
        "Beginner":  "Use very simple language. Avoid jargon. Explain terms. Short sentences. Easy to understand for a 10th grade student.",
        "Intermediate": "Use moderate technical language. Brief explanations for key terms. Balanced depth.",
        "Advanced":  "Use technical/academic language. Assume domain knowledge. Include in-depth analysis and expert insights.",
        "Expert":    "Use highly specialized language. Maximum depth. Include cutting-edge details, statistics, and expert-level analysis."
    }
    return prompts.get(level, prompts["Beginner"])

def calculate_confidence(sources, summaries):
    score = 0
    # Count sources
    if len(sources) >= 5: score += 40
    elif len(sources) >= 3: score += 25
    elif len(sources) >= 1: score += 10
    # Content depth
    total_words = sum(len(s.split()) for s in summaries)
    if total_words > 500: score += 30
    elif total_words > 200: score += 20
    elif total_words > 50: score += 10
    # Unique domains
    unique_domains = len(set(
        s.get("url","").replace("https://","").replace("http://","").split("/")[0]
        for s in sources if s.get("url")
    ))
    if unique_domains >= 3: score += 30
    elif unique_domains >= 2: score += 20
    elif unique_domains >= 1: score += 10
    return min(score, 100)

def label_sources(sources):
    labeled = []
    for src in sources:
        url = src.get("url","").lower()
        if any(x in url for x in [".edu", ".ac."]):
            tag, color = "Academic", "#4CAF50"
        elif any(x in url for x in ["wikipedia", "britannica"]):
            tag, color = "Encyclopedia", "#2196F3"
        elif any(x in url for x in ["gov", ".org"]):
            tag, color = "Official", "#FF9800"
        elif any(x in url for x in ["arxiv", "researchgate", "scholar"]):
            tag, color = "Research", "#9C27B0"
        else:
            tag, color = "Web", "#607D8B"
        labeled.append({**src, "tag": tag, "color": color})
    return labeled

def generate_multi_format_output(topic, report, level):
    groq_key = get_groq_key()
    if not groq_key:
        return None
    from groq import Groq
    client = Groq(api_key=groq_key)
    level_instruction = get_level_prompt(level)
    prompt = f"""Based on this research report about "{topic}", generate a multi-format output.
{level_instruction}

REPORT:
{report[:2500]}

Return ONLY valid JSON:
{{
  "simple_explanation": "2-3 sentence plain English summary anyone can understand",
  "detailed_explanation": "4-6 sentence detailed explanation with key facts",
  "key_terms": ["term1", "term2", "term3", "term4", "term5"],
  "important_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],
  "fun_fact": "One surprising or interesting fact from the report",
  "one_line_summary": "Single sentence summary of the entire topic"
}}"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800, temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    return json.loads(raw.strip())

def generate_quiz(topic, report, level):
    groq_key = get_groq_key()
    if not groq_key: return None
    from groq import Groq
    client = Groq(api_key=groq_key)
    level_instruction = get_level_prompt(level)
    prompt = f"""Generate 5 MCQ questions about "{topic}" from this report.
{level_instruction}

REPORT: {report[:2500]}

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "question": "Question text?",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "A",
      "explanation": "Why this is correct."
    }}
  ]
}}"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500, temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    return json.loads(raw.strip())

def generate_notes_pdf(topic, report, quiz_data=None, template="Standard Report", language="English", level="Beginner"):
    from fpdf.enums import XPos, YPos
    NX, NY = XPos.LMARGIN, YPos.NEXT
    def clean(text):
        reps = {"\u2022":"*","\u2023":"*","\u25cf":"*","\u2018":"'","\u2019":"'",
                "\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"--","\u2026":"...",
                "\u2192":"->","\u2713":"[OK]","\u2714":"[OK]","\u20ac":"EUR","\u00a3":"GBP"}
        for c,r in reps.items(): text = text.replace(c,r)
        return text.encode("ascii","replace").decode("ascii")
    pdf = FPDF(format="A4"); pdf.set_margins(20,20,20); pdf.set_auto_page_break(auto=True,margin=25); pdf.add_page()
    pdf.set_fill_color(63,81,181); pdf.set_text_color(255,255,255); pdf.set_font("helvetica",style="B",size=16)
    pdf.cell(0,10,clean(f"STUDY NOTES: {topic}")[:80],new_x=NX,new_y=NY,fill=True,align="C"); pdf.ln(2)
    pdf.set_font("helvetica",size=9); pdf.set_text_color(120,120,120)
    pdf.cell(0,6,clean(f"Level: {level} | Template: {template} | Language: {language} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"),new_x=NX,new_y=NY)
    pdf.ln(3); pdf.set_draw_color(180,190,220); pdf.line(20,pdf.get_y(),190,pdf.get_y()); pdf.ln(4)
    pdf.set_text_color(30,30,30)
    for line in [l for l in clean(report).split("\n") if not l.strip().startswith("<!--")]:
        line=line.strip()
        if pdf.get_y()>255: pdf.add_page(); pdf.ln(5)
        if not line: pdf.ln(2)
        elif line.startswith("# "): pdf.set_font("helvetica",style="B",size=13); pdf.set_text_color(40,55,160); pdf.multi_cell(0,8,line[2:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("## "): pdf.set_font("helvetica",style="B",size=11); pdf.set_text_color(63,81,181); pdf.multi_cell(0,7,line[3:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("### "): pdf.set_font("helvetica",style="B",size=10); pdf.set_text_color(80,80,180); pdf.multi_cell(0,7,line[4:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith(("- ","* ","+ ")): pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6," * "+line[2:].strip(),new_x=NX,new_y=NY)
        elif line.startswith("**") and line.endswith("**") and len(line)>4: pdf.set_font("helvetica",style="B",size=10); pdf.multi_cell(0,6,line[2:-2].strip(),new_x=NX,new_y=NY)
        else: pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6,line,new_x=NX,new_y=NY)
    if quiz_data and quiz_data.get("questions"):
        pdf.add_page()
        pdf.set_fill_color(76,175,80); pdf.set_text_color(255,255,255); pdf.set_font("helvetica",style="B",size=14)
        pdf.cell(0,10,"QUIZ - Test Your Knowledge",new_x=NX,new_y=NY,fill=True,align="C"); pdf.ln(4)
        pdf.set_text_color(30,30,30)
        for i,q in enumerate(quiz_data["questions"],1):
            if pdf.get_y()>230: pdf.add_page(); pdf.ln(5)
            pdf.set_font("helvetica",style="B",size=11); pdf.set_text_color(40,55,160)
            pdf.multi_cell(0,7,clean(f"Q{i}. {q['question']}"),new_x=NX,new_y=NY)
            pdf.set_text_color(30,30,30); pdf.set_font("helvetica",size=10)
            for opt,text in q["options"].items(): pdf.multi_cell(0,6,clean(f"   {opt}. {text}"),new_x=NX,new_y=NY)
            pdf.set_font("helvetica",style="B",size=10); pdf.set_text_color(0,128,0)
            pdf.multi_cell(0,6,clean(f"   Answer: {q['answer']}. {q['options'].get(q['answer'],'')}"),new_x=NX,new_y=NY)
            pdf.set_font("helvetica",style="I",size=9); pdf.set_text_color(100,100,100)
            pdf.multi_cell(0,6,clean(f"   Explanation: {q.get('explanation','')}"),new_x=NX,new_y=NY)
            pdf.set_text_color(30,30,30); pdf.ln(3)
    pdf.set_y(-18); pdf.set_font("helvetica",style="I",size=8); pdf.set_text_color(160,160,160)
    pdf.cell(0,8,f"Study Notes | {datetime.now().strftime('%Y-%m-%d')} | Multi-Agent Research Assistant",align="C")
    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out,str) else bytes(out)

def generate_pdf(topic, report, template="Standard Report", language="English"):
    from fpdf.enums import XPos, YPos
    NX, NY = XPos.LMARGIN, YPos.NEXT
    def clean(text):
        reps={"\u2022":"*","\u2023":"*","\u25cf":"*","\u2018":"'","\u2019":"'","\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"--","\u2026":"...","\u2192":"->","\u2713":"[OK]","\u2714":"[OK]","\u20ac":"EUR","\u00a3":"GBP"}
        for c,r in reps.items(): text=text.replace(c,r)
        return text.encode("ascii","replace").decode("ascii")
    pdf=FPDF(format="A4"); pdf.set_margins(20,20,20); pdf.set_auto_page_break(auto=True,margin=25); pdf.add_page()
    pdf.set_fill_color(63,81,181); pdf.set_text_color(255,255,255); pdf.set_font("helvetica",style="B",size=15)
    pdf.cell(0,9,clean(topic)[:80],new_x=NX,new_y=NY,fill=True,align="C"); pdf.ln(4)
    pdf.set_font("helvetica",size=9); pdf.set_text_color(120,120,120)
    pdf.cell(0,6,clean(f"Template: {template} | Language: {language} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"),new_x=NX,new_y=NY)
    pdf.ln(2); pdf.set_draw_color(180,190,220); pdf.line(20,pdf.get_y(),190,pdf.get_y()); pdf.ln(4)
    pdf.set_text_color(30,30,30)
    for line in [l for l in clean(report).split("\n") if not l.strip().startswith("<!--")]:
        line=line.strip()
        if pdf.get_y()>255: pdf.add_page(); pdf.ln(5)
        if not line: pdf.ln(2)
        elif line.startswith("# "): pdf.set_font("helvetica",style="B",size=13); pdf.set_text_color(40,55,160); pdf.multi_cell(0,8,line[2:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("## "): pdf.set_font("helvetica",style="B",size=11); pdf.set_text_color(63,81,181); pdf.multi_cell(0,7,line[3:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("### "): pdf.set_font("helvetica",style="B",size=10); pdf.set_text_color(80,80,180); pdf.multi_cell(0,7,line[4:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith(("- ","* ","+ ")): pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6," * "+line[2:].strip(),new_x=NX,new_y=NY)
        elif line.startswith("**") and line.endswith("**") and len(line)>4: pdf.set_font("helvetica",style="B",size=10); pdf.multi_cell(0,6,line[2:-2].strip(),new_x=NX,new_y=NY)
        else: pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6,line,new_x=NX,new_y=NY)
    pdf.set_y(-18); pdf.set_font("helvetica",style="I",size=8); pdf.set_text_color(160,160,160)
    pdf.cell(0,8,f"Research Report | {datetime.now().strftime('%Y-%m-%d')}",align="C")
    out=pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out,str) else bytes(out)

def show_agent_log(logs):
    with st.expander("🤖 Agent Activity Log", expanded=False):
        for log in logs: st.markdown(log)

def show_confidence_score(score, sources):
    st.divider()
    st.markdown("### 🎯 Report Confidence Score")
    col_score, col_info = st.columns([1, 3])
    with col_score:
        color = "#4CAF50" if score >= 70 else "#FF9800" if score >= 40 else "#F44336"
        label = "High" if score >= 70 else "Medium" if score >= 40 else "Low"
        st.markdown(f"""
        <div style="text-align:center;background:{color}22;border:2px solid {color};
        border-radius:12px;padding:20px;">
        <div style="font-size:42px;font-weight:bold;color:{color};">{score}%</div>
        <div style="font-size:16px;color:{color};font-weight:bold;">{label} Confidence</div>
        </div>""", unsafe_allow_html=True)
    with col_info:
        st.markdown("**What this means:**")
        if score >= 70:
            st.success("✅ Report is well-supported by multiple reliable sources.")
        elif score >= 40:
            st.warning("⚠️ Report has moderate source coverage. Some claims may need verification.")
        else:
            st.error("❌ Limited sources found. Treat this report with caution.")
        st.markdown(f"- 📰 **Sources found:** {len(sources)}")
        domains = list(set(s.get('url','').split('/')[2] for s in sources if s.get('url')))
        st.markdown(f"- 🌐 **Unique domains:** {len(domains)}")
        st.markdown("- 🤖 **Generated by:** Groq LLaMA 3.3 70B")
        st.markdown("- ⚡ **AI label:** This report is AI-generated. Always verify important facts.")

def show_labeled_sources(labeled_sources):
    if not labeled_sources: return
    st.divider()
    st.markdown("### 🔗 Sources Used")
    st.caption("Each source is labeled by type for transparency.")
    cols = st.columns(2)
    for idx, src in enumerate(labeled_sources[:10]):
        with cols[idx % 2]:
            st.markdown(
                f'<div style="border:1px solid #ddd;border-radius:8px;padding:10px;margin:4px 0;">'
                f'<span style="background:{src["color"]}22;color:{src["color"]};border:1px solid {src["color"]};'
                f'border-radius:20px;padding:2px 8px;font-size:11px;font-weight:bold;">{src["tag"]}</span> '
                f'<a href="{src.get("url","#")}" target="_blank" style="font-size:13px;margin-left:6px;">'
                f'{src.get("title","Source")[:50]}</a></div>',
                unsafe_allow_html=True
            )

def show_multi_format(multi_data, level):
    if not multi_data: return
    st.divider()
    st.markdown("### 📊 Multi-Format Output")
    st.caption(f"Report adapted for **{level}** level")
    tab1, tab2, tab3, tab4 = st.tabs(["🟢 Simple", "📘 Detailed", "🏷️ Keywords", "💡 Fun Fact"])
    with tab1:
        st.markdown("#### Simple Explanation")
        st.info(multi_data.get("simple_explanation", ""))
        st.markdown(f"**One Line:** _{multi_data.get('one_line_summary', '')}_")
    with tab2:
        st.markdown("#### Detailed Explanation")
        st.markdown(multi_data.get("detailed_explanation", ""))
    with tab3:
        st.markdown("#### Key Terms")
        terms = multi_data.get("key_terms", [])
        cols = st.columns(3)
        for i, term in enumerate(terms):
            cols[i % 3].markdown(f"📌 **{term}**")
        st.divider()
        st.markdown("#### Important Keywords")
        kws = multi_data.get("important_keywords", [])
        kw_html = " ".join([f'<span style="background:#3f51b522;color:#3f51b5;border:1px solid #3f51b5;border-radius:20px;padding:3px 10px;margin:3px;display:inline-block;font-size:13px;">{k}</span>' for k in kws])
        st.markdown(kw_html, unsafe_allow_html=True)
    with tab4:
        st.markdown("#### 🎉 Fun Fact")
        st.success(multi_data.get("fun_fact", ""))

def show_quiz_section(topic, report, level):
    st.divider()
    st.markdown("### 🧠 Quiz Generator")
    st.caption(f"Questions adapted for **{level}** level")
    col_gen, col_regen = st.columns([1, 1])
    with col_gen:
        if st.button("🎯 Generate Quiz", type="primary", key="gen_quiz_btn"):
            with st.spinner("Generating questions..."):
                try:
                    quiz_data = generate_quiz(topic, report, level)
                    if quiz_data and quiz_data.get("questions"):
                        st.session_state.quiz_data = quiz_data
                        st.session_state.quiz_answers = {}
                        st.session_state.quiz_submitted = False
                        st.session_state.quiz_generated = True
                        st.rerun()
                    else:
                        st.error("Could not generate quiz. Try again.")
                except Exception as e:
                    st.error(f"Quiz error: {e}")
    with col_regen:
        if st.session_state.quiz_generated:
            if st.button("🔄 Regenerate", key="regen_btn"):
                with st.spinner("Regenerating..."):
                    try:
                        quiz_data = generate_quiz(topic, report, level)
                        if quiz_data:
                            st.session_state.quiz_data = quiz_data
                            st.session_state.quiz_answers = {}
                            st.session_state.quiz_submitted = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    if st.session_state.quiz_generated and st.session_state.quiz_data:
        questions = st.session_state.quiz_data.get("questions", [])
        st.markdown(f"**📋 {len(questions)} Questions | Level: {level}**")
        st.markdown("---")
        for i, q in enumerate(questions):
            st.markdown(f"**Q{i+1}. {q['question']}**")
            options_list = [f"{k}. {v}" for k, v in q["options"].items()]
            if not st.session_state.quiz_submitted:
                selected = st.radio("", options_list, key=f"q_{i}", label_visibility="collapsed")
                if selected:
                    st.session_state.quiz_answers[i] = selected[0]
            else:
                user_ans = st.session_state.quiz_answers.get(i, "")
                correct_ans = q["answer"]
                if user_ans == correct_ans:
                    st.success(f"✅ {user_ans}. {q['options'].get(user_ans,'')} — Correct!")
                else:
                    st.error(f"❌ Your answer: {user_ans}. {q['options'].get(user_ans,'')} — Wrong!")
                    st.info(f"✅ Correct: {correct_ans}. {q['options'].get(correct_ans,'')}")
                with st.expander("💡 Explanation"): st.write(q.get("explanation",""))
            st.markdown("")

        if not st.session_state.quiz_submitted:
            if st.button("📝 Submit Quiz", type="primary", key="submit_quiz"):
                if len(st.session_state.quiz_answers) < len(questions):
                    st.warning(f"Answer all {len(questions)} questions first!")
                else:
                    st.session_state.quiz_submitted = True
                    st.rerun()
        else:
            correct = sum(1 for i,q in enumerate(questions) if st.session_state.quiz_answers.get(i,"") == q["answer"])
            total = len(questions)
            pct = int((correct/total)*100)
            st.divider()
            if pct >= 80: st.success(f"🎉 Excellent! {correct}/{total} ({pct}%)")
            elif pct >= 60: st.warning(f"👍 Good! {correct}/{total} ({pct}%)")
            else: st.error(f"📚 {correct}/{total} ({pct}%) — Read the report and retry!")
            if st.button("🔁 Try Again", key="retry_quiz"):
                st.session_state.quiz_answers = {}
                st.session_state.quiz_submitted = False
                st.rerun()

def show_media_tabs(topic):
    st.divider()
    st.markdown("### 🎬 Media Resources")
    enc = urllib.parse.quote(topic)
    dm = st.session_state.dark_mode
    bg = "#1e2130" if dm else "#fff"
    tc = "#aaa" if dm else "#666"
    tab_img, tab_vid, tab_audio = st.tabs(["🖼️ Images", "🎥 Videos", "🎵 Audio"])
    with tab_img:
        sources = [("Google Images",f"https://www.google.com/search?tbm=isch&q={enc}","#4f8ef7","Millions of images"),("Unsplash",f"https://unsplash.com/s/photos/{enc}","#4f8ef7","Free HD photos"),("Wikimedia",f"https://commons.wikimedia.org/w/index.php?search={enc}","#4f8ef7","Free media"),("Flickr",f"https://www.flickr.com/search/?text={enc}","#4f8ef7","Creative commons"),("Pexels",f"https://www.pexels.com/search/{enc}/","#4f8ef7","Free stock"),("NASA",f"https://images.nasa.gov/#/?q={enc}","#4f8ef7","NASA library")]
        cols=st.columns(2)
        for i,(n,u,c,d) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{u}" target="_blank" style="font-size:15px;font-weight:bold;text-decoration:none;color:{c};">{n}</a><p style="margin:4px 0 0;font-size:12px;color:{tc};">{d}</p></div>',unsafe_allow_html=True)
    with tab_vid:
        sources = [("YouTube",f"https://www.youtube.com/results?search_query={enc}","#e05252","YouTube search"),("YouTube EDU",f"https://www.youtube.com/results?search_query={enc}+explained","#e05252","Educational"),("TED Talks",f"https://www.ted.com/search?q={enc}","#e05252","Expert talks"),("Vimeo",f"https://vimeo.com/search?q={enc}","#e05252","HD videos"),("Reuters",f"https://www.reuters.com/search/news?blob={enc}","#e05252","News videos"),("Dailymotion",f"https://www.dailymotion.com/search/{enc}","#e05252","More videos")]
        cols=st.columns(2)
        for i,(n,u,c,d) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{u}" target="_blank" style="font-size:15px;font-weight:bold;text-decoration:none;color:{c};">{n}</a><p style="margin:4px 0 0;font-size:12px;color:{tc};">{d}</p></div>',unsafe_allow_html=True)
    with tab_audio:
        sources = [("Spotify",f"https://open.spotify.com/search/{enc}/podcasts","#1db954","Podcasts"),("Google Podcasts",f"https://podcasts.google.com/search/{enc}","#1db954","Google Podcasts"),("BBC Sounds",f"https://www.bbc.co.uk/sounds/search?q={enc}","#1db954","BBC Audio"),("Apple Podcasts",f"https://podcasts.apple.com/search?term={enc}","#1db954","Apple"),("LibriVox",f"https://librivox.org/search?q={enc}&search_form=advanced","#1db954","Free audiobooks"),("Internet Archive",f"https://archive.org/search?query={enc}&and[]=mediatype%3A%22audio%22","#1db954","Free audio")]
        cols=st.columns(2)
        for i,(n,u,c,d) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{u}" target="_blank" style="font-size:15px;font-weight:bold;text-decoration:none;color:{c};">{n}</a><p style="margin:4px 0 0;font-size:12px;color:{tc};">{d}</p></div>',unsafe_allow_html=True)

def run_research(topic_input, language, template, max_queries, level):
    agent_logs = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    agent_logs.append("**🧠 Planner Agent** - Generating queries...")
    with st.status("Step 1: Planning research queries...", expanded=True) as status:
        queries = plan_research(topic_input)
        queries = queries[:max_queries]
        for i,q in enumerate(queries,1):
            st.write(f"Query {i}: {q}")
            agent_logs.append(f"  → Query {i}: {q}")
        status.update(label="✅ Queries planned!", state="complete")
    progress_bar.progress(20)
    summaries = []; sources = []
    for i,query in enumerate(queries,1):
        agent_logs.append(f"**🔍 Searcher Agent** - Searching: `{query}`")
        with st.status(f"Step 2.{i}: Searching: {query}", expanded=True) as status:
            results = search_web(query)
            if isinstance(results,list):
                for r in results:
                    if isinstance(r,dict) and r.get("url"): sources.append({"title":r.get("title",query),"url":r["url"]})
            elif isinstance(results,dict) and results.get("results"):
                for r in results["results"]:
                    if r.get("url"): sources.append({"title":r.get("title",query),"url":r["url"]})
            agent_logs.append(f"**📝 Summarizer Agent** - Summarizing query {i}...")
            summary = summarize(results)
            summaries.append(summary)
            st.write(summary)
            status.update(label=f"✅ Search {i} complete!", state="complete")
        progress_bar.progress(20 + i*(50//len(queries)))
    agent_logs.append(f"**✍️ Writer Agent** - Writing {template} in {language} for {level} level...")
    with st.status("Step 3: Writing final report...", expanded=True) as status:
        level_hint = get_level_prompt(level)
        report = write_report(topic_input, summaries, language=language, template=template)
        status.update(label="✅ Report ready!", state="complete")
    progress_bar.progress(100)
    status_text.text("✅ Research Complete!")
    return report, sources, summaries, agent_logs

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: RESEARCH ASSISTANT
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.page == "Research Assistant":
    st.title("🔬 Multi-Agent Research Assistant")
    st.markdown("*The smartest way to research any topic in the world.*")
    st.divider()

    # ── PERSONALIZATION BAR ──
    st.markdown("### 🎓 Personalization")
    pcol1, pcol2 = st.columns([2, 3])
    with pcol1:
        level = st.selectbox(
            "Your Knowledge Level:",
            ["Beginner", "Intermediate", "Advanced", "Expert"],
            index=["Beginner","Intermediate","Advanced","Expert"].index(st.session_state.user_level),
            help="Beginner = simple language | Expert = deep technical analysis"
        )
        st.session_state.user_level = level
    with pcol2:
        level_descriptions = {
            "Beginner":     "🟢 Simple language, easy explanations, no jargon",
            "Intermediate": "🟡 Balanced depth, some technical terms explained",
            "Advanced":     "🟠 Technical language, detailed analysis, domain knowledge assumed",
            "Expert":       "🔴 Highly specialized, cutting-edge insights, maximum depth"
        }
        st.info(level_descriptions[level])
    st.divider()

    # ── TOPIC SUGGESTIONS ──
    st.markdown("### 💡 Quick Topic Suggestions:")
    suggestions = ["Artificial Intelligence 2025","Climate Change Solutions","Blockchain Technology",
                   "Space Exploration 2025","Cybersecurity Trends","Electric Vehicles Future",
                   "Quantum Computing","Renewable Energy"]
    selected_topic = ""
    cols = st.columns(4)
    for i, s in enumerate(suggestions):
        if cols[i%4].button(s, key=f"sug_{i}"): selected_topic = s
    st.divider()

    # ── RESEARCH OPTIONS ──
    st.markdown("### 🔎 Research Options")
    research_mode = st.radio("Select Mode:", ["Single Topic","Compare Two Topics"], horizontal=True)
    topic = ""; topic2 = ""
    if research_mode == "Single Topic":
        topic = st.text_input("Enter your topic:", value=selected_topic, placeholder="e.g. Artificial Intelligence trends 2025")
    else:
        c1, c2 = st.columns(2)
        with c1: topic = st.text_input("Topic 1:", placeholder="e.g. Python Programming")
        with c2: topic2 = st.text_input("Topic 2:", placeholder="e.g. JavaScript Programming")
    st.divider()

    # ── REPORT STYLE ──
    st.markdown("### 🎨 Report Language & Style")
    lc, tc2, dc = st.columns(3)
    with lc: language = st.selectbox("Output Language:", ["English","Hindi","Kannada","Tamil","Telugu","Spanish","French","German","Arabic","Chinese","Japanese"])
    with tc2: template = st.selectbox("Report Template:", ["Standard Report","Academic Paper","Blog Post","Executive Summary","News Article"])
    with dc: depth = st.selectbox("Research Depth:", ["Quick (2 queries)","Standard (3 queries)","Deep (5 queries)"])
    depth_map = {"Quick (2 queries)":2,"Standard (3 queries)":3,"Deep (5 queries)":5}
    max_queries = depth_map[depth]

    # ── OUTPUT FORMAT PREFERENCES ──
    st.divider()
    st.markdown("### 📦 Output Preferences")
    oc1, oc2, oc3 = st.columns(3)
    with oc1: want_quiz = st.checkbox("🧠 Auto-generate Quiz", value=True)
    with oc2: want_multiformat = st.checkbox("📊 Multi-format Output", value=True)
    with oc3: want_confidence = st.checkbox("🎯 Confidence Score", value=True)
    st.divider()

    run_btn = st.button("🚀 Start Research", type="primary")

    if run_btn and topic:
        # Reset all state
        for k in ["quiz_data","quiz_answers","quiz_submitted","quiz_generated"]:
            st.session_state[k] = {} if k == "quiz_answers" else (False if "submitted" in k or "generated" in k else None)

        if research_mode == "Single Topic":
            st.divider()
            report, sources, summaries, agent_logs = run_research(topic, language, template, max_queries, level)
            show_agent_log(agent_logs)

            # Confidence & source labeling
            conf_score = calculate_confidence(sources, summaries) if want_confidence else 0
            labeled_sources = label_sources(sources)
            st.session_state.confidence_score = conf_score
            st.session_state.source_labels = labeled_sources

            # Track topic usage for dashboard
            st.session_state.topic_counts[topic] = st.session_state.topic_counts.get(topic, 0) + 1

            st.divider()
            st.subheader("📄 Final Research Report")
            col_report, col_copy = st.columns([5,1])
            with col_copy:
                copy_js = f"""<textarea id='rt' style='display:none'>{report}</textarea>
<button onclick="navigator.clipboard.writeText(document.getElementById('rt').value);this.innerText='Copied!';setTimeout(()=>this.innerText='📋 Copy',2000);"
style="background:#4CAF50;color:white;border:none;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:13px;margin-top:10px;">📋 Copy</button>"""
                st.components.v1.html(copy_js, height=50)
            with col_report: st.markdown(report)

            # Confidence score
            if want_confidence:
                show_confidence_score(conf_score, sources)

            # Labeled sources
            show_labeled_sources(labeled_sources)

            # Multi-format output
            if want_multiformat:
                with st.spinner("Generating multi-format output..."):
                    try:
                        multi_data = generate_multi_format_output(topic, report, level)
                        show_multi_format(multi_data, level)
                    except Exception as e:
                        st.warning(f"Multi-format output error: {e}")

            # Share + Stats
            st.divider()
            encoded = urllib.parse.quote(report[:500])
            share_url = f"https://multi-ai-assistant.streamlit.app/?report={encoded}"
            st.markdown("### 🔗 Share Report")
            st.text_input("Copy link:", value=share_url, key="share_link")
            st.divider()
            word_count = len(report.split())
            reading_time = max(1, round(word_count/200))
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("📝 Words", word_count)
            c2.metric("⏱️ Reading Time", f"{reading_time} min")
            c3.metric("🔤 Characters", len(report))
            c4.metric("🎯 Confidence", f"{conf_score}%")

            # Downloads
            st.divider()
            st.markdown("### 💾 Download Report")
            dc1, dc2, dc3 = st.columns(3)
            with dc1:
                st.download_button("📄 Download TXT", data=report, file_name=f"research_{topic[:30]}.txt", mime="text/plain")
            with dc2:
                pdf_data = generate_pdf(topic, report, template, language)
                st.download_button("📕 Download PDF", data=pdf_data, file_name=f"research_{topic[:30]}.pdf", mime="application/pdf")
            with dc3:
                notes_pdf = generate_notes_pdf(topic, report, st.session_state.quiz_data, template, language, level)
                st.download_button("📗 Notes + Quiz PDF", data=notes_pdf, file_name=f"notes_{topic[:30]}.pdf", mime="application/pdf", help="Study notes with quiz included!")

            # Save to bookmarks button
            st.divider()
            if st.button("⭐ Save to Bookmarks", key="save_btn"):
                already = any(s["topic"] == topic for s in st.session_state.saved_reports)
                if not already:
                    st.session_state.saved_reports.append({"topic": topic, "report": report, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "level": level, "confidence": conf_score})
                    st.success("✅ Saved to Bookmarks! View it in the Dashboard.")
                else:
                    st.info("Already saved!")

            show_media_tabs(topic)

            # Save history
            word_count = len(report.split())
            st.session_state.history.append({"topic":topic,"report":report,"time":datetime.now().strftime("%H:%M:%S"),"words":word_count,"language":language,"template":template,"level":level,"confidence":conf_score})
            st.session_state.current_report = report
            st.session_state.current_topic = topic
            st.session_state.report_ready = True
            st.session_state.chat_messages = []

        else:
            # Compare mode
            st.divider()
            st.markdown("## ⚖️ Topic Comparison")
            cl, cr = st.columns(2)
            with cl:
                st.markdown(f"### {topic}")
                r1,s1,sum1,l1 = run_research(topic, language, template, max_queries, level)
                st.markdown(r1)
                show_labeled_sources(label_sources(s1))
                st.metric("Words", len(r1.split()))
            with cr:
                st.markdown(f"### {topic2}")
                r2,s2,sum2,l2 = run_research(topic2, language, template, max_queries, level)
                st.markdown(r2)
                show_labeled_sources(label_sources(s2))
                st.metric("Words", len(r2.split()))
            st.divider()
            combined = f"# TOPIC 1: {topic}\n\n{r1}\n\n---\n\n# TOPIC 2: {topic2}\n\n{r2}"
            cc1,cc2 = st.columns(2)
            with cc1: st.download_button("📄 Download TXT", data=combined, file_name="comparison.txt", mime="text/plain")
            with cc2:
                pdf_data = generate_pdf(f"{topic} vs {topic2}", combined, template, language)
                st.download_button("📕 Download PDF", data=pdf_data, file_name="comparison.pdf", mime="application/pdf")
            show_media_tabs(topic)

    elif run_btn:
        st.warning("⚠️ Please enter a research topic first!")

    # ── POST-REPORT: QUIZ + CHAT ──
    if st.session_state.report_ready and st.session_state.current_report:
        if want_quiz if 'want_quiz' in dir() else True:
            show_quiz_section(st.session_state.current_topic, st.session_state.current_report, st.session_state.user_level)

        if st.session_state.quiz_generated and st.session_state.quiz_data:
            st.divider()
            notes_pdf = generate_notes_pdf(st.session_state.current_topic, st.session_state.current_report, st.session_state.quiz_data, "Standard Report", "English", st.session_state.user_level)
            st.download_button("📗 Download Notes + Quiz PDF", data=notes_pdf, file_name=f"notes_quiz_{st.session_state.current_topic[:25]}.pdf", mime="application/pdf", type="primary")

        st.divider()
        st.markdown("### 💬 Chat with Your Report")
        st.caption(f"Ask questions about: **{st.session_state.current_topic}**")
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        user_question = st.chat_input("Ask anything about the report...")
        if user_question:
            st.session_state.chat_messages.append({"role":"user","content":user_question})
            with st.chat_message("user"): st.markdown(user_question)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    from langchain_groq import ChatGroq
                    from langchain_core.prompts import ChatPromptTemplate
                    chat_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.5)
                    level_hint = get_level_prompt(st.session_state.user_level)
                    chat_prompt = ChatPromptTemplate.from_template(
                        "You are a helpful assistant. {level_hint}\nREPORT:\n{report}\nQUESTION:\n{question}\nAnswer based on the report. Be concise."
                    )
                    chain = chat_prompt | chat_llm
                    response = chain.invoke({"report":st.session_state.current_report[:3000],"question":user_question,"level_hint":level_hint})
                    answer = response.content
                    st.markdown(answer)
                    st.session_state.chat_messages.append({"role":"assistant","content":answer})

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "Dashboard":
    st.title("📊 Research Dashboard")
    st.markdown("*Your personal research overview and saved reports.*")
    st.divider()

    # ── STATS ROW ──
    total = len(st.session_state.history)
    saved = len(st.session_state.saved_reports)
    avg_conf = int(sum(h.get("confidence",0) for h in st.session_state.history) / total) if total else 0
    total_words = sum(h.get("words",0) for h in st.session_state.history)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("📚 Total Researched", total)
    c2.metric("⭐ Saved Reports", saved)
    c3.metric("🎯 Avg Confidence", f"{avg_conf}%")
    c4.metric("📝 Total Words Read", f"{total_words:,}")
    st.divider()

    # ── RECENT ACTIVITY ──
    tab1, tab2, tab3, tab4 = st.tabs(["📜 Recent History", "⭐ Saved Reports", "📈 Progress", "💡 Recommended"])

    with tab1:
        st.markdown("### Recent Searches")
        if st.session_state.history:
            for item in reversed(st.session_state.history[-10:]):
                dm = st.session_state.dark_mode
                bg = "#1e2130" if dm else "#ffffff"
                conf = item.get("confidence", 0)
                conf_color = "#4CAF50" if conf >= 70 else "#FF9800" if conf >= 40 else "#F44336"
                st.markdown(f"""
                <div style="border:1px solid #ddd;border-radius:10px;padding:14px;margin:8px 0;background:{bg};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:16px;font-weight:bold;">🔬 {item['topic']}</span>
                <span style="background:{conf_color}22;color:{conf_color};border:1px solid {conf_color};
                border-radius:20px;padding:2px 10px;font-size:12px;">⭐ {conf}% confidence</span>
                </div>
                <div style="margin-top:6px;font-size:13px;color:#888;">
                🕐 {item['time']} &nbsp;|&nbsp; 📝 {item['words']} words &nbsp;|&nbsp;
                🎓 {item.get('level','Beginner')} &nbsp;|&nbsp; 🌐 {item.get('language','English')}
                </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No research history yet. Start researching a topic!")

    with tab2:
        st.markdown("### ⭐ Saved / Bookmarked Reports")
        if st.session_state.saved_reports:
            for i, saved_item in enumerate(st.session_state.saved_reports):
                with st.expander(f"📄 {saved_item['topic']} — {saved_item['time']}"):
                    st.write(f"🎓 Level: {saved_item.get('level','Beginner')}")
                    st.write(f"🎯 Confidence: {saved_item.get('confidence',0)}%")
                    st.markdown(saved_item["report"][:500] + "...")
                    col_view, col_del, col_dl = st.columns(3)
                    with col_view:
                        if st.button("📖 View Full Report", key=f"view_{i}"):
                            st.markdown(saved_item["report"])
                    with col_del:
                        if st.button("🗑️ Remove", key=f"del_{i}"):
                            st.session_state.saved_reports.pop(i)
                            st.rerun()
                    with col_dl:
                        pdf_data = generate_pdf(saved_item["topic"], saved_item["report"])
                        st.download_button("📕 Download PDF", data=pdf_data, file_name=f"saved_{saved_item['topic'][:20]}.pdf", mime="application/pdf", key=f"dl_{i}")
        else:
            st.info("No saved reports yet. Click '⭐ Save to Bookmarks' after researching a topic!")

    with tab3:
        st.markdown("### 📈 Your Learning Progress")
        if st.session_state.history:
            # Level distribution
            level_counts = {}
            for h in st.session_state.history:
                l = h.get("level", "Beginner")
                level_counts[l] = level_counts.get(l, 0) + 1
            st.markdown("**Research by Knowledge Level:**")
            for lvl, count in level_counts.items():
                bar = "█" * count + "░" * (10 - min(count, 10))
                st.markdown(f"`{lvl:<12}` {bar} **{count}** searches")
            st.divider()

            # Most researched topics
            if st.session_state.topic_counts:
                st.markdown("**Most Researched Topics:**")
                sorted_topics = sorted(st.session_state.topic_counts.items(), key=lambda x: x[1], reverse=True)
                for topic_name, count in sorted_topics[:5]:
                    st.markdown(f"🔬 **{topic_name}** — researched {count} time(s)")
            st.divider()

            # Language usage
            lang_counts = {}
            for h in st.session_state.history:
                lang = h.get("language", "English")
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
            st.markdown("**Languages Used:**")
            for lang, count in lang_counts.items():
                st.markdown(f"🌐 {lang}: **{count}** report(s)")
        else:
            st.info("Research some topics to see your progress here!")

    with tab4:
        st.markdown("### 💡 Recommended Topics")
        st.caption("Based on your research history")
        if st.session_state.history:
            recent_topics = [h["topic"] for h in st.session_state.history[-3:]]
            recommendations = {
                "Artificial Intelligence": ["Machine Learning Basics","Neural Networks","AI Ethics","Deep Learning","NLP 2025"],
                "Cybersecurity": ["Ethical Hacking","Cloud Security","Zero Trust Architecture","OWASP Top 10","Cyber Laws India"],
                "Blockchain": ["Web3 Development","Smart Contracts","DeFi Explained","NFT Technology","Crypto Regulations"],
                "Climate": ["Carbon Capture Tech","Solar Energy 2025","Green Hydrogen","Electric Grids","Ocean Cleanup"],
                "Space": ["Mars Mission 2026","James Webb Telescope","SpaceX Starship","Asteroid Mining","Moon Base"],
            }
            shown = set()
            for rt in recent_topics:
                for key, recs in recommendations.items():
                    if key.lower() in rt.lower():
                        for rec in recs[:3]:
                            if rec not in shown:
                                st.markdown(f"➡️ **{rec}** _(related to your search: {rt})_")
                                shown.add(rec)
            if not shown:
                st.markdown("**Popular Topics to Explore:**")
                default_recs = ["Generative AI 2025","Large Language Models","India Tech Startups","Web3 Future","Quantum Computing Basics","Green Energy Solutions","Machine Learning for Beginners","Cybersecurity Careers"]
                for rec in default_recs:
                    st.markdown(f"🌟 {rec}")
        else:
            st.info("Start researching topics and we'll recommend related ones here!")

    st.divider()
    if st.button("🗑️ Clear All History", type="secondary"):
        st.session_state.history = []
        st.session_state.topic_counts = {}
        st.success("History cleared!")
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: VISION AI CHAT
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "Vision AI Chat":
    st.title("👁️ Vision AI Chat")
    st.markdown("*Upload an image or file and ask any question about it!*")
    st.divider()
    cn, cc = st.columns(2)
    with cn:
        if st.button("🆕 New Chat", type="primary"):
            st.session_state.vision_messages = []; st.session_state.uploaded_image = None; st.session_state.uploaded_file_text = None; st.rerun()
    with cc:
        if st.button("🗑️ Clear Chat"):
            st.session_state.vision_messages = []; st.rerun()
    st.divider()
    st.markdown("### Upload Image or File")
    ut1, ut2 = st.tabs(["📷 Upload Image","📄 Upload File (PDF/TXT)"])
    with ut1:
        uploaded_image = st.file_uploader("Upload image", type=["jpg","jpeg","png","gif","webp"], key="img_uploader")
        if uploaded_image:
            st.image(uploaded_image, caption="Uploaded Image", width=700)
            image_bytes = uploaded_image.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            st.session_state.uploaded_image = {"data":image_b64,"media_type":uploaded_image.type,"name":uploaded_image.name}
            st.session_state.uploaded_file_text = None
            st.success(f"✅ '{uploaded_image.name}' uploaded!")
    with ut2:
        uploaded_file = st.file_uploader("Upload PDF or TXT", type=["txt","pdf"], key="file_uploader")
        if uploaded_file:
            if uploaded_file.type == "text/plain":
                file_text = uploaded_file.read().decode("utf-8")
                st.session_state.uploaded_file_text = file_text; st.session_state.uploaded_image = None
                st.success(f"✅ '{uploaded_file.name}' uploaded!")
                with st.expander("Preview"): st.text(file_text[:500]+"..." if len(file_text)>500 else file_text)
            elif uploaded_file.type == "application/pdf":
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(uploaded_file)
                    file_text = "".join(page.extract_text()+"\n" for page in pdf_reader.pages)
                    st.session_state.uploaded_file_text = file_text; st.session_state.uploaded_image = None
                    st.success(f"✅ PDF '{uploaded_file.name}' uploaded! ({len(pdf_reader.pages)} pages)")
                    with st.expander("Preview"): st.text(file_text[:500]+"..." if len(file_text)>500 else file_text)
                except Exception as e:
                    st.error(f"PDF error: {e}")
    st.divider()
    st.markdown("### 💬 Chat")
    if st.session_state.uploaded_image: st.info(f"🖼️ Image: **{st.session_state.uploaded_image['name']}** — Ask anything!")
    elif st.session_state.uploaded_file_text: st.info("📄 File loaded — Ask anything!")
    else: st.info("💬 Ask anything, or upload an image/file above!")
    for msg in st.session_state.vision_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    user_input = st.chat_input("Ask anything...")
    if user_input:
        st.session_state.vision_messages.append({"role":"user","content":user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    groq_key = get_groq_key()
                    if not groq_key: st.error("❌ GROQ_API_KEY not found!"); st.stop()
                    from groq import Groq
                    client = Groq(api_key=groq_key)
                    messages = []
                    if st.session_state.uploaded_image:
                        system_msg = "You are a helpful Vision AI assistant. Analyze the provided image and answer clearly."
                    elif st.session_state.uploaded_file_text:
                        system_msg = f"You are a helpful AI. The user uploaded a file:\n\n{st.session_state.uploaded_file_text[:4000]}\n\nAnswer based on this content."
                    else:
                        system_msg = "You are a helpful AI assistant. Answer clearly and helpfully."
                    messages.append({"role":"system","content":system_msg})
                    for prev in st.session_state.vision_messages[-6:]:
                        messages.append({"role":prev["role"],"content":prev["content"]})
                    if st.session_state.uploaded_image:
                        img = st.session_state.uploaded_image
                        messages[-1] = {"role":"user","content":[{"type":"image_url","image_url":{"url":f"data:{img['media_type']};base64,{img['data']}"}},{"type":"text","text":user_input}]}
                        model = "meta-llama/llama-4-scout-17b-16e-instruct"
                    else:
                        model = "llama-3.3-70b-versatile"
                    response = client.chat.completions.create(model=model, messages=messages, max_tokens=1500)
                    answer = response.choices[0].message.content
                    st.markdown(answer)
                    st.session_state.vision_messages.append({"role":"assistant","content":answer})
                except Exception as e:
                    err = str(e)
                    st.error(f"❌ Error: {err}")
                    st.session_state.vision_messages.append({"role":"assistant","content":f"Error: {err}"})

st.divider()
st.markdown("🌐 Making knowledge accessible to everyone, everywhere.")
