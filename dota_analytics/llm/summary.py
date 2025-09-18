import google.generativeai as genai
import json

from dota_analytics.config import settings

class LLMSummaryService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    async def generate_summary(self, stats_context: dict, style: str = "neutral", max_lines: int = 6) -> str:
        prompt_template = """
System:
You are a blunt, sarcastic Dota 2 analyst. Be brief (3–6 sentences), witty, and use gamer slang. Avoid hate speech and personal attacks; light profanity allowed. Output plain text only.

User:
Summarize the period below for our chat. Congratulate top performers, roast obvious feeders, and give 1 tip.
<context>
{context_json}
</context>
Style: {style}, 3–6 sentences, mention specific heroes/items if clear.
"""
        context_json = json.dumps(stats_context, indent=2)
        prompt = prompt_template.format(context_json=context_json, style=style)

        response = self.model.generate_content(prompt)
        return response.text
