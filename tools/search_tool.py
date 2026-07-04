from tavily import TavilyClient
import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()
load_dotenv(dotenv_path=".vscode/.env")

# Works both locally and on Streamlit Cloud
try:
    api_key = st.secrets["TAVILY_API_KEY"]
except:
    api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise RuntimeError("TAVILY_API_KEY not found. Please set it in your .env file or Streamlit secrets.")

client = TavilyClient(api_key=api_key)

def search_web(query: str):
    results = client.search(query=query, max_results=3)
    output = []
    for r in results["results"]:
        output.append({
            "title": r["title"],
            "url": r["url"],
            "content": r["content"]
        })
    return output
