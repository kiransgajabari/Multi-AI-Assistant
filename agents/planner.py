from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("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")
)

def plan_research(topic: str) -> list:
    prompt = ChatPromptTemplate.from_template(
        "You are a research planner. Break this topic into exactly 3 specific search queries.\n"
        "Return ONLY the 3 queries, one per line, no numbering, no extra text.\n"
        "Topic: {topic}"
    )
    chain = prompt | llm
    result = chain.invoke({"topic": topic})
    queries = result.content.strip().split("\n")
    return [q.strip() for q in queries if q.strip()][:3]