import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from fpdf import FPDF
import io
import base64
import urllib.parse
import urllib.request
import json

load_dotenv()

from agents.planner import plan_research
from agents.summarizer import summarize
from agents.writer import write_report
from tools.search_tool import search_web

# ─── Page Config ───────────────────────────────────────
st.set_page_config(
    page_title="Multi-Agent Research Assistant",
    page_icon="🔬",
    layout="wide"
)

# ─── Initialize Session State ──────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "current_report" not in st.session_state:
    st.session_state.current_report = ""
if "current_topic" not in st.session_state:
    st.session_state.current_topic = ""
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "report_ready" not in st.session_state:
    st.session_state.report_ready = False

# ─── Dark Mode CSS ─────────────────────────────────────
def apply_theme(dark_mode):
    if dark_mode:
        st.markdown("""
        <style>
        .stApp {
            background-color: #0e1117;
            color: #fafafa;
        }
        .stTextInput > div > div > input {
            background-color: #1e2130;
            color: #fafafa;
            border: 1px solid #444;
        }
        .stExpander {
            background-color: #1e2130;
            border: 1px solid #333;
        }
        .metric-card {
            background-color: #1e2130 !important;
            border: 1px solid #333 !important;
        }
        .report-box {
            background-color: #1a1d2e !important;
            border: 1px solid #444 !important;
            color: #f0f0f0 !important;
        }
        .stButton > button {
            background-color: #262940;
            color: #fff;
            border: 1px solid #555;
        }
        .sidebar-card {
            background-color: #1e2130 !important;
            border: 1px solid #333 !important;
        }
        h1, h2, h3, h4 {
            color: #e0e0ff !important;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp {
            background-color: #f8f9ff;
        }
        .report-box {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            padding: 20px;
        }
        .metric-card {
            background-color: #ffffff;
            border: 1px solid #e8e8f0;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }
        </style>
        """, unsafe_allow_html=True)

apply_theme(st.session_state.dark_mode)

# ─── Sidebar ───────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/bot.png", width=80)
    st.title("Research Assistant")
    st.markdown("""
    👋 **Welcome!**

    Enter any topic and get a
    complete research report
    in seconds!
    """)
    st.divider()

    # ── FEATURE 9: Dark Mode Toggle ───────────────────
    st.markdown("**⚙️ Settings:**")
    dark_toggle = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dark_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_toggle
        st.rerun()

    st.divider()

    # ── FEATURE 12: History Search Bar ────────────────
    st.header("📚 Research History")
    history_search = st.text_input("🔎 Filter history:", placeholder="Search topics...")

    if st.session_state.history:
        filtered = [
            item for item in st.session_state.history
            if history_search.lower() in item['topic'].lower()
        ] if history_search else st.session_state.history

        if filtered:
            for item in reversed(filtered):
                with st.expander(f"📄 {item['topic'][:25]}..."):
                    st.write(f"⏰ Time: {item['time']}")
                    st.write(f"📝 Words: {item['words']}")
                    st.write(f"🌐 Language: {item.get('language', 'English')}")
                    st.write(f"📋 Template: {item.get('template', 'Standard Report')}")
                    st.write(item['report'][:200] + "...")
        else:
            st.info("No matching topics found.")
    else:
        st.info("No research history yet!")

# ─── Header ────────────────────────────────────────────
st.title("🤖 Multi-Agent Research Assistant")
st.markdown("*💡 The smartest way to research any topic in the world.*")
st.divider()

# ─── Topic Suggestions ─────────────────────────────────
st.markdown("### 💡 Quick Topic Suggestions:")

suggestions = [
    "Artificial Intelligence 2025",
    "Climate Change Solutions",
    "Blockchain Technology",
    "Space Exploration 2025",
    "Cybersecurity Trends",
    "Electric Vehicles Future",
    "Quantum Computing",
    "Renewable Energy"
]

selected_topic = ""
cols = st.columns(4)
for i, suggestion in enumerate(suggestions):
    if cols[i % 4].button(suggestion, key=f"sug_{i}"):
        selected_topic = suggestion

st.divider()

# ─── FEATURE 4: Topic Comparison Mode ─────────────────
st.markdown("### ⚙️ Research Options")
research_mode = st.radio(
    "Select Mode:",
    ["Single Topic", "Compare Two Topics"],
    horizontal=True
)

topic = ""
topic2 = ""

if research_mode == "Single Topic":
    topic = st.text_input(
        "🔍 Enter your topic:",
        value=selected_topic,
        placeholder="Example: Artificial Intelligence trends 2025"
    )
else:
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        topic = st.text_input("🔍 Topic 1:", placeholder="e.g. Python Programming")
    with col_t2:
        topic2 = st.text_input("🔍 Topic 2:", placeholder="e.g. JavaScript Programming")

st.divider()

# ─── FEATURE 6: Language Selector ─────────────────────
st.markdown("### 🌐 Report Language & Style")
lang_col, tmpl_col, depth_col = st.columns(3)

with lang_col:
    language = st.selectbox(
        "🌍 Output Language:",
        ["English", "Hindi", "Spanish", "French", "German", "Arabic", "Chinese", "Japanese"]
    )

# ─── FEATURE 7: Report Templates ──────────────────────
with tmpl_col:
    template = st.selectbox(
        "📋 Report Template:",
        ["Standard Report", "Academic Paper", "Blog Post", "Executive Summary", "News Article"]
    )

# ─── FEATURE 1: Research Depth Selector ───────────────
with depth_col:
    depth = st.selectbox(
        "🔬 Research Depth:",
        ["Quick (2 queries)", "Standard (3 queries)", "Deep (5 queries)"]
    )

depth_map = {
    "Quick (2 queries)": 2,
    "Standard (3 queries)": 3,
    "Deep (5 queries)": 5
}
max_queries = depth_map[depth]

st.divider()

col1, col2 = st.columns([1, 4])
with col1:
    run_btn = st.button("🚀 Start Research", type="primary")

# ─── FEATURE 3: PDF Generator (Formatted) ─────────────
def generate_pdf(topic, report, template="Standard Report", language="English"):
    from fpdf.enums import XPos, YPos
    NX, NY = XPos.LMARGIN, YPos.NEXT

    def clean(text):
        replacements = {
            "\u2022": "*", "\u2023": "*", "\u25cf": "*",
            "\u2018": "'", "\u2019": "'",
            "\u201c": '"', "\u201d": '"',
            "\u2013": "-", "\u2014": "--",
            "\u2026": "...", "\u2192": "->",
            "\u2713": "[OK]", "\u2714": "[OK]",
            "\u20ac": "EUR", "\u00a3": "GBP",
        }
        for char, rep in replacements.items():
            text = text.replace(char, rep)
        return text.encode("ascii", "replace").decode("ascii")

    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    pdf.set_fill_color(63, 81, 181)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", style="B", size=15)
    safe_title = clean(topic)[:80]
    pdf.cell(0, 9, safe_title, new_x=NX, new_y=NY, fill=True, align="C")
    pdf.ln(4)

    pdf.set_font("helvetica", size=9)
    pdf.set_text_color(120, 120, 120)
    meta = clean(
        f"Template: {template}  |  Language: {language}  |  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    pdf.cell(0, 6, meta, new_x=NX, new_y=NY)
    pdf.ln(2)
    pdf.set_draw_color(180, 190, 220)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(4)

    pdf.set_text_color(30, 30, 30)
    clean_report = clean(report)
    report_lines = [l for l in clean_report.split("\n") if not l.strip().startswith("<!--")]

    for line in report_lines:
        line = line.strip()
        if pdf.get_y() > 255:
            pdf.add_page()
            pdf.ln(5)
        if not line:
            pdf.ln(2)
            continue
        if line.startswith("# "):
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
            pdf.multi_cell(0, 6, "  * " + line[2:].strip(), new_x=NX, new_y=NY)
        elif line.startswith("**") and line.endswith("**") and len(line) > 4:
            pdf.set_font("helvetica", style="B", size=10)
            pdf.multi_cell(0, 6, line[2:-2].strip(), new_x=NX, new_y=NY)
        else:
            pdf.set_font("helvetica", size=10)
            pdf.multi_cell(0, 6, line, new_x=NX, new_y=NY)

    pdf.set_y(-18)
    pdf.set_font("helvetica", style="I", size=8)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 8, f"Research Report  |  {datetime.now().strftime('%Y-%m-%d')}", align="C")

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    return bytes(pdf_output)


# ─── FEATURE 8: Agent Activity Log ────────────────────
def show_agent_log(logs):
    with st.expander("🤖 Agent Activity Log", expanded=False):
        for log in logs:
            st.markdown(log)


# ─── NEW FEATURE: Images, Videos, Audio ───────────────
def show_media_tabs(topic):
    """Show Images, Videos, and Audio tabs related to the research topic."""
    st.divider()
    st.markdown("### 🎨 Media Resources")
    st.caption(f"Explore images, videos, and audio related to: **{topic}**")

    tab_img, tab_vid, tab_audio = st.tabs(["🖼️ Images", "🎬 Videos", "🎵 Audio"])

    encoded_topic = urllib.parse.quote(topic)

    # ── Images Tab ────────────────────────────────────
    with tab_img:
        st.markdown("#### 🖼️ Related Images")
        st.info("Click any link below to view images for your research topic.")

        image_sources = [
            {
                "name": "🔍 Google Images",
                "url": f"https://www.google.com/search?tbm=isch&q={encoded_topic}",
                "desc": "Search millions of images on Google"
            },
            {
                "name": "📸 Unsplash",
                "url": f"https://unsplash.com/s/photos/{encoded_topic}",
                "desc": "Free high-quality stock photos"
            },
            {
                "name": "🖼️ Wikimedia Commons",
                "url": f"https://commons.wikimedia.org/w/index.php?search={encoded_topic}",
                "desc": "Free media from Wikipedia"
            },
            {
                "name": "🎨 Flickr",
                "url": f"https://www.flickr.com/search/?text={encoded_topic}",
                "desc": "Creative commons images from Flickr"
            },
            {
                "name": "🖼️ Pexels",
                "url": f"https://www.pexels.com/search/{encoded_topic}/",
                "desc": "Free stock photos and images"
            },
            {
                "name": "🔬 NASA Images",
                "url": f"https://images.nasa.gov/#/?q={encoded_topic}",
                "desc": "NASA image library (great for science topics)"
            },
        ]

        cols = st.columns(2)
        for i, src in enumerate(image_sources):
            with cols[i % 2]:
                st.markdown(f"""
                <div style="border:1px solid #ddd; border-radius:10px; padding:12px; margin:6px 0;
                            background: {'#1e2130' if st.session_state.dark_mode else '#fff'};">
                    <a href="{src['url']}" target="_blank" style="font-size:16px; font-weight:bold;
                       text-decoration:none; color:#4f8ef7;">{src['name']}</a>
                    <p style="margin:4px 0 0 0; font-size:13px;
                       color:{'#aaa' if st.session_state.dark_mode else '#666'};">{src['desc']}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"🔗 **Quick Search:** [Google Images for '{topic}']"
                    f"(https://www.google.com/search?tbm=isch&q={encoded_topic})")

    # ── Videos Tab ────────────────────────────────────
    with tab_vid:
        st.markdown("#### 🎬 Related Videos")
        st.info("Click any link below to watch videos related to your research topic.")

        video_sources = [
            {
                "name": "▶️ YouTube",
                "url": f"https://www.youtube.com/results?search_query={encoded_topic}",
                "desc": "Search videos on YouTube"
            },
            {
                "name": "🎓 YouTube EDU",
                "url": f"https://www.youtube.com/results?search_query={encoded_topic}+explained+tutorial",
                "desc": "Educational & tutorial videos"
            },
            {
                "name": "📺 TED Talks",
                "url": f"https://www.ted.com/search?q={encoded_topic}",
                "desc": "Expert TED Talks on the topic"
            },
            {
                "name": "🎬 Vimeo",
                "url": f"https://vimeo.com/search?q={encoded_topic}",
                "desc": "High-quality videos on Vimeo"
            },
            {
                "name": "📰 Reuters Video",
                "url": f"https://www.reuters.com/search/news?blob={encoded_topic}",
                "desc": "News videos from Reuters"
            },
            {
                "name": "🌐 Dailymotion",
                "url": f"https://www.dailymotion.com/search/{encoded_topic}",
                "desc": "Videos from Dailymotion"
            },
        ]

        cols = st.columns(2)
        for i, src in enumerate(video_sources):
            with cols[i % 2]:
                st.markdown(f"""
                <div style="border:1px solid #ddd; border-radius:10px; padding:12px; margin:6px 0;
                            background: {'#1e2130' if st.session_state.dark_mode else '#fff'};">
                    <a href="{src['url']}" target="_blank" style="font-size:16px; font-weight:bold;
                       text-decoration:none; color:#e05252;">{src['name']}</a>
                    <p style="margin:4px 0 0 0; font-size:13px;
                       color:{'#aaa' if st.session_state.dark_mode else '#666'};">{src['desc']}</p>
                </div>
                """, unsafe_allow_html=True)

        # Embed YouTube search shortcut
        st.markdown("---")
        st.markdown("#### 🎥 Watch on YouTube")
        yt_embed_url = f"https://www.youtube.com/results?search_query={encoded_topic}"
        st.markdown(f"[▶️ Open YouTube search for **'{topic}'**]({yt_embed_url})", unsafe_allow_html=False)

    # ── Audio Tab ─────────────────────────────────────
    with tab_audio:
        st.markdown("#### 🎵 Related Audio & Podcasts")
        st.info("Click any link below to find audio content and podcasts on your research topic.")

        audio_sources = [
            {
                "name": "🎙️ Spotify Podcasts",
                "url": f"https://open.spotify.com/search/{encoded_topic}/podcasts",
                "desc": "Search podcasts on Spotify"
            },
            {
                "name": "🎧 Google Podcasts",
                "url": f"https://podcasts.google.com/search/{encoded_topic}",
                "desc": "Find podcasts on Google Podcasts"
            },
            {
                "name": "📻 BBC Sounds",
                "url": f"https://www.bbc.co.uk/sounds/search?q={encoded_topic}",
                "desc": "Audio & radio from BBC"
            },
            {
                "name": "🎤 Apple Podcasts",
                "url": f"https://podcasts.apple.com/search?term={encoded_topic}",
                "desc": "Search Apple Podcasts"
            },
            {
                "name": "📖 LibriVox",
                "url": f"https://librivox.org/search?q={encoded_topic}&search_form=advanced",
                "desc": "Free public domain audiobooks"
            },
            {
                "name": "🌐 Internet Archive Audio",
                "url": f"https://archive.org/search?query={encoded_topic}&and[]=mediatype%3A%22audio%22",
                "desc": "Free audio from Internet Archive"
            },
        ]

        cols = st.columns(2)
        for i, src in enumerate(audio_sources):
            with cols[i % 2]:
                st.markdown(f"""
                <div style="border:1px solid #ddd; border-radius:10px; padding:12px; margin:6px 0;
                            background: {'#1e2130' if st.session_state.dark_mode else '#fff'};">
                    <a href="{src['url']}" target="_blank" style="font-size:16px; font-weight:bold;
                       text-decoration:none; color:#1db954;">{src['name']}</a>
                    <p style="margin:4px 0 0 0; font-size:13px;
                       color:{'#aaa' if st.session_state.dark_mode else '#666'};">{src['desc']}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"🎙️ **Quick Access:** [Search Spotify Podcasts for '{topic}']"
                    f"(https://open.spotify.com/search/{encoded_topic}/podcasts)")


# ─── Helper: Run research for one topic ───────────────
def run_research(topic_input, language, template, max_queries):
    agent_logs = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1 - Planning
    status_text.text("📋 Planning research queries...")
    agent_logs.append("🧠 **Planner Agent** — Starting query generation...")
    with st.status("📋 Step 1: Planning research queries...", expanded=True) as status:
        queries = plan_research(topic_input)
        queries = queries[:max_queries]
        for i, q in enumerate(queries, 1):
            st.write(f"Query {i}: {q}")
            agent_logs.append(f"  ✅ Query {i}: {q}")
        status.update(label="✅ Queries planned!", state="complete")
    agent_logs.append("🧠 **Planner Agent** — ✅ Done!")
    progress_bar.progress(25)
    status_text.text("✅ Step 1 Complete!")

    # Step 2 - Search & Summarize
    summaries = []
    sources = []

    for i, query in enumerate(queries, 1):
        agent_logs.append(f"🔍 **Searcher Agent** — Searching: `{query}`")
        with st.status(f"🌐 Step 2.{i}: Searching: {query}", expanded=True) as status:
            results = search_web(query)

            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict) and r.get("url"):
                        sources.append({"title": r.get("title", query), "url": r["url"]})
            elif isinstance(results, dict) and results.get("results"):
                for r in results["results"]:
                    if r.get("url"):
                        sources.append({"title": r.get("title", query), "url": r["url"]})

            st.write("📝 Summarizing results...")
            agent_logs.append(f"📝 **Summarizer Agent** — Summarizing results for query {i}...")
            summary = summarize(results)
            summaries.append(summary)
            st.write(summary)
            status.update(label=f"✅ Search {i} complete!", state="complete")
        agent_logs.append(f"📝 **Summarizer Agent** — ✅ Done for query {i}!")
        progress_bar.progress(25 + (i * (50 // len(queries))))
        status_text.text(f"✅ Search {i} Complete!")

    # Step 3 - Write Report
    status_text.text("✍️ Writing final report...")
    agent_logs.append(f"✍️ **Writer Agent** — Writing {template} in {language}...")

    with st.status("✍️ Step 3: Writing final report...", expanded=True) as status:
        report = write_report(topic_input, summaries, language=language, template=template)
        status.update(label="✅ Report ready!", state="complete")

    agent_logs.append("✍️ **Writer Agent** — ✅ Report complete!")
    progress_bar.progress(100)
    status_text.text("✅ Research Complete!")

    return report, sources, agent_logs

# ─── Main Research Logic ───────────────────────────────
if run_btn and (topic or (research_mode == "Compare Two Topics" and topic and topic2)):

    if research_mode == "Single Topic":
        st.divider()
        report, sources, agent_logs = run_research(topic, language, template, max_queries)

        # ── FEATURE 8: Show Agent Log ──────────────────
        show_agent_log(agent_logs)

        # ── Show Report ────────────────────────────────
        st.divider()
        st.subheader("📄 Final Research Report")

        # ── FEATURE 10: Copy to Clipboard Button ───────
        col_report, col_copy = st.columns([5, 1])
        with col_copy:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            copy_js = f"""
            <textarea id='reportText' style='display:none'>{report}</textarea>
            <button onclick="navigator.clipboard.writeText(document.getElementById('reportText').value);
                this.innerText='✅ Copied!'; setTimeout(()=>this.innerText='📋 Copy',2000);"
                style="background:#4CAF50;color:white;border:none;padding:8px 14px;
                border-radius:8px;cursor:pointer;font-size:14px;margin-top:10px;">
                📋 Copy
            </button>
            """
            st.components.v1.html(copy_js, height=50)

        with col_report:
            st.markdown(report)

        # ── FEATURE 2: Source Citations ────────────────
        if sources:
            st.divider()
            st.markdown("### 🔗 Sources Used")
            for idx, src in enumerate(sources[:10], 1):
                st.markdown(f"{idx}. [{src['title']}]({src['url']})")

        # ── FEATURE 11: Share Report via Link ──────────
        st.divider()
        encoded = urllib.parse.quote(report[:500])
        share_url = f"https://your-app.streamlit.app/?report={encoded}"
        st.markdown("### 🔗 Share Report")
        st.text_input("Copy this link to share:", value=share_url, key="share_link")
        st.caption("ℹ️ Replace `your-app.streamlit.app` with your deployed app URL.")

        # ── Report Statistics ──────────────────────────
        st.divider()
        word_count = len(report.split())
        reading_time = max(1, round(word_count / 200))
        char_count = len(report)

        col1, col2, col3 = st.columns(3)
        col1.metric("📝 Word Count", word_count)
        col2.metric("⏱️ Reading Time", f"{reading_time} min")
        col3.metric("🔤 Characters", char_count)

        # ── Download Buttons ───────────────────────────
        st.divider()
        st.markdown("### ⬇️ Download Report")
        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                label="📝 Download as TXT",
                data=report,
                file_name=f"research_{topic[:30]}.txt",
                mime="text/plain"
            )
        with col2:
            pdf_data = generate_pdf(topic, report, template, language)
            st.download_button(
                label="📄 Download as PDF",
                data=pdf_data,
                file_name=f"research_{topic[:30]}.pdf",
                mime="application/pdf"
            )

        # ── NEW: Images, Videos, Audio Tabs ───────────
        show_media_tabs(topic)

        # ── Save to History ────────────────────────────
        st.session_state.history.append({
            "topic": topic,
            "report": report,
            "time": datetime.now().strftime("%H:%M:%S"),
            "words": word_count,
            "language": language,
            "template": template
        })

        # ── Store for Chat ─────────────────────────────
        st.session_state.current_report = report
        st.session_state.current_topic = topic
        st.session_state.report_ready = True
        st.session_state.chat_messages = []

    # ── FEATURE 4: Compare Two Topics ─────────────────
    else:
        st.divider()
        st.markdown("## 🔄 Topic Comparison")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown(f"### 📘 {topic}")
            report1, sources1, logs1 = run_research(topic, language, template, max_queries)
            st.markdown(report1)
            if sources1:
                st.markdown("**Sources:**")
                for s in sources1[:5]:
                    st.markdown(f"- [{s['title']}]({s['url']})")
            w1 = len(report1.split())
            st.metric("Words", w1)

        with col_right:
            st.markdown(f"### 📗 {topic2}")
            report2, sources2, logs2 = run_research(topic2, language, template, max_queries)
            st.markdown(report2)
            if sources2:
                st.markdown("**Sources:**")
                for s in sources2[:5]:
                    st.markdown(f"- [{s['title']}]({s['url']})")
            w2 = len(report2.split())
            st.metric("Words", w2)

        # Download both
        st.divider()
        st.markdown("### ⬇️ Download Comparison")
        combined = f"# TOPIC 1: {topic}\n\n{report1}\n\n---\n\n# TOPIC 2: {topic2}\n\n{report2}"
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button("📝 Download as TXT", data=combined,
                               file_name="comparison_report.txt", mime="text/plain")
        with col_dl2:
            pdf_data = generate_pdf(f"{topic} vs {topic2}", combined, template, language)
            st.download_button("📄 Download as PDF", data=pdf_data,
                               file_name="comparison_report.pdf", mime="application/pdf")

        # ── Media tabs for both topics ─────────────────
        st.divider()
        st.markdown("### 🎨 Media Resources")
        media_tab1, media_tab2 = st.tabs([f"🖼️ Media: {topic[:20]}", f"🖼️ Media: {topic2[:20]}"])
        with media_tab1:
            show_media_tabs(topic)
        with media_tab2:
            show_media_tabs(topic2)

elif run_btn:
    st.warning("⚠️ Please enter a research topic first!")

# ─── FEATURE 5: Chat with Report ──────────────────────
if st.session_state.report_ready and st.session_state.current_report:
    st.divider()
    st.markdown("### 💬 Chat with Your Report")
    st.caption(f"Ask questions about: **{st.session_state.current_topic}**")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_question = st.chat_input("Ask anything about the report...")

    if user_question:
        st.session_state.chat_messages.append({"role": "user", "content": user_question})
        with st.chat_message("user"):
            st.markdown(user_question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                from langchain_groq import ChatGroq
                from langchain_core.prompts import ChatPromptTemplate

                chat_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.5)
                chat_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant. The user has a research report and wants to ask questions about it.

REPORT:
{report}

USER QUESTION:
{question}

Answer the question based on the report content. Be concise and helpful.
""")
                chain = chat_prompt | chat_llm
                response = chain.invoke({
                    "report": st.session_state.current_report[:3000],
                    "question": user_question
                })
                answer = response.content
                st.markdown(answer)
                st.session_state.chat_messages.append({"role": "assistant", "content": answer})

# ─── Footer ────────────────────────────────────────────
st.divider()
st.markdown("🌍 Making knowledge accessible to everyone, everywhere.")