from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7)

def write_report(topic: str, summaries: list, language: str = "English", template: str = "Standard Report") -> str:
    """
    Write a final research report using the given summaries.
    Supports multiple languages and report templates.
    """

    combined = "\n\n".join(summaries)

    # ── Template-specific instructions ──────────────────
    template_instructions = {
        "Standard Report": "Write a well-structured research report with Introduction, Key Findings, Analysis, and Conclusion sections.",
        "Academic Paper": "Write in academic style with Abstract, Introduction, Literature Review, Analysis, Discussion, and Conclusion. Use formal academic language and cite findings properly.",
        "Blog Post": "Write in an engaging, conversational blog post style. Use catchy headings, short paragraphs, and make it easy and fun to read for a general audience.",
        "Executive Summary": "Write a concise executive summary (max 400 words). Focus only on key findings, business implications, and actionable recommendations. Use bullet points.",
        "News Article": "Write as a professional news article. Start with a strong headline and lead paragraph answering who/what/when/where/why. Use inverted pyramid structure.",
    }

    style_instruction = template_instructions.get(template, template_instructions["Standard Report"])

    # ── Language instruction ─────────────────────────────
    if language == "English":
        language_instruction = "Write the entire report in English."
    else:
        language_instruction = f"IMPORTANT: Write the ENTIRE report in {language} language only. Every single word including headings, sections, and content must be in {language}. Do NOT use English at all."

    prompt = ChatPromptTemplate.from_template("""
You are an expert research writer. Your task is to write a complete, high-quality research report.

TOPIC: {topic}

RESEARCH DATA:
{summaries}

TEMPLATE STYLE: {style_instruction}

LANGUAGE REQUIREMENT: {language_instruction}

INSTRUCTIONS:
- Follow the template style exactly
- Follow the language requirement strictly
- Use markdown formatting (# for title, ## for sections, **bold** for key terms)
- Make it comprehensive, well-organized, and informative
- Do NOT include any HTML comments or meta-instructions in the output
- Write ONLY the report content, nothing else

Now write the complete report:
""")

    chain = prompt | llm
    response = chain.invoke({
        "topic": topic,
        "summaries": combined,
        "style_instruction": style_instruction,
        "language_instruction": language_instruction,
    })

    return response.content