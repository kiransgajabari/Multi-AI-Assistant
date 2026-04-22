from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("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")
)

def summarize(content: str) -> str:
    prompt = ChatPromptTemplate.from_template(
        "Summarize this research content in 3-5 clear key points:\n{content}"
    )
    chain = prompt | llm
    return chain.invoke({"content": content}).content