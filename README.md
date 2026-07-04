Multi-AI-Assistant — Multi-Agent Research Assistant

An AI-powered research assistant built with a 4-agent pipeline (Planner → Searcher → Summarizer → Writer) that turns any topic into a personalized, verified, multi-format research report.

Live demo: https://multi-ai-assistant.streamlit.app

<!-- Add a screenshot or demo GIF here once you have one -->
<!-- ![Demo](path/to/screenshot.png) -->

Overview

This project explores multi-agent orchestration for research and learning. Instead of a single LLM call, the app runs a coordinated pipeline of specialized agents, then layers personalization, gamification, and multi-modal output on top.

Tech Stack


Language / Framework: Python, Streamlit
LLM Orchestration: LangChain
LLM: Groq API (LLaMA 3.3 70B)
Web Search: Tavily Search API
Visualization: vis.js (Knowledge Mind Map)
Voice: Web Speech API (voice input)


Architecture
User Topic
   │
   ▼
Planner Agent   → breaks the topic into a research plan
   │
   ▼
Searcher Agent  → runs Tavily search, returns structured source list
   │
   ▼
Summarizer Agent → condenses sources into key points
   │
   ▼
Writer Agent    → produces the final report in chosen format/level
Features


Personalization — content adapts to Beginner / Intermediate / Advanced / Expert level
Multi-format Output — Simple, Detailed, Keywords, and Fun Fact tabs
Confidence Score — labels sources as Academic / Web / Official / Research / Encyclopedia
Quiz Generator — auto-generates 5 MCQs from any report
Knowledge Mind Map — interactive visual concept map (vis.js)
Agent Debate Mode — two agents argue FOR vs AGAINST a topic
Compare Two Topics — side-by-side research comparison
Chat with Report — ask follow-up questions on a generated report
Vision AI Chat — upload an image or file and chat about it (LLaMA Vision)
Voice Input — mic button for hands-free topic entry
Gamification — points, badges, and streak tracking
Dashboard — history, saved reports, progress tracking, recommendations
Analytics — timeline view, level progression, badge collection
Multi-language Support — English, Hindi, Kannada, Tamil, Telugu, and more
PDF Export — download reports, or notes + quiz together
Dark Mode
Media Resources — related Images / Videos / Audio links per topic

Setup / Run Locally

# Clone the repo
git clone https://github.com/kiransgajabari/Multi-AI-Assistant.git
cd Multi-AI-Assistant

# Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Add your API keys
# Create a .env file in the root folder with:
# GROQ_API_KEY=your_groq_key_here
# TAVILY_API_KEY=your_tavily_key_here

# Run the app
streamlit run app.py
Security Note

API keys are managed via .env locally and Streamlit Secrets in production — never committed to the repository.

Project Status

Actively developed. Built solo as a self-directed learning project exploring RAG, multi-agent systems, and applied LLM engineering.

Author

Kiran S Gajabari
Final-year ECE, SGBIT Belagavi
GitHub