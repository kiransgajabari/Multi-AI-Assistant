from dotenv import load_dotenv
load_dotenv()

from agents.planner import plan_research
from agents.summarizer import summarize
from agents.writer import write_report
from tools.search_tool import search_web

def run_research(topic: str):
    print(f"\n{'='*50}")
    print(f"🔍 Research Topic: {topic}")
    print(f"{'='*50}\n")

    print("📋 Step 1: Planning research queries...")
    queries = plan_research(topic)
    for i, q in enumerate(queries, 1):
        print(f"   Query {i}: {q}")

    summaries = []
    for i, query in enumerate(queries, 1):
        print(f"\n🌐 Step 2.{i}: Searching: {query}")
        results = search_web(query)
        print(f"📝 Summarizing results...")
        summary = summarize(results)
        summaries.append(summary)
        print(f"✅ Done!")

    print("\n✍️  Step 3: Writing final report...")
    report = write_report(topic, summaries)

    print("\n" + "="*50)
    print("📄 FINAL RESEARCH REPORT")
    print("="*50)
    print(report)
    print("="*50)

if __name__ == "__main__":
    topic = input("\nEnter your research topic: ")
    run_research(topic)