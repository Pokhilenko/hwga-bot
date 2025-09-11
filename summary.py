import os
import google.generativeai as genai

async def generate_summary(match_details):
    """Generate a summary of a Dota 2 match."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API key not found. Cannot generate summary."

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')

    prompt = f"""
    Generate a short, narrative summary of a Dota 2 match with the following details:
    {match_details}
    """

    response = await model.generate_content_async(prompt)
    return response.text
