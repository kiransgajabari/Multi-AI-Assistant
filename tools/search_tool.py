from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

client = TavilyClient(api_key=os.getenv("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"))

def search_web(query: str) -> str:
    results = client.search(query=query, max_results=3)
    output = ""
    for r in results["results"]:
        output += f"\nTitle: {r['title']}\nURL: {r['url']}\nContent: {r['content']}\n"
    return output