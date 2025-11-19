"""
Prompt templates for the question decomposition agent
"""

DECOMPOSITION_PROMPT = """You are a research assistant that breaks down complex questions into simpler sub-questions.

Your task: Analyze the following research question and decompose it into atomic sub-questions.

Guidelines:
1. Each sub-question should be answerable from a SINGLE research paper
2. Identify which specific paper is needed (if obvious from the question)
3. Make questions specific and focused
4. Don't create sub-questions for general knowledge
5. Number of sub-questions should match complexity (typically 2-4)

Original Question: {query}

Respond with a JSON array ONLY (no other text):
[
    {{
        "question": "What training method does BERT use?",
        "paper_needed": "BERT"
    }},
    {{
        "question": "What datasets does GPT-2 train on?",
        "paper_needed": "GPT-2"
    }}
]

JSON Response:"""


SYNTHESIS_PROMPT = """You are a research assistant that synthesizes information from multiple papers.

Original Question: {original_query}

I have gathered the following information from research papers:

{sub_answers}

Your task: Create a comprehensive, coherent answer to the original question by:
1. Comparing and contrasting findings where relevant
2. Highlighting key differences and similarities
3. Being concise but complete
4. Citing sources using [Paper Name] notation
5. Organizing information logically

Synthesized Answer:"""


PAPER_RANKING_PROMPT = """You are a research assistant helping to find the most relevant paper.

Question to answer: {question}

Available papers:
{papers_list}

Which paper is MOST relevant for answering this question?
Respond with ONLY the paper number (e.g., "1" or "2" or "3").

Paper number:"""


SEARCH_TERM_EXTRACTION_PROMPT = """Extract the key search terms from this research question.

Question: {question}

Return 2-4 key terms that would be good for searching academic papers.
Format as comma-separated values.

Search terms:"""
