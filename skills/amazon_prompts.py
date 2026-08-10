"""
Prompt templates for the Amazon research skill.

PROJ-171 — Sprint 2.

These prompts produce concise, consistent summaries from Claude when given
structured Amazon product data. They are designed to be filled in via the
`format_prompt()` helper using keyword arguments matching the placeholders.
"""


SEARCH_PROMPT = """You are an Amazon product research assistant. The user searched for: "{query}".

Below are the top results returned from Amazon:

{results}

Write a clear, helpful summary of these products for the user. Highlight the
standout options, note any patterns in price or rating, and call out anything
the user should be cautious about (e.g. low review counts, suspiciously cheap
listings).

Keep your response under 150 words.
"""


COMPARE_PROMPT = """You are an Amazon product research assistant. The user wants a side-by-side comparison of the following products:

{products}

Compare them across price, rating, review count, and key features. Be concrete
about trade-offs — say which product wins on which dimension rather than
hedging. End with a one-line summary of who each product is best for.

Keep your response under 150 words.
"""


RECOMMEND_PROMPT = """You are an Amazon product research assistant. The user has a budget of {budget} and is choosing between the following products:

{products}

Recommend the single best pick for their budget. Justify the choice in 2-3
sentences using price, rating, and feature fit. If nothing fits the budget
well, say so honestly and suggest the closest reasonable option.

Keep your response under 150 words.
"""


def format_prompt(template: str, **kwargs) -> str:
    """
    Fill a prompt template with the given keyword arguments.

    Args:
        template: One of SEARCH_PROMPT, COMPARE_PROMPT, RECOMMEND_PROMPT.
        **kwargs: Values for the template's placeholders. Must include all
            placeholders required by the template (e.g. `query` and `results`
            for SEARCH_PROMPT).

    Returns:
        The formatted prompt string with all placeholders filled in.

    Raises:
        KeyError: If a required placeholder is missing from kwargs.
    """
    return template.format(**kwargs)