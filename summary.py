import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

async def generate_summary(match_details):
    """Generate a summary of a Dota 2 match."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "No GEMINI api key found or it's corrupted, skipping games summary expanation..."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')

        prompt = f"""
        Generate a short, narrative summary of a Dota 2 match with the following details:
        {match_details}
        """

        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error generating summary with Gemini: {e}")
        return "No GEMINI api key found or it's corrupted, skipping games summary expanation..."
