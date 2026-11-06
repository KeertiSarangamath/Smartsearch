import json
import logging
import re
import google.generativeai as genai
from config import Config

# Configure Google Gemini API key if present in configuration
if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)


def generate_paper(topic, sources, paper_length='medium', citation_style='IEEE'):
    """
    Generates a structured research paper using Google Gemini API based on topic and sources.
    
    Returns a Python dictionary with keys for each section:
    Title, Abstract, Keywords, Introduction, Literature Review, Methodology, Results, Discussion, Conclusion.
    """
    # Map paper length setting to target total word counts
    word_count_map = {
        'short': 800,
        'medium': 1500,
        'long': 2500
    }
    target_words = word_count_map.get(paper_length, 1500)

    # Format source academic papers into context text for Gemini
    source_context = ""
    for idx, src in enumerate(sources, 1):
        source_context += f"Source [{idx}]:\n"
        source_context += f"- Title: {src.get('title')}\n"
        source_context += f"- Authors: {src.get('authors')}\n"
        source_context += f"- Year: {src.get('year')}\n"
        source_context += f"- Abstract: {src.get('abstract')}\n"
        source_context += f"- Link: {src.get('url')}\n\n"

    # Define citation formatting instruction
    if citation_style.upper() == 'IEEE':
        citation_instruction = "Use IEEE style numbered inline citations like [1], [2] referencing the source indices."
    else:
        citation_instruction = "Use APA style inline citations like (Author, Year) based on the provided sources."

    # Construct complete prompt for Gemini AI
    prompt = f"""
You are an expert academic researcher writing a peer-reviewed research paper.

RESEARCH TOPIC: {topic}
TARGET TOTAL WORD COUNT: ~{target_words} words
CITATION STYLE: {citation_style} ({citation_instruction})

ACADEMIC SOURCES CONTEXT:
{source_context}

INSTRUCTIONS:
1. Synthesize a comprehensive, high-quality research paper on the topic using ONLY the provided sources.
2. Identify existing research gaps in the literature review.
3. Write clear, academic sections: Title, Abstract, Keywords, Introduction, Literature Review, Methodology, Results, Discussion, Conclusion.
4. Output MUST be valid JSON only, without additional conversational text. 

JSON FORMAT REQUIRED:
{{
  "Title": "Paper title here",
  "Abstract": "Abstract paragraph here...",
  "Keywords": "Keyword 1, Keyword 2, Keyword 3...",
  "Introduction": "Introduction text...",
  "Literature Review": "Literature review text with citations...",
  "Methodology": "Methodology text...",
  "Results": "Results text...",
  "Discussion": "Discussion text...",
  "Conclusion": "Conclusion text..."
}}
"""

    sections = {}

    try:
        # Use gemini-3.8-flash model for fast and accurate research synthesis
        model = genai.GenerativeModel("gemini-3.8-flash")
        response = model.generate_content(prompt)
        
        response_text = response.text.strip()

        # Remove markdown code block fences if present (```json ... ```)
        cleaned_json = re.sub(r'^```json\s*|\s*```$', '', response_text, flags=re.MULTILINE).strip()

        # Parse JSON output into a Python dictionary
        sections = json.loads(cleaned_json, strict=False)
        logging.debug(f"[GEMINI API] Successfully generated {len(sections)} paper sections for topic: '{topic}'")
        return sections

    except Exception as e:
        logging.error(f"[GEMINI API ERROR] Generation failed: {str(e)}", exc_info=True)
        raise


def regenerate_section(topic, section_name, current_content, instruction, sources, citation_style='IEEE'):
    """
    Regenerates a single specific section of a paper based on user instructions and source context.
    Returns updated plain text for that section.
    """
    # Format sources list
    source_context = ""
    for idx, src in enumerate(sources, 1):
        source_context += f"Source [{idx}]: {src.get('title')} ({src.get('year')}) - {src.get('authors')}\n"

    prompt = f"""
You are an academic research editor refining a specific section of a research paper.

TOPIC: {topic}
SECTION TO REWRITE: {section_name}
CURRENT CONTENT:
{current_content}

USER REGENERATION INSTRUCTION: {instruction}
CITATION STYLE: {citation_style}

AVAILABLE SOURCES:
{source_context}

INSTRUCTIONS:
Rewrite and improve ONLY the "{section_name}" section according to the user instruction while maintaining academic tone and proper citations. Return ONLY the updated section text directly, without introductory phrases or titles.
"""

    try:
        model = genai.GenerativeModel("gemini-3.8-flash")
        response = model.generate_content(prompt)
        updated_text = response.text.strip()
        if not updated_text:
            raise Exception("Gemini API returned empty response text.")
        logging.debug(f"[GEMINI API] Successfully regenerated section '{section_name}'")
        return updated_text
    except Exception as e:
        logging.error(f"[GEMINI API ERROR] Section regeneration failed: {str(e)}", exc_info=True)
        raise

