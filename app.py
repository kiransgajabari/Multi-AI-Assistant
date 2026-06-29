import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from fpdf import FPDF
import io
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

if "history" not in st.session_state: st.session_state.history = []
if "dark_mode" not in st.session_state: st.session_state.dark_mode = False
if "current_report" not in st.session_state: st.session_state.current_report = ""
if "current_topic" not in st.session_state: st.session_state.current_topic = ""
if "chat_messages" not in st.session_state: st.session_state.chat_messages = []
if "report_ready" not in st.session_state: st.session_state.report_ready = False
if "page" not in st.session_state: st.session_state.page = "Research Assistant"
if "vision_messages" not in st.session_state: st.session_state.vision_messages = []
if "uploaded_image" not in st.session_state: st.session_state.uploaded_image = None
if "uploaded_file_text" not in st.session_state: st.session_state.uploaded_file_text = None
# NEW: Quiz state
if "quiz_data" not in st.session_state: st.session_state.quiz_data = None
if "quiz_answers" not in st.session_state: st.session_state.quiz_answers = {}
if "quiz_submitted" not in st.session_state: st.session_state.quiz_submitted = False
if "quiz_generated" not in st.session_state: st.session_state.quiz_generated = False

def get_groq_key():
    try:
        return st.secrets["GROQ_API_KEY"]
    except:
        return os.getenv("GROQ_API_KEY")

def apply_theme(dark_mode):
    if dark_mode:
        st.markdown("""<style>
.stApp{background-color:#0e1117;color:#fafafa;}
.stTextInput>div>div>input{background-color:#1e2130;color:#fafafa;border:1px solid #444;}
.stExpander{background-color:#1e2130;border:1px solid #333;}
.stButton>button{background-color:#262940;color:#fff;border:1px solid #555;}
h1,h2,h3,h4{color:#e0e0ff!important;}
.quiz-box{background-color:#1e2130;border:1px solid #444;border-radius:12px;padding:16px;margin:10px 0;}
</style>""", unsafe_allow_html=True)
    else:
        st.markdown("""<style>
.stApp{background-color:#f8f9ff;}
.report-box{background-color:#ffffff;border:1px solid #e0e0e0;border-radius:12px;padding:20px;}
.quiz-box{background-color:#ffffff;border:1px solid #e0e0e0;border-radius:12px;padding:16px;margin:10px 0;}
</style>""", unsafe_allow_html=True)

apply_theme(st.session_state.dark_mode)

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/bot.png", width=80)
    st.title("Research Assistant")
    st.markdown("### Navigation")
    page = st.radio("Choose Feature:", ["Research Assistant", "Vision AI Chat"], label_visibility="collapsed")
    st.session_state.page = page
    st.divider()
    st.markdown("**Welcome!**\n\nEnter any topic and get a complete research report in seconds!")
    st.divider()
    st.markdown("**Settings:**")
    dark_toggle = st.toggle("Dark Mode", value=st.session_state.dark_mode)
    if dark_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_toggle
        st.rerun()
    st.divider()
    if st.session_state.page == "Research Assistant":
        st.header("Research History")
        history_search = st.text_input("Filter history:", placeholder="Search topics...")
        if st.session_state.history:
            filtered = [item for item in st.session_state.history if history_search.lower() in item['topic'].lower()] if history_search else st.session_state.history
            if filtered:
                for item in reversed(filtered):
                    with st.expander(f"{item['topic'][:25]}..."):
                        st.write(f"Time: {item['time']}")
                        st.write(f"Words: {item['words']}")
                        st.write(f"Language: {item.get('language','English')}")
                        st.write(f"Template: {item.get('template','Standard Report')}")
                        st.write(item['report'][:200]+"...")
            else:
                st.info("No matching topics found.")
        else:
            st.info("No research history yet!")

# ── HELPER FUNCTIONS ──────────────────────────────────────────────────────────

def generate_quiz(topic, report):
    """Generate 5 MCQ questions from the report using Groq AI"""
    groq_key = get_groq_key()
    if not groq_key:
        return None
    from groq import Groq
    client = Groq(api_key=groq_key)
    prompt = f"""You are a quiz maker. Based on this research report about "{topic}", generate exactly 5 multiple choice questions.

REPORT:
{report[:3000]}

Return ONLY valid JSON in this exact format, nothing else:
{{
  "questions": [
    {{
      "question": "Question text here?",
      "options": {{
        "A": "Option A text",
        "B": "Option B text",
        "C": "Option C text",
        "D": "Option D text"
      }},
      "answer": "A",
      "explanation": "Brief explanation why this is correct."
    }}
  ]
}}

Rules:
- Exactly 5 questions
- Questions must be based on the report content
- Each question has exactly 4 options (A, B, C, D)
- answer must be one of: A, B, C, D
- Return ONLY the JSON, no markdown, no extra text"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    # Clean any markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    data = json.loads(raw)
    return data

def generate_notes_pdf(topic, report, quiz_data=None, template="Standard Report", language="English"):
    """Generate a structured Notes PDF with quiz at the end"""
    from fpdf.enums import XPos, YPos
    NX, NY = XPos.LMARGIN, YPos.NEXT

    def clean(text):
        replacements = {
            "\u2022":"*","\u2023":"*","\u25cf":"*","\u2018":"'","\u2019":"'",
            "\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"--","\u2026":"...",
            "\u2192":"->","\u2713":"[OK]","\u2714":"[OK]","\u20ac":"EUR","\u00a3":"GBP"
        }
        for char, rep in replacements.items():
            text = text.replace(char, rep)
        return text.encode("ascii","replace").decode("ascii")

    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # ── HEADER ──
    pdf.set_fill_color(63, 81, 181)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", style="B", size=16)
    pdf.cell(0, 10, clean(f"STUDY NOTES: {topic}")[:80], new_x=NX, new_y=NY, fill=True, align="C")
    pdf.ln(2)
    pdf.set_font("helvetica", size=9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, clean(f"Template: {template} | Language: {language} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), new_x=NX, new_y=NY)
    pdf.ln(3)
    pdf.set_draw_color(180, 190, 220)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(4)

    # ── REPORT CONTENT ──
    pdf.set_text_color(30, 30, 30)
    for line in [l for l in clean(report).split("\n") if not l.strip().startswith("<!--")]:
        line = line.strip()
        if pdf.get_y() > 255:
            pdf.add_page()
            pdf.ln(5)
        if not line:
            pdf.ln(2)
        elif line.startswith("# "):
            pdf.set_font("helvetica", style="B", size=13)
            pdf.set_text_color(40, 55, 160)
            pdf.multi_cell(0, 8, line[2:].strip(), new_x=NX, new_y=NY)
            pdf.set_text_color(30, 30, 30)
        elif line.startswith("## "):
            pdf.set_font("helvetica", style="B", size=11)
            pdf.set_text_color(63, 81, 181)
            pdf.multi_cell(0, 7, line[3:].strip(), new_x=NX, new_y=NY)
            pdf.set_text_color(30, 30, 30)
        elif line.startswith("### "):
            pdf.set_font("helvetica", style="B", size=10)
            pdf.set_text_color(80, 80, 180)
            pdf.multi_cell(0, 7, line[4:].strip(), new_x=NX, new_y=NY)
            pdf.set_text_color(30, 30, 30)
        elif line.startswith(("- ", "* ", "+ ")):
            pdf.set_font("helvetica", size=10)
            pdf.multi_cell(0, 6, " * " + line[2:].strip(), new_x=NX, new_y=NY)
        elif line.startswith("**") and line.endswith("**") and len(line) > 4:
            pdf.set_font("helvetica", style="B", size=10)
            pdf.multi_cell(0, 6, line[2:-2].strip(), new_x=NX, new_y=NY)
        else:
            pdf.set_font("helvetica", size=10)
            pdf.multi_cell(0, 6, line, new_x=NX, new_y=NY)

    # ── QUIZ SECTION (if quiz exists) ──
    if quiz_data and quiz_data.get("questions"):
        pdf.add_page()
        pdf.set_fill_color(76, 175, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", style="B", size=14)
        pdf.cell(0, 10, "QUIZ - Test Your Knowledge", new_x=NX, new_y=NY, fill=True, align="C")
        pdf.ln(4)
        pdf.set_text_color(30, 30, 30)

        for i, q in enumerate(quiz_data["questions"], 1):
            if pdf.get_y() > 230:
                pdf.add_page()
                pdf.ln(5)
            pdf.set_font("helvetica", style="B", size=11)
            pdf.set_text_color(40, 55, 160)
            pdf.multi_cell(0, 7, clean(f"Q{i}. {q['question']}"), new_x=NX, new_y=NY)
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("helvetica", size=10)
            for opt, text in q["options"].items():
                pdf.multi_cell(0, 6, clean(f"   {opt}. {text}"), new_x=NX, new_y=NY)
            pdf.set_font("helvetica", style="B", size=10)
            pdf.set_text_color(0, 128, 0)
            pdf.multi_cell(0, 6, clean(f"   Answer: {q['answer']}. {q['options'].get(q['answer'], '')}"), new_x=NX, new_y=NY)
            pdf.set_font("helvetica", style="I", size=9)
            pdf.set_text_color(100, 100, 100)
            pdf.multi_cell(0, 6, clean(f"   Explanation: {q.get('explanation', '')}"), new_x=NX, new_y=NY)
            pdf.set_text_color(30, 30, 30)
            pdf.ln(3)

    # ── FOOTER ──
    pdf.set_y(-18)
    pdf.set_font("helvetica", style="I", size=8)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 8, f"Study Notes | {datetime.now().strftime('%Y-%m-%d')} | Multi-Agent Research Assistant", align="C")

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    return bytes(pdf_output)


def generate_pdf(topic, report, template="Standard Report", language="English"):
    """Original PDF generator (kept for backward compatibility)"""
    from fpdf.enums import XPos, YPos
    NX, NY = XPos.LMARGIN, YPos.NEXT

    def clean(text):
        replacements = {"\u2022":"*","\u2023":"*","\u25cf":"*","\u2018":"'","\u2019":"'","\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"--","\u2026":"...","\u2192":"->","\u2713":"[OK]","\u2714":"[OK]","\u20ac":"EUR","\u00a3":"GBP"}
        for char, rep in replacements.items(): text = text.replace(char, rep)
        return text.encode("ascii","replace").decode("ascii")

    pdf = FPDF(format="A4")
    pdf.set_margins(20,20,20)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()
    pdf.set_fill_color(63,81,181)
    pdf.set_text_color(255,255,255)
    pdf.set_font("helvetica",style="B",size=15)
    pdf.cell(0,9,clean(topic)[:80],new_x=NX,new_y=NY,fill=True,align="C")
    pdf.ln(4)
    pdf.set_font("helvetica",size=9)
    pdf.set_text_color(120,120,120)
    pdf.cell(0,6,clean(f"Template: {template} | Language: {language} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"),new_x=NX,new_y=NY)
    pdf.ln(2)
    pdf.set_draw_color(180,190,220)
    pdf.line(20,pdf.get_y(),190,pdf.get_y())
    pdf.ln(4)
    pdf.set_text_color(30,30,30)
    for line in [l for l in clean(report).split("\n") if not l.strip().startswith("<!--")]:
        line = line.strip()
        if pdf.get_y() > 255: pdf.add_page(); pdf.ln(5)
        if not line: pdf.ln(2)
        elif line.startswith("# "): pdf.set_font("helvetica",style="B",size=13); pdf.set_text_color(40,55,160); pdf.multi_cell(0,8,line[2:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("## "): pdf.set_font("helvetica",style="B",size=11); pdf.set_text_color(63,81,181); pdf.multi_cell(0,7,line[3:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith("### "): pdf.set_font("helvetica",style="B",size=10); pdf.set_text_color(80,80,180); pdf.multi_cell(0,7,line[4:].strip(),new_x=NX,new_y=NY); pdf.set_text_color(30,30,30)
        elif line.startswith(("- ","* ","+ ")): pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6," * "+line[2:].strip(),new_x=NX,new_y=NY)
        elif line.startswith("**") and line.endswith("**") and len(line)>4: pdf.set_font("helvetica",style="B",size=10); pdf.multi_cell(0,6,line[2:-2].strip(),new_x=NX,new_y=NY)
        else: pdf.set_font("helvetica",size=10); pdf.multi_cell(0,6,line,new_x=NX,new_y=NY)
    pdf.set_y(-18)
    pdf.set_font("helvetica",style="I",size=8)
    pdf.set_text_color(160,160,160)
    pdf.cell(0,8,f"Research Report | {datetime.now().strftime('%Y-%m-%d')}",align="C")
    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str): return pdf_output.encode("latin-1")
    return bytes(pdf_output)


def show_agent_log(logs):
    with st.expander("Agent Activity Log", expanded=False):
        for log in logs: st.markdown(log)


def show_quiz_section(topic, report):
    """Show the Quiz Generator UI"""
    st.divider()
    st.markdown("### 🧠 Quiz Generator")
    st.caption("Test your knowledge based on the research report!")

    col_gen, col_reset = st.columns([1, 1])
    with col_gen:
        if st.button("🎯 Generate Quiz", type="primary", key="gen_quiz_btn"):
            with st.spinner("Generating 5 questions from your report..."):
                try:
                    quiz_data = generate_quiz(topic, report)
                    if quiz_data and quiz_data.get("questions"):
                        st.session_state.quiz_data = quiz_data
                        st.session_state.quiz_answers = {}
                        st.session_state.quiz_submitted = False
                        st.session_state.quiz_generated = True
                        st.rerun()
                    else:
                        st.error("Could not generate quiz. Please try again.")
                except Exception as e:
                    st.error(f"Quiz generation failed: {str(e)}")

    with col_reset:
        if st.session_state.quiz_generated:
            if st.button("🔄 Regenerate Quiz", key="regen_quiz_btn"):
                with st.spinner("Generating new questions..."):
                    try:
                        quiz_data = generate_quiz(topic, report)
                        if quiz_data:
                            st.session_state.quiz_data = quiz_data
                            st.session_state.quiz_answers = {}
                            st.session_state.quiz_submitted = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    # Show quiz if generated
    if st.session_state.quiz_generated and st.session_state.quiz_data:
        questions = st.session_state.quiz_data.get("questions", [])
        st.markdown(f"**📋 {len(questions)} Questions — Topic: {topic}**")
        st.markdown("---")

        for i, q in enumerate(questions):
            st.markdown(f"**Q{i+1}. {q['question']}**")
            options_list = [f"{k}. {v}" for k, v in q["options"].items()]

            if not st.session_state.quiz_submitted:
                selected = st.radio(
                    f"Select answer for Q{i+1}:",
                    options_list,
                    key=f"q_{i}",
                    label_visibility="collapsed"
                )
                if selected:
                    st.session_state.quiz_answers[i] = selected[0]  # Store just "A", "B", "C", or "D"
            else:
                # Show results
                user_ans = st.session_state.quiz_answers.get(i, "")
                correct_ans = q["answer"]
                correct_text = f"{correct_ans}. {q['options'].get(correct_ans, '')}"

                if user_ans == correct_ans:
                    st.success(f"✅ Your answer: {user_ans}. {q['options'].get(user_ans, '')} — Correct!")
                else:
                    st.error(f"❌ Your answer: {user_ans}. {q['options'].get(user_ans, '')} — Wrong!")
                    st.info(f"✅ Correct answer: {correct_text}")

                with st.expander("💡 Explanation"):
                    st.write(q.get("explanation", "No explanation available."))
            st.markdown("")

        # Submit / Score buttons
        if not st.session_state.quiz_submitted:
            if st.button("📝 Submit Quiz", type="primary", key="submit_quiz"):
                if len(st.session_state.quiz_answers) < len(questions):
                    st.warning(f"Please answer all {len(questions)} questions before submitting!")
                else:
                    st.session_state.quiz_submitted = True
                    st.rerun()
        else:
            # Calculate and show score
            correct = sum(
                1 for i, q in enumerate(questions)
                if st.session_state.quiz_answers.get(i, "") == q["answer"]
            )
            total = len(questions)
            pct = int((correct / total) * 100)

            st.divider()
            if pct >= 80:
                st.success(f"🎉 Excellent! You scored **{correct}/{total} ({pct}%)**!")
            elif pct >= 60:
                st.warning(f"👍 Good! You scored **{correct}/{total} ({pct}%)**. Review the report to improve!")
            else:
                st.error(f"📚 You scored **{correct}/{total} ({pct}%)**. Read the report again and retry!")

            if st.button("🔁 Try Again", key="retry_quiz"):
                st.session_state.quiz_answers = {}
                st.session_state.quiz_submitted = False
                st.rerun()


def show_media_tabs(topic):
    st.divider()
    st.markdown("### Media Resources")
    st.caption(f"Explore images, videos, and audio related to: **{topic}**")
    tab_img, tab_vid, tab_audio = st.tabs(["Images", "Videos", "Audio"])
    enc = urllib.parse.quote(topic)
    dm = st.session_state.dark_mode
    bg = "#1e2130" if dm else "#fff"
    tc = "#aaa" if dm else "#666"

    with tab_img:
        st.markdown("#### Related Images")
        sources = [("Google Images",f"https://www.google.com/search?tbm=isch&q={enc}","#4f8ef7","Search millions of images"),("Unsplash",f"https://unsplash.com/s/photos/{enc}","#4f8ef7","Free high-quality photos"),("Wikimedia",f"https://commons.wikimedia.org/w/index.php?search={enc}","#4f8ef7","Free media"),("Flickr",f"https://www.flickr.com/search/?text={enc}","#4f8ef7","Creative commons images"),("Pexels",f"https://www.pexels.com/search/{enc}/","#4f8ef7","Free stock photos"),("NASA Images",f"https://images.nasa.gov/#/?q={enc}","#4f8ef7","NASA image library")]
        cols = st.columns(2)
        for i,(name,url,color,desc) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{url}" target="_blank" style="font-size:16px;font-weight:bold;text-decoration:none;color:{color};">{name}</a><p style="margin:4px 0 0 0;font-size:13px;color:{tc};">{desc}</p></div>', unsafe_allow_html=True)

    with tab_vid:
        st.markdown("#### Related Videos")
        sources = [("YouTube",f"https://www.youtube.com/results?search_query={enc}","#e05252","YouTube search"),("YouTube EDU",f"https://www.youtube.com/results?search_query={enc}+explained","#e05252","Educational videos"),("TED Talks",f"https://www.ted.com/search?q={enc}","#e05252","Expert TED Talks"),("Vimeo",f"https://vimeo.com/search?q={enc}","#e05252","High-quality videos"),("Reuters",f"https://www.reuters.com/search/news?blob={enc}","#e05252","News videos"),("Dailymotion",f"https://www.dailymotion.com/search/{enc}","#e05252","Dailymotion videos")]
        cols = st.columns(2)
        for i,(name,url,color,desc) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{url}" target="_blank" style="font-size:16px;font-weight:bold;text-decoration:none;color:{color};">{name}</a><p style="margin:4px 0 0 0;font-size:13px;color:{tc};">{desc}</p></div>', unsafe_allow_html=True)

    with tab_audio:
        st.markdown("#### Related Audio & Podcasts")
        sources = [("Spotify",f"https://open.spotify.com/search/{enc}/podcasts","#1db954","Spotify Podcasts"),("Google Podcasts",f"https://podcasts.google.com/search/{enc}","#1db954","Google Podcasts"),("BBC Sounds",f"https://www.bbc.co.uk/sounds/search?q={enc}","#1db954","BBC Audio"),("Apple Podcasts",f"https://podcasts.apple.com/search?term={enc}","#1db954","Apple Podcasts"),("LibriVox",f"https://librivox.org/search?q={enc}&search_form=advanced","#1db954","Free audiobooks"),("Internet Archive",f"https://archive.org/search?query={enc}&and[]=mediatype%3A%22audio%22","#1db954","Free audio")]
        cols = st.columns(2)
        for i,(name,url,color,desc) in enumerate(sources):
            with cols[i%2]: st.markdown(f'<div style="border:1px solid #ddd;border-radius:10px;padding:12px;margin:6px 0;background:{bg};"><a href="{url}" target="_blank" style="font-size:16px;font-weight:bold;text-decoration:none;color:{color};">{name}</a><p style="margin:4px 0 0 0;font-size:13px;color:{tc};">{desc}</p></div>', unsafe_allow_html=True)


def run_research(topic_input, language, template, max_queries):
    agent_logs = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text("Planning research queries...")
    agent_logs.append("**Planner Agent** - Starting query generation...")
    with st.status("Step 1: Planning research queries...", expanded=True) as status:
        queries = plan_research(topic_input)
        queries = queries[:max_queries]
        for i,q in enumerate(queries,1):
            st.write(f"Query {i}: {q}")
            agent_logs.append(f"  Query {i}: {q}")
        status.update(label="Queries planned!", state="complete")
        agent_logs.append("**Planner Agent** - Done!")
    progress_bar.progress(25)
    status_text.text("Step 1 Complete!")
    summaries = []
    sources = []
    for i,query in enumerate(queries,1):
        agent_logs.append(f"**Searcher Agent** - Searching: `{query}`")
        with st.status(f"Step 2.{i}: Searching: {query}", expanded=True) as status:
            results = search_web(query)
            if isinstance(results,list):
                for r in results:
                    if isinstance(r,dict) and r.get("url"): sources.append({"title":r.get("title",query),"url":r["url"]})
            elif isinstance(results,dict) and results.get("results"):
                for r in results["results"]:
                    if r.get("url"): sources.append({"title":r.get("title",query),"url":r["url"]})
            st.write("Summarizing results...")
            agent_logs.append(f"**Summarizer Agent** - Summarizing query {i}...")
            summary = summarize(results)
            summaries.append(summary)
            st.write(summary)
            status.update(label=f"Search {i} complete!", state="complete")
            agent_logs.append(f"**Summarizer Agent** - Done for query {i}!")
        progress_bar.progress(25+(i*(50//len(queries))))
        status_text.text(f"Search {i} Complete!")
    status_text.text("Writing final report...")
    agent_logs.append(f"**Writer Agent** - Writing {template} in {language}...")
    with st.status("Step 3: Writing final report...", expanded=True) as status:
        report = write_report(topic_input, summaries, language=language, template=template)
        status.update(label="Report ready!", state="complete")
        agent_logs.append("**Writer Agent** - Report complete!")
    progress_bar.progress(100)
    status_text.text("Research Complete!")
    return report, sources, agent_logs


# ── MAIN PAGE ─────────────────────────────────────────────────────────────────

if st.session_state.page == "Research Assistant":
    st.title("Multi-Agent Research Assistant")
    st.markdown("*The smartest way to research any topic in the world.*")
    st.divider()

    st.markdown("### Quick Topic Suggestions:")
    suggestions = ["Artificial Intelligence 2025","Climate Change Solutions","Blockchain Technology","Space Exploration 2025","Cybersecurity Trends","Electric Vehicles Future","Quantum Computing","Renewable Energy"]
    selected_topic = ""
    cols = st.columns(4)
    for i, suggestion in enumerate(suggestions):
        if cols[i%4].button(suggestion, key=f"sug_{i}"):
            selected_topic = suggestion
    st.divider()

    st.markdown("### Research Options")
    research_mode = st.radio("Select Mode:", ["Single Topic","Compare Two Topics"], horizontal=True)
    topic = ""
    topic2 = ""
    if research_mode == "Single Topic":
        topic = st.text_input("Enter your topic:", value=selected_topic, placeholder="Example: Artificial Intelligence trends 2025")
    else:
        col_t1, col_t2 = st.columns(2)
        with col_t1: topic = st.text_input("Topic 1:", placeholder="e.g. Python Programming")
        with col_t2: topic2 = st.text_input("Topic 2:", placeholder="e.g. JavaScript Programming")
    st.divider()

    st.markdown("### Report Language & Style")
    lang_col, tmpl_col, depth_col = st.columns(3)
    with lang_col: language = st.selectbox("Output Language:", ["English","Hindi","Spanish","French","German","Arabic","Chinese","Japanese"])
    with tmpl_col: template = st.selectbox("Report Template:", ["Standard Report","Academic Paper","Blog Post","Executive Summary","News Article"])
    with depth_col: depth = st.selectbox("Research Depth:", ["Quick (2 queries)","Standard (3 queries)","Deep (5 queries)"])
    depth_map = {"Quick (2 queries)":2,"Standard (3 queries)":3,"Deep (5 queries)":5}
    max_queries = depth_map[depth]
    st.divider()

    col1, col2 = st.columns([1,4])
    with col1: run_btn = st.button("🚀 Start Research", type="primary")

    if run_btn and (topic or (research_mode=="Compare Two Topics" and topic and topic2)):
        # Reset quiz state on new research
        st.session_state.quiz_data = None
        st.session_state.quiz_answers = {}
        st.session_state.quiz_submitted = False
        st.session_state.quiz_generated = False

        if research_mode=="Single Topic":
            st.divider()
            report, sources, agent_logs = run_research(topic, language, template, max_queries)
            show_agent_log(agent_logs)
            st.divider()
            st.subheader("Final Research Report")
            col_report, col_copy = st.columns([5,1])
            with col_copy:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                copy_js = f"""<textarea id='reportText' style='display:none'>{report}</textarea>
<button onclick="navigator.clipboard.writeText(document.getElementById('reportText').value);this.innerText='Copied!';setTimeout(()=>this.innerText='Copy',2000);"
style="background:#4CAF50;color:white;border:none;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:14px;margin-top:10px;">Copy</button>"""
                st.components.v1.html(copy_js, height=50)
            with col_report: st.markdown(report)

            if sources:
                st.divider()
                st.markdown("### Sources Used")
                for idx,src in enumerate(sources[:10],1): st.markdown(f"{idx}. [{src['title']}]({src['url']})")

            st.divider()
            encoded = urllib.parse.quote(report[:500])
            share_url = f"https://multi-ai-assistant.streamlit.app/?report={encoded}"
            st.markdown("### Share Report")
            st.text_input("Copy this link to share:", value=share_url, key="share_link")
            st.divider()

            word_count = len(report.split())
            reading_time = max(1, round(word_count/200))
            char_count = len(report)
            col1,col2,col3 = st.columns(3)
            col1.metric("Word Count", word_count)
            col2.metric("Reading Time", f"{reading_time} min")
            col3.metric("Characters", char_count)

            st.divider()
            st.markdown("### Download Report")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    label="📄 Download as TXT",
                    data=report,
                    file_name=f"research_{topic[:30]}.txt",
                    mime="text/plain"
                )
            with col2:
                pdf_data = generate_pdf(topic, report, template, language)
                st.download_button(
                    label="📕 Download as PDF",
                    data=pdf_data,
                    file_name=f"research_{topic[:30]}.pdf",
                    mime="application/pdf"
                )
            with col3:
                notes_pdf = generate_notes_pdf(topic, report, st.session_state.quiz_data, template, language)
                st.download_button(
                    label="📗 Download Notes + Quiz PDF",
                    data=notes_pdf,
                    file_name=f"notes_{topic[:30]}.pdf",
                    mime="application/pdf",
                    help="Structured study notes with quiz questions included!"
                )

            show_media_tabs(topic)
            st.session_state.history.append({"topic":topic,"report":report,"time":datetime.now().strftime("%H:%M:%S"),"words":word_count,"language":language,"template":template})
            st.session_state.current_report = report
            st.session_state.current_topic = topic
            st.session_state.report_ready = True
            st.session_state.chat_messages = []

        else:
            st.divider()
            st.markdown("## Topic Comparison")
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown(f"### {topic}")
                report1,sources1,logs1 = run_research(topic, language, template, max_queries)
                st.markdown(report1)
                if sources1:
                    st.markdown("**Sources:**")
                    for s in sources1[:5]: st.markdown(f"- [{s['title']}]({s['url']})")
                st.metric("Words", len(report1.split()))
            with col_right:
                st.markdown(f"### {topic2}")
                report2,sources2,logs2 = run_research(topic2, language, template, max_queries)
                st.markdown(report2)
                if sources2:
                    st.markdown("**Sources:**")
                    for s in sources2[:5]: st.markdown(f"- [{s['title']}]({s['url']})")
                st.metric("Words", len(report2.split()))
            st.divider()
            st.markdown("### Download Comparison")
            combined = f"# TOPIC 1: {topic}\n\n{report1}\n\n---\n\n# TOPIC 2: {topic2}\n\n{report2}"
            col_dl1,col_dl2 = st.columns(2)
            with col_dl1: st.download_button("Download as TXT", data=combined, file_name="comparison_report.txt", mime="text/plain")
            with col_dl2:
                pdf_data = generate_pdf(f"{topic} vs {topic2}", combined, template, language)
                st.download_button("Download as PDF", data=pdf_data, file_name="comparison_report.pdf", mime="application/pdf")
            show_media_tabs(topic)

    elif run_btn:
        st.warning("Please enter a research topic first!")

    # ── QUIZ SECTION (shown after report is ready) ──
    if st.session_state.report_ready and st.session_state.current_report:
        show_quiz_section(st.session_state.current_topic, st.session_state.current_report)

        # ── NOTES PDF with Quiz ──
        if st.session_state.quiz_generated and st.session_state.quiz_data:
            st.divider()
            st.markdown("### 📗 Download Notes + Quiz PDF")
            st.caption("Your study notes with quiz questions and answers included!")
            notes_pdf = generate_notes_pdf(
                st.session_state.current_topic,
                st.session_state.current_report,
                st.session_state.quiz_data,
                "Standard Report",
                "English"
            )
            st.download_button(
                label="📗 Download Notes + Quiz PDF",
                data=notes_pdf,
                file_name=f"notes_quiz_{st.session_state.current_topic[:30]}.pdf",
                mime="application/pdf",
                type="primary"
            )

        # ── CHAT WITH REPORT ──
        st.divider()
        st.markdown("### Chat with Your Report")
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
                    chat_prompt = ChatPromptTemplate.from_template("You are a helpful assistant. The user has a research report.\nREPORT:\n{report}\nUSER QUESTION:\n{question}\nAnswer based on the report. Be concise.")
                    chain = chat_prompt | chat_llm
                    response = chain.invoke({"report":st.session_state.current_report[:3000],"question":user_question})
                    answer = response.content
                    st.markdown(answer)
                    st.session_state.chat_messages.append({"role":"assistant","content":answer})

# ── VISION AI CHAT PAGE ───────────────────────────────────────────────────────
elif st.session_state.page == "Vision AI Chat":
    st.title("👁️ Vision AI Chat")
    st.markdown("*Upload an image or file and ask any question about it!*")
    st.divider()
    col_new, col_clear = st.columns([1,1])
    with col_new:
        if st.button("🆕 New Chat", type="primary"):
            st.session_state.vision_messages = []
            st.session_state.uploaded_image = None
            st.session_state.uploaded_file_text = None
            st.rerun()
    with col_clear:
        if st.button("🗑️ Clear Chat"):
            st.session_state.vision_messages = []
            st.rerun()
    st.divider()
    st.markdown("### Upload Image or File")
    upload_tab1, upload_tab2 = st.tabs(["📷 Upload Image", "📄 Upload File (PDF/TXT)"])
    with upload_tab1:
        uploaded_image = st.file_uploader("Upload an image and ask questions about it", type=["jpg","jpeg","png","gif","webp"], key="img_uploader")
        if uploaded_image:
            st.image(uploaded_image, caption="Uploaded Image", width=700)
            image_bytes = uploaded_image.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            st.session_state.uploaded_image = {"data": image_b64, "media_type": uploaded_image.type, "name": uploaded_image.name}
            st.session_state.uploaded_file_text = None
            st.success(f"✅ Image '{uploaded_image.name}' uploaded successfully!")
    with upload_tab2:
        uploaded_file = st.file_uploader("Upload a PDF or TXT file and ask questions about it", type=["txt","pdf"], key="file_uploader")
        if uploaded_file:
            if uploaded_file.type == "text/plain":
                file_text = uploaded_file.read().decode("utf-8")
                st.session_state.uploaded_file_text = file_text
                st.session_state.uploaded_image = None
                st.success(f"✅ File '{uploaded_file.name}' uploaded!")
                with st.expander("File Preview"): st.text(file_text[:500]+"..." if len(file_text)>500 else file_text)
            elif uploaded_file.type == "application/pdf":
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(uploaded_file)
                    file_text = ""
                    for page in pdf_reader.pages: file_text += page.extract_text()+"\n"
                    st.session_state.uploaded_file_text = file_text
                    st.session_state.uploaded_image = None
                    st.success(f"✅ PDF '{uploaded_file.name}' uploaded! ({len(pdf_reader.pages)} pages)")
                    with st.expander("PDF Preview"): st.text(file_text[:500]+"..." if len(file_text)>500 else file_text)
                except Exception as e:
                    st.error(f"Could not read PDF: {e}. Try: pip install PyPDF2")
    st.divider()
    st.markdown("### 💬 Chat")
    if st.session_state.uploaded_image:
        st.info(f"🖼️ Image loaded: **{st.session_state.uploaded_image['name']}** - Ask anything about it!")
    elif st.session_state.uploaded_file_text:
        st.info("📄 File loaded - Ask anything about its content!")
    else:
        st.info("💬 Chat without uploading, or upload an image/file above for context!")
    for msg in st.session_state.vision_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    user_input = st.chat_input("Ask anything... (about image, file, or any question)")
    if user_input:
        st.session_state.vision_messages.append({"role":"user","content":user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    groq_key = get_groq_key()
                    if not groq_key:
                        st.error("❌ GROQ_API_KEY not found!")
                        st.stop()
                    from groq import Groq
                    client = Groq(api_key=groq_key)
                    messages = []
                    if st.session_state.uploaded_image:
                        system_msg = "You are a helpful Vision AI assistant. Analyze the provided image and answer questions about it clearly and in detail."
                    elif st.session_state.uploaded_file_text:
                        system_msg = f"You are a helpful AI assistant. The user uploaded a file with this content:\n\n{st.session_state.uploaded_file_text[:4000]}\n\nAnswer questions based on this content clearly."
                    else:
                        system_msg = "You are a helpful AI assistant like ChatGPT. Answer any questions clearly, helpfully, and in detail."
                    messages.append({"role": "system", "content": system_msg})
                    history = st.session_state.vision_messages[-6:]
                    for prev_msg in history:
                        if prev_msg["role"] == "user":
                            messages.append({"role": "user", "content": prev_msg["content"]})
                        else:
                            messages.append({"role": "assistant", "content": prev_msg["content"]})
                    if st.session_state.uploaded_image:
                        img_data = st.session_state.uploaded_image
                        messages[-1] = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:{img_data['media_type']};base64,{img_data['data']}"}}, {"type": "text", "text": user_input}]}
                        model = "meta-llama/llama-4-scout-17b-16e-instruct"
                    else:
                        model = "llama-3.3-70b-versatile"
                    response = client.chat.completions.create(model=model, messages=messages, max_tokens=1500)
                    answer = response.choices[0].message.content
                    st.markdown(answer)
                    st.session_state.vision_messages.append({"role":"assistant","content":answer})
                except Exception as e:
                    error_msg = str(e)
                    st.error(f"❌ Error: {error_msg}")
                    st.session_state.vision_messages.append({"role":"assistant","content":f"Error: {error_msg}"})

st.divider()
st.markdown("🌐 Making knowledge accessible to everyone, everywhere.")