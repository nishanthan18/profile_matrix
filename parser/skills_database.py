"""
Master skills/keyword database used for:
  - detecting which stack/skill a work-experience or project entry belongs to
  - highlighting keywords found in a resume
  - scoring candidates during shortlisting

Add / remove keywords freely -- everything else in the app reads from this file.
"""

SKILLS_DB = {
    "Programming Languages": [
        "python", "java", "c++", "c#", "c", "javascript", "typescript", "go", "golang",
        "rust", "kotlin", "swift", "php", "ruby", "scala", "r", "matlab", "perl", "dart"
    ],
    "Web / Frontend": [
        "html", "css", "react", "reactjs", "react.js", "angular", "vue", "vue.js",
        "next.js", "nextjs", "redux", "bootstrap", "tailwind", "jquery", "sass", "webpack"
    ],
    "Backend / Frameworks": [
        "django", "flask", "fastapi", "node.js", "nodejs", "express", "express.js",
        "spring", "spring boot", "asp.net", ".net", "laravel", "streamlit"
    ],
    "Databases": [
        "sql", "mysql", "postgresql", "postgres", "mongodb", "sqlite", "oracle",
        "redis", "cassandra", "supabase", "firebase", "dynamodb", "elasticsearch", "nosql"
    ],
    "Cloud / DevOps": [
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "jenkins",
        "terraform", "ansible", "ci/cd", "git", "github", "gitlab", "linux", "nginx",
        "cloudformation", "github actions"
    ],
    "Data Science / ML / AI": [
        "machine learning", "deep learning", "nlp", "natural language processing",
        "computer vision", "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
        "pandas", "numpy", "opencv", "llm", "large language model", "generative ai",
        "genai", "data science", "data analysis", "artificial intelligence",
        "neural network", "transformers", "huggingface", "langchain", "groq", "gemini",
        "openai", "rag", "prompt engineering"
    ],
    "Mobile": [
        "android", "ios", "flutter", "react native", "kotlin", "swift"
    ],
    "Tools / Other": [
        "jira", "figma", "postman", "vs code", "excel", "power bi", "tableau",
        "rest api", "graphql", "microservices", "agile", "scrum", "oauth",
        "oauth 2.0", "unit testing", "pytest", "junit"
    ],
}

# Flat lookup: keyword -> category, sorted by length (longest first) so multi-word
# keywords ("machine learning") are matched before their substrings ("learning" isn't
# a keyword here, but this ordering matters generally).
ALL_SKILLS_FLAT = []
for _category, _kws in SKILLS_DB.items():
    for _kw in _kws:
        ALL_SKILLS_FLAT.append((_kw.lower(), _category))

ALL_SKILLS_FLAT.sort(key=lambda x: len(x[0]), reverse=True)


def find_skills_in_text(text: str):
    """Return a sorted list of unique skill keywords found in `text`."""
    if not text:
        return []
    text_low = text.lower()
    found = set()
    for kw, _cat in ALL_SKILLS_FLAT:
        # word-boundary-ish match; skills with symbols (c++, .net) handled via plain `in`
        if any(ch in kw for ch in "+#."):
            if kw in text_low:
                found.add(kw)
        else:
            import re
            if re.search(r"(?<![a-zA-Z0-9])" + re.escape(kw) + r"(?![a-zA-Z0-9])", text_low):
                found.add(kw)
    return sorted(found)


def skill_category(skill: str) -> str:
    for kw, cat in ALL_SKILLS_FLAT:
        if kw == skill.lower():
            return cat
    return "Other"