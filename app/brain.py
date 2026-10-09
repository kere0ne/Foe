"""Foe Brain — the built-in personal-assistant engine.

Foe Brain lets Foe work with ZERO setup: no Google login, no Ollama download,
no paid API keys. It provides:

- General knowledge answers (science, tech, geography, study help, how-tos)
- Utilities (calculator, unit converter, passwords, text tools, date/time...)
- Workspace actions (list/read/write/search files, notes & todos)
- Web research (search + read pages, when network is available)
- Command running (via the project's sandbox tool)
- Code templates and coding guidance

When the user later connects Ollama or a hosted model, Foe automatically
upgrades to the full LLM and Foe Brain steps aside (but its utilities and
actions stay available as tools).
"""
from __future__ import annotations

import ast
import base64
import binascii
import calendar
import datetime as _dt
import hashlib
import json as _json
import math
import random
import re
import secrets
import string
import uuid
from typing import Any, Awaitable, Callable
from urllib.parse import quote as _urlquote, unquote as _urlunquote

BRAIN_VERSION = "1.0"
BRAIN_MODEL_NAME = "foe-brain-1"

CAPABILITIES = [
    {"id": "chat", "title": "Answer questions", "detail": "General knowledge, explanations, study help, how-tos, ideas and advice."},
    {"id": "calculate", "title": "Calculate", "detail": "Math, percentages, unit conversions (length, weight, temperature, data) and date math."},
    {"id": "utilities", "title": "Utilities", "detail": "Passwords, UUIDs, hashes, base64, JSON formatting, word counts, coin flips, dice and more."},
    {"id": "write", "title": "Write things", "detail": "Emails, essays, stories, plans, resumes — plus ready-made code templates."},
    {"id": "files", "title": "Work with files", "detail": "List, read, create and search files in your private assistant workspace."},
    {"id": "notes", "title": "Notes & todos", "detail": "Keep notes and todo lists. Just say 'note ...', 'todo ...' or 'show my notes'."},
    {"id": "web", "title": "Web research", "detail": "Search the web and read pages, with source URLs cited."},
    {"id": "run", "title": "Run things", "detail": "Run project commands, scripts and tests in an isolated sandbox."},
    {"id": "code", "title": "Code help", "detail": "Explain code, fix errors, and generate starter projects in Python, JS, HTML and more."},
    {"id": "memory", "title": "Remember", "detail": "Save preferences and facts in Memory so Foe personalizes future answers."},
]

CAPABILITY_SUMMARY = (
    "I'm Foe, your personal AI assistant. Here's what I can do:\n\n"
    "• Answer questions — general knowledge, explanations, study help, ideas\n"
    "• Calculate — math, percentages, unit & currency-style conversions, date math\n"
    "• Utilities — passwords, UUIDs, hashes, base64, JSON, word counts, dice, coin flips\n"
    "• Write — emails, essays, stories, plans, plus code templates\n"
    "• Files — list, read, create and search files in my workspace\n"
    "• Notes & todos — say 'note ...', 'todo ...', 'show my notes / todos'\n"
    "• Web research — 'search the web for ...' and I'll read pages and cite sources\n"
    "• Run things — 'run ...' executes commands in a safe sandbox\n"
    "• Code help — explain code, debug errors, starter projects\n"
    "• Remember — save things in Memory and I'll use them later\n\n"
    "Try: 'calculate 15% of 240', 'convert 5 miles to km', 'make me a password', "
    "'search the web for ...', 'create a file hello.py', or just ask me anything."
)


# ---------------------------------------------------------------- utilities ---

_SAFE_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "sqrt": math.sqrt, "cbrt": (lambda x: x ** (1 / 3)),
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log10, "ln": math.log, "exp": math.exp,
    "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial,
    "gcd": math.gcd, "pow": pow,
    "pi": math.pi, "e": math.e, "tau": math.tau,
}


def safe_calculate(expr: str) -> float | int:
    """Evaluate a math expression safely (no eval of arbitrary code)."""
    cleaned = expr.strip().lower()
    cleaned = cleaned.replace("^", "**").replace("×", "*").replace("÷", "/").replace("π", "pi")
    cleaned = re.sub(r"\bmod\b", "%", cleaned)
    # percentages like "15% of 240" -> "(15/100)*240"
    cleaned = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1/100)*", cleaned)
    cleaned = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", cleaned)
    tree = ast.parse(cleaned, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
               ast.UAdd, ast.USub, ast.Constant, ast.Tuple, ast.List)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("Only numbers, +-*/%^, parentheses and math functions are supported.")
        if isinstance(node, ast.Name) and node.id not in _SAFE_FUNCS:
            raise ValueError(f"Unknown name: {node.id}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS):
            raise ValueError("That function is not supported.")
    result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, dict(_SAFE_FUNCS))  # noqa: S307 (AST-validated)
    if isinstance(result, (int, float)) and not isinstance(result, bool):
        return result
    raise ValueError("Expression did not produce a number.")


def _fmt_num(value: float | int) -> str:
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        text = f"{value:.6g}"
        return text
    return str(value)


_LENGTH_TO_M = {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "in": 0.0254,
                "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}
_WEIGHT_TO_KG = {"mg": 1e-6, "g": 0.001, "kg": 1.0, "oz": 0.028349523125, "lb": 0.45359237}
_DATA_TO_B = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
_VOLUME_TO_ML = {"ml": 1.0, "l": 1000.0, "tsp": 4.92892, "tbsp": 14.7868,
                 "floz": 29.5735, "cup": 236.588, "pt": 473.176, "qt": 946.353, "gal": 3785.41}
_TEMP_UNITS = {"c", "f", "k", "celsius", "fahrenheit", "kelvin"}


def convert_units(amount: float, from_unit: str, to_unit: str) -> float:
    fu, tu = from_unit.lower(), to_unit.lower()
    fu = {"millimeter": "mm", "millimeters": "mm", "centimeter": "cm", "centimeters": "cm",
          "meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km",
          "kilometers": "km", "kilometre": "km", "kilometres": "km", "inch": "in",
          "inches": "in", "foot": "ft", "feet": "ft", "yard": "yd", "yards": "yd",
          "mile": "mi", "miles": "mi"}.get(fu, fu)
    tu = {"millimeter": "mm", "millimeters": "mm", "centimeter": "cm", "centimeters": "cm",
          "meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km",
          "kilometers": "km", "kilometre": "km", "kilometres": "km", "inch": "in",
          "inches": "in", "foot": "ft", "feet": "ft", "yard": "yd", "yards": "yd",
          "mile": "mi", "miles": "mi"}.get(tu, tu)
    fu = {"gram": "g", "grams": "g", "kilogram": "kg", "kilograms": "kg", "ounce": "oz",
          "ounces": "oz", "pound": "lb", "pounds": "lb", "milligram": "mg", "milligrams": "mg"}.get(fu, fu)
    tu = {"gram": "g", "grams": "g", "kilogram": "kg", "kilograms": "kg", "ounce": "oz",
          "ounces": "oz", "pound": "lb", "pounds": "lb", "milligram": "mg", "milligrams": "mg"}.get(tu, tu)
    if fu in _TEMP_UNITS and tu in _TEMP_UNITS:
        f, t = fu[0], tu[0]
        c = amount if f == "c" else ((amount - 32) * 5 / 9 if f == "f" else amount - 273.15)
        if t == "c":
            return c
        if t == "f":
            return c * 9 / 5 + 32
        return c + 273.15
    for table in (_LENGTH_TO_M, _WEIGHT_TO_KG, _DATA_TO_B, _VOLUME_TO_ML):
        if fu in table and tu in table:
            return amount * table[fu] / table[tu]
    raise ValueError(f"Cannot convert {from_unit} to {to_unit}.")


def make_password(length: int = 16, memorable: bool = False) -> str:
    if memorable:
        words = ["ember", "harbor", "meadow", "puzzle", "rocket", "silent", "tiger",
                 "violet", "wander", "yellow", "zebra", "cobalt", "drift", "flint",
                 "grove", "helix", "ivory", "jungle", "karma", "lunar"]
        picked = "-".join(secrets.choice(words) for _ in range(3))
        return f"{picked}-{secrets.randbelow(90) + 10}"
    length = max(8, min(length, 64))
    alphabet = string.ascii_letters + string.digits + "!@#$%^*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_text(algorithm: str, text: str) -> str:
    algo = algorithm.lower().replace("-", "")
    if algo not in ("md5", "sha1", "sha256", "sha512"):
        raise ValueError("Supported hashes: md5, sha1, sha256, sha512.")
    return hashlib.new(algo, text.encode()).hexdigest()


# ------------------------------------------------------------- knowledge ---

# Each entry: (keywords_any, keywords_all, title, answer). Scored by matches.
KNOWLEDGE: list[tuple[list[str], list[str], str, str]] = [
    (["hello", "hi", "hey", "yo", "sup"], [], "greeting",
     "Hey! I'm Foe, your personal AI assistant. Ask me anything, tell me to calculate, "
     "convert, create files, take notes, search the web, or run commands. "
     "Type 'what can you do' to see everything."),
    (["what can you do", "help", "capabilities", "features", "commands"], [], "capabilities", CAPABILITY_SUMMARY),
    (["who are you", "your name", "about you", "what are you"], [], "about",
     "I'm Foe — your own personal AI assistant and software helper. I run as your private app: "
     "I can answer questions, calculate, write things, manage files and notes, research the web, "
     "and run commands in a safe sandbox. Connect Ollama or an API key any time to unlock an even smarter model."),
    (["thank", "thanks", "thx"], [], "thanks",
     "You're welcome! Anything else I can help with?"),
    (["bye", "goodbye", "good night", "see you"], [], "bye",
     "Goodbye! I'll be here whenever you need me."),
    (["joke", "funny", "make me laugh"], [], "joke",
     "Here's one for you:\n\nWhy do programmers prefer dark mode?\nBecause light attracts bugs.\n\nWant another? Just ask!"),
    (["fun fact", "interesting fact", "tell me something interesting"], [], "funfact",
     "Fun fact: Honey never spoils. Archaeologists have tasted 3,000-year-old honey from Egyptian tombs and found it perfectly edible!"),
    (["motivate", "motivated", "motivation", "motivating", "inspire", "inspired", "inspiring", "inspiration", "encourage", "encouragement", "sad", "stressed", "anxious", "depressed", "give up"], [], "motivation",
     "You've got this. One small step at a time is still progress — most big achievements are just small efforts repeated daily. "
     "If you're feeling overwhelmed, try: pick ONE tiny task, do it for 10 minutes, then rest. Momentum builds from there. 💪"),
    # --- science ---
    (["planet", "planets", "solar system", "mars", "jupiter", "saturn", "venus", "mercury", "neptune", "uranus"], [], "planets",
     "Our solar system has 8 planets, in order from the Sun:\n\n1. Mercury — smallest, closest to the Sun\n2. Venus — hottest planet (~465°C), thick CO2 atmosphere\n3. Earth — our home, the only known planet with life\n4. Mars — the red planet, target of exploration missions\n5. Jupiter — largest planet, a gas giant with the Great Red Spot storm\n6. Saturn — famous for its bright rings made of ice and rock\n7. Uranus — an ice giant that spins on its side\n8. Neptune — windiest planet, deep blue ice giant\n\nPluto is classified as a dwarf planet since 2006."),
    (["photosynthesis"], [], "photosynthesis",
     "Photosynthesis is how plants make food:\n\n6CO2 + 6H2O + sunlight → C6H12O6 + 6O2\n\nPlants take in carbon dioxide and water, capture sunlight with chlorophyll (the green pigment), "
     "and produce glucose (sugar) plus oxygen. It happens mainly in the leaves, inside chloroplasts."),
    (["gravity", "newton", "why do things fall"], [], "gravity",
     "Gravity is the force that pulls objects with mass toward each other. On Earth it gives everything weight and pulls at 9.8 m/s². "
     "Newton described it mathematically (F = G·m1·m2/r²), and Einstein later explained it as the bending of spacetime by mass. "
     "It's the weakest of the fundamental forces, yet it holds planets, stars and galaxies together."),
    (["speed of light", "how fast is light"], [], "lightspeed",
     "The speed of light in a vacuum is 299,792,458 meters per second (about 300,000 km/s or 186,000 miles/s). "
     "Nothing with mass can reach it. Sunlight takes about 8 minutes 20 seconds to reach Earth."),
    (["water", "h2o"], [], "water",
     "Water (H2O) facts:\n• Boils at 100°C / 212°F and freezes at 0°C / 32°F (at sea level)\n• Covers ~71% of Earth's surface; only ~2.5% is freshwater\n• The water cycle: evaporation → condensation → precipitation → collection\n• Adults are ~60% water; staying hydrated supports energy and focus"),
    (["atom", "atoms", "molecule", "molecules", "proton", "neutron", "electron", "periodic table"], [], "atoms",
     "Atoms are the building blocks of matter:\n• Protons (+) and neutrons (neutral) form the nucleus\n• Electrons (−) orbit in shells around it\n• The number of protons defines the element (e.g. 1 = hydrogen, 6 = carbon, 8 = oxygen)\n• Atoms bond into molecules — e.g. two hydrogen + one oxygen = water (H2O)"),
    (["dna", "gene", "genes", "genetics", "chromosome"], [], "dna",
     "DNA (deoxyribonucleic acid) is the instruction manual for life:\n• Shaped like a twisted ladder (double helix)\n• Built from 4 bases: A, T, C, G — their order spells out genes\n• Genes are sections of DNA that code for proteins\n• Humans share ~99.9% of DNA with each other, and ~60% with bananas!"),
    (["black hole"], [], "blackhole",
     "A black hole is a region where gravity is so strong that nothing — not even light — can escape. "
     "They form when massive stars collapse. The boundary is called the event horizon. "
     "The first photo of a black hole (M87*) was captured in 2019 by the Event Horizon Telescope."),
    (["evolution", "darwin", "natural selection"], [], "evolution",
     "Evolution by natural selection (Darwin, 1859): organisms with traits that help them survive tend to reproduce more, "
     "so those traits spread over generations. Given millions of years, this produces new species. "
     "Evidence includes fossils, DNA similarities, and observed adaptation (e.g. antibiotic resistance)."),
    (["climate", "global warming", "greenhouse"], [], "climate",
     "Climate change basics:\n• Greenhouse gases (CO2, methane) trap heat — necessary in balance, harmful in excess\n• Burning fossil fuels has raised CO2 ~50% since 1850, warming the planet ~1.2°C\n• Effects: sea-level rise, extreme weather, ecosystem shifts\n• Solutions: clean energy, efficiency, forests, and new technology"),
    # --- geography ---
    (["capital", "france", "paris"], ["france"], "france",
     "France — capital: Paris. Population ~68 million. Known for art, cuisine, fashion, and the Eiffel Tower (330m tall). "
     "Other major cities: Marseille, Lyon, Toulouse. Currency: euro."),
    (["capital", "capitals"], [], "capitals",
     "Some world capitals:\n• France — Paris • UK — London • USA — Washington, D.C. • Japan — Tokyo\n• Germany — Berlin • Italy — Rome • Spain — Madrid • Canada — Ottawa\n• Australia — Canberra • Brazil — Brasília • India — New Delhi • China — Beijing\n• Nigeria — Abuja • Egypt — Cairo • South Africa — Pretoria • Mexico — Mexico City\n\nAsk me about a specific country for more detail."),
    (["continent", "continents"], [], "continents",
     "The 7 continents (largest to smallest): Asia, Africa, North America, South America, Antarctica, Europe, Australia. "
     "Asia holds ~60% of all humans. Antarctica is the coldest, driest, windiest continent — and covered in ice."),
    (["ocean", "oceans", "sea", "seas", "pacific", "atlantic"], [], "oceans",
     "The 5 oceans (largest to smallest): Pacific, Atlantic, Indian, Southern, Arctic. "
     "The Pacific alone covers more area than all land combined. The deepest point is the Mariana Trench (~11,000m deep)."),
    (["tallest mountain", "mount everest", "highest mountain"], [], "everest",
     "Mount Everest (8,849m / 29,032ft) on the Nepal–China border is the tallest mountain above sea level. "
     "Mauna Kea in Hawaii is taller from base to peak (~10,200m) but mostly underwater."),
    (["longest river", "nile", "amazon river"], [], "rivers",
     "The Nile (~6,650 km) and the Amazon (~6,400 km) compete for 'world's longest river' depending on how you measure. "
     "The Amazon carries by far the most water — about 20% of all river water reaching the oceans."),
    # --- tech & coding ---
    (["python", "pip", "django", "flask"], [], "python-intro",
     "Python is a beginner-friendly programming language used for web apps, data science, AI, and automation.\n\n"
     "Your first program:\n```python\nprint(\"Hello, world!\")\n```\n\nKey basics:\n• Variables: `name = \"Foe\"`\n• Lists: `items = [1, 2, 3]`\n• Loops: `for x in items: print(x)`\n• Functions: `def greet(n): return f\"Hi {n}!\"`\n\nWant me to create a Python starter file? Say 'create a file hello.py'."),
    (["javascript", "js", "nodejs", "node.js"], [], "js-intro",
     "JavaScript runs in every web browser — it's the language of the web.\n\n```javascript\nconsole.log(\"Hello, world!\");\nconst greet = (name) => `Hi ${name}!`;\n```\n\nBasics: variables (`let`, `const`), functions, arrays, and DOM manipulation with `document.querySelector`. "
     "Say 'create a file app.js' and I'll make you a starter."),
    (["html", "css", "webpage", "website"], [], "html-intro",
     "HTML structures web pages. Minimal page:\n\n```html\n<!doctype html>\n<html>\n<head><meta charset=\"utf-8\"><title>My page</title></head>\n<body><h1>Hello!</h1></body>\n</html>\n```\n\nSay 'create a file index.html' and I'll build you a styled starter page."),
    (["git", "github", "commit", "push", "pull", "clone", "branch", "merge"], [], "git",
     "Essential Git commands:\n```\ngit clone <url>        # download a repo\ngit status             # what changed\ngit add .              # stage changes\ngit commit -m \"msg\"    # save snapshot\ngit push               # upload\ngit pull               # download updates\ngit checkout -b feat   # new branch\ngit log --oneline      # history\n```"),
    (["docker", "container", "containers", "dockerfile"], [], "docker",
     "Docker packages apps into portable containers.\n```\ndocker build -t myapp .   # build image\ndocker run -p 8000:8000 myapp\ndocker ps                 # running containers\ndocker compose up --build # multi-container app\n```\nFoe itself can run with Docker Compose — your sandbox commands also use containers."),
    (["sql", "mysql", "postgres", "database", "query"], [], "sql",
     "SQL queries databases:\n```sql\nSELECT name, email FROM users WHERE active = 1 ORDER BY name;\nINSERT INTO users (name, email) VALUES ('Ada', 'ada@x.dev');\nUPDATE users SET active = 0 WHERE id = 7;\nDELETE FROM users WHERE id = 7;\n```"),
    (["regex", "regexp", "regular expression"], [], "regex",
     "Regex quick reference:\n• `.` any char, `\\d` digit, `\\w` word char, `\\s` whitespace\n• `*` 0+, `+` 1+, `?` optional, `{2,4}` repeat\n• `^a` starts with a, `z$` ends with z\n• `[a-z]` range, `(a|b)` either\n• Example email-ish: `^[\\w.]+@[\\w.]+\\.\\w+$`"),
    (["http", "https", "api", "rest", "status code"], [], "http",
     "HTTP basics:\n• Methods: GET (read), POST (create), PUT (replace), PATCH (update), DELETE\n• Status codes: 200 OK, 201 Created, 400 bad request, 401 unauthorized, 404 not found, 500 server error\n• REST APIs exchange JSON over these methods — Foe's own backend is a REST API!"),
    (["linux", "terminal", "bash", "command line", "shell", "ubuntu"], [], "linux",
     "Handy terminal commands:\n```\nls -la        # list files\ncd folder     # change directory\npwd           # where am I\ncat file      # show file\nmkdir name    # make folder\nrm file       # delete (careful!)\ngrep -r \"x\" . # search text\nps aux        # processes\n```\nYou can run safe commands in Foe with 'run ...' — they execute in an isolated sandbox."),
    (["loop", "loops", "for loop", "while loop"], [], "loops",
     "Loops repeat actions:\nPython: `for i in range(5): print(i)`\nJavaScript: `for (let i = 0; i < 5; i++) console.log(i)`\nUse `for` when you know how many times, `while` when looping until a condition changes."),
    (["variable", "variables"], [], "variables",
     "A variable stores a value you can reuse: `score = 10` then `score + 5`. "
     "Think of it as a labeled box. Good names (`user_email`) beat cryptic ones (`x2`)."),
    (["function", "functions", "method", "methods"], [], "functions",
     "A function is a reusable block of code:\nPython:\n```python\ndef add(a, b):\n    return a + b\n```\nFunctions take inputs (parameters), do work, and optionally return a result. They keep code organized and DRY (Don't Repeat Yourself)."),
    (["bug", "debug", "error", "fix my code", "not working"], [], "debugging",
     "Debugging strategy:\n1. Read the FULL error message — file, line number, error type\n2. Reproduce it with the smallest possible example\n3. Print intermediate values (`print` / `console.log`) to find where reality diverges\n4. Check common culprits: typos, wrong types, off-by-one, missing await/return, stale cache\n5. Search the exact error text on the web\n\nPaste your error message and I'll help you reason through it!"),
    # --- math help ---
    (["percent", "percentage", "percentages"], [], "percent",
     "Percentages made easy:\n• x% of N = (x/100) × N → e.g. 15% of 240 = 0.15 × 240 = 36\n• Increase: N × (1 + x/100)\n• What % is A of B? (A/B) × 100\n\nJust tell me like 'calculate 15% of 240' and I'll do it instantly."),
    (["fraction", "fractions"], [], "fractions",
     "Fraction essentials:\n• Add/subtract: common denominator first (1/4 + 1/2 = 1/4 + 2/4 = 3/4)\n• Multiply: across (2/3 × 3/4 = 6/12 = 1/2)\n• Divide: flip the second and multiply\n• Decimal: divide top by bottom (3/4 = 0.75)"),
    (["algebra", "solve for x", "equation", "equations"], [], "algebra",
     "Solving equations: isolate x by doing the same operation to both sides.\nExample: 2x + 6 = 14 → subtract 6 → 2x = 8 → divide by 2 → x = 4.\nTell me an equation like 'solve 2x + 6 = 14' and I'll work it through."),
    (["area", "circle area", "triangle area", "circumference"], [], "area",
     "Area formulas:\n• Rectangle: length × width\n• Triangle: ½ × base × height\n• Circle: π × r²\n• Circumference: 2 × π × r"),
    (["average", "median"], [], "average",
     "Average = sum ÷ count. Example: (4 + 7 + 10) ÷ 3 = 7.\nMedian = the middle value when sorted. Mode = most frequent value.\nGive me numbers like 'average of 4, 7, 10' and I'll compute it."),
    # --- practical life ---
    (["recipe", "recipes", "cook", "cooking", "pasta", "rice", "bake", "baking"], [], "cooking",
     "Quick staples:\n• Pasta: boil salted water, cook 8–12 min (taste it!), save a cup of pasta water for sauce\n• Rice: 1 cup rice + 2 cups water, simmer covered ~18 min, rest 5 min\n• Eggs (boiled): 6½ min = jammy yolk, 9–10 min = firm\n\nWant a cooking conversion? Try 'convert 2 cups to ml'."),
    (["budget", "budgeting", "save money", "saving money", "personal finance"], [], "budget",
     "Simple budgeting (50/30/20 rule):\n• 50% needs (rent, food, bills)\n• 30% wants (fun, dining out)\n• 20% savings & debt payoff\nAutomate savings first ('pay yourself first'), track spending for one month, and kill subscriptions you forgot about. "
     "This is general education, not financial advice."),
    (["compound interest"], [], "compound",
     "Compound interest = earning returns on your returns. Rule of 72: years to double ≈ 72 ÷ interest rate. "
     "At 7% average returns, money doubles roughly every 10 years — which is why starting early matters so much."),
    (["sleep", "sleeping", "insomnia", "can't sleep", "cannot sleep", "tired", "exhausted"], [], "sleep",
     "Better sleep basics:\n• Consistent wake time (even weekends)\n• No screens 30–60 min before bed; dim lights\n• Cool, dark room; no caffeine after ~2pm\n• If awake >20 min, get up, do something calm, return when drowsy\nPersistent problems? Talk to a doctor — sleep matters a lot."),
    (["exercise", "workout", "fitness", "lose weight", "gym", "running"], [], "fitness",
     "Fitness starter (general info, not medical advice):\n• 150 min/week moderate activity (brisk walking counts!)\n• Strength train 2×/week (bodyweight is fine: squats, push-ups, planks)\n• Progress gradually; rest days are part of training\n• You can't out-train a bad diet — nutrition is half the battle"),
    (["headache", "cold", "flu", "fever", "sick", "illness", "symptoms"], [], "health-general",
     "I can share general wellness info, but I'm not a doctor:\n• Rest, fluids, and monitoring symptoms are the usual basics for minor bugs\n• Seek professional care for: high/persistent fever, breathing difficulty, severe pain, or anything that worries you\n• In an emergency, call your local emergency number immediately\n\nYour health deserves a real professional — tell me if you want help finding what to ask them."),
    # --- writing ---
    (["email", "e-mail"], [], "email-help",
     "Professional email template:\n\nSubject: [Clear topic]\n\nHi [Name],\n\n[1 line: context]. [2–3 lines: request or update, with specifics and dates].\n\n[1 line: what you need from them + by when].\n\nThanks,\n[Your name]\n\nTips: short subject, one topic per email, put the ask up front. Tell me the details and I'll draft it!"),
    (["resume", "resumes", "cv", "cover letter"], [], "resume",
     "Resume essentials:\n• 1 page, clean layout, no photo (US/UK norm)\n• Header: name, email, phone, location, links\n• Experience bullets: action verb + what + measurable result ('Cut load time 40% by...')\n• Skills section with real keywords\n• Tailor every application to the job post\nTell me your experience and I'll help draft bullets."),
    (["essay", "essays"], [], "essay",
     "Essay structure that works:\n1. Intro: hook + thesis (your one-sentence argument)\n2. Body: one idea per paragraph (claim → evidence → explanation)\n3. Conclusion: restate thesis in a new way + why it matters\nTell me your topic and thesis and I'll help outline it."),
    (["story", "write me a story"], [], "story",
     "Here's a tiny tale:\n\n*The lighthouse keeper wound the great lamp each dusk, though no ships had passed in years. "
     "One foggy night, a light answered from the sea — another keeper, still tending, still believing. "
     "Some lights aren't for guiding ships home. They're for reminding other lights they're not alone.*\n\nWant a longer story on a specific theme? Name it!"),
    # --- study ---
    (["study", "studying", "exam", "exams", "test prep"], [], "study",
     "Evidence-based study tips:\n• Active recall: close the book and test yourself\n• Spaced repetition: review after 1 day, 3 days, 1 week\n• Teach it to someone (or a rubber duck)\n• 25-min focused sprints (Pomodoro) with real breaks\n• Sleep! Memory consolidates overnight\nTell me your subject and I'll quiz you or explain topics."),
    (["learn"], ["language", "spanish", "french", "english", "german"], "language",
     "Language learning that works:\n• 15–30 min daily beats weekend marathons\n• Learn the 500 most common words first\n• Speak from day one (even badly!)\n• Use spaced-repetition flashcards\n• Consume media you enjoy in the language\nTell me which language and your level for a starter plan."),
    # --- foe usage ---
    (["ollama", "model", "llm", "smarter", "upgrade"], [], "upgrade",
     "Foe has two brains:\n• Built-in Foe Brain (me right now) — instant, private, offline-capable\n• Full LLM via Ollama or API keys — deeper reasoning, open-ended coding\n\nTo upgrade: run Foe with Docker Compose (includes Ollama), or set AI_PROVIDER + API key env vars. "
     "See the README 'Run Foe Engine locally' section. Either way, I'll keep helping meanwhile!"),
    (["github"], ["connect", "import", "repo", "use"], "github-help",
     "To use GitHub with Foe:\n1. Create a fine-grained personal access token on GitHub (grant only needed repo permissions)\n2. Click 'Connect GitHub' in the sidebar and paste it (it stays in your browser)\n3. Pick a repo to import into a project\n4. Ask me to explain, fix, or extend the code!"),
    (["memory", "remember me", "forget"], ["how", "use", "what"], "memory-help",
     "Memory makes me personal:\n• Open Workspace → Memory tab to save facts ('I prefer Python, concise answers')\n• I also auto-save useful facts from chats (toggle with FOE_AUTO_MEMORY)\n• I reread memories every chat to personalize answers\n• Delete any memory any time — they're private to your account"),
    (["bot", "discord"], ["run", "start", "create", "how"], "bot-help",
     "To run a Discord bot:\n1. Create a project with your bot's main.py\n2. Open Workspace → Terminal\n3. Fill the bot panel (name, entrypoint, runtime hours, Discord token)\n4. Hit 'Start bot' (needs the separate bot-runtime service configured)\nBots run up to 20 hours per launch. Ask me to write a starter discord bot!"),
]

# Code templates the brain can generate on demand.
CODE_TEMPLATES: dict[str, tuple[str, str]] = {
    "python hello": ("hello.py", 'print("Hello from Foe!")\n\n\ndef greet(name: str) -> str:\n    return f"Hello, {name}!"\n\n\nif __name__ == "__main__":\n    print(greet("world"))\n'),
    "python web": ("server.py", '"""Tiny web server — run: python server.py, open http://localhost:8000."""\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n\n\nclass Handler(BaseHTTPRequestHandler):\n    def do_GET(self):\n        body = b"<h1>Hello from Foe!</h1>"\n        self.send_response(200)\n        self.send_header("Content-Type", "text/html")\n        self.send_header("Content-Length", str(len(body)))\n        self.end_headers()\n        self.wfile.write(body)\n\n\nif __name__ == "__main__":\n    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()\n'),
    "html page": ("index.html", '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>My page</title>\n<style>\n  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }\n</style>\n</head>\n<body>\n<h1>Hello from Foe!</h1>\n<p>Edit this file to make it yours.</p>\n</body>\n</html>\n'),
    "js hello": ("app.js", 'console.log("Hello from Foe!");\n\nconst greet = (name) => `Hello, ${name}!`;\nconsole.log(greet("world"));\n'),
    "discord bot": ("main.py", '"""Minimal Discord bot. Set DISCORD_TOKEN env var, pip install discord.py, run: python main.py."""\nimport os\nimport discord\n\nintents = discord.Intents.default()\nintents.message_content = True\nclient = discord.Client(intents=intents)\n\n\n@client.event\nasync def on_ready():\n    print(f"Logged in as {client.user}")\n\n\n@client.event\nasync def on_message(message):\n    if message.author == client.user:\n        return\n    if message.content.lower().startswith("!hello"):\n        await message.channel.send("Hello from Foe!")\n\n\nclient.run(os.environ["DISCORD_TOKEN"])\n'),
}


def _word_hit(low: str, key: str) -> bool:
    """Whole-word/phrase match so 'sea' doesn't fire on 'search'."""
    return re.search(r"\b" + re.escape(key.strip()) + r"\b", low) is not None


def knowledge_lookup(text: str) -> str | None:
    """Find the best matching knowledge answer, or None."""
    low = text.lower()
    best: tuple[int, str] | None = None
    for keywords_any, keywords_all, _title, answer in KNOWLEDGE:
        if keywords_all and not any(_word_hit(low, k) for k in keywords_all):
            continue
        hits = [k for k in keywords_any if _word_hit(low, k)]
        if not hits:
            continue
        # Prefer longer, more specific matches.
        score = len(hits) * 10 + max(len(k) for k in hits)
        if best is None or score > best[0]:
            best = (score, answer)
    return best[1] if best else None


# ------------------------------------------------- intent parsing / tools ---

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

_RE_CALC = re.compile(r"(?:calculate|compute|eval|solve|math|what(?:'s| is))\s*[:\-]?\s*(.+)", re.I)
_RE_PURE_MATH = re.compile(r"^[\d\s+\-*/%^().,sqrtcossintanloglnepifactorialgcdabsroundfloorceil!×÷π%]+$", re.I)
_RE_CONVERT = re.compile(r"convert\s+(-?\d+(?:\.\d+)?)\s*([a-z°]+)\s+(?:to|in|into)\s+([a-z°]+)", re.I)
_RE_TEMP_SHORT = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*(celsius|fahrenheit|c|f)\s+(?:to|in|into)\s+°?\s*(celsius|fahrenheit|c|f)\b", re.I)
_RE_PASSWORD = re.compile(r"\b(password|passphrase)\b", re.I)
_RE_UUID = re.compile(r"\buuid\b", re.I)
_RE_HASH = re.compile(r"\b(md5|sha1|sha256|sha512)\s+(?:hash\s+)?(?:of\s+)?[\"']?(.+?)[\"']?$", re.I)
_RE_B64E = re.compile(r"base64\s+encode\s+[\"']?(.+?)[\"']?$", re.I)
_RE_B64D = re.compile(r"base64\s+decode\s+[\"']?(.+?)[\"']?$", re.I)
_RE_COUNT = re.compile(r"(?:count|how many)\s+(words|characters|chars|lines)(?:\s+in)?\s*[:\-]?\s*(.+)", re.I | re.S)
_RE_COIN = re.compile(r"\b(flip(\s+a)?\s+coin|coin\s+flip)\b", re.I)
_RE_DICE = re.compile(r"\broll\b.*\bdice\b|\bd(\d{1,3})\b", re.I)
_RE_RANDOM_NUM = re.compile(r"random\s+number(?:\s+between\s+(-?\d+)\s+and\s+(-?\d+))?", re.I)
_RE_PICK = re.compile(r"(?:pick|choose)(?:\s+one)?(?:\s+from)?\s*[:\-]?\s*(.+)", re.I)
_RE_JSON = re.compile(r"(?:format|validate|prettify)(?:\s+this)?\s+json\s*[:\-]?\s*(\{.*|\[.*)", re.I | re.S)
_RE_UPPER = re.compile(r"(uppercase|lowercase|titlecase|reverse)\s*[:\-]\s*(.+)", re.I | re.S)
_RE_WEBSEARCH = re.compile(r"(?:search(?:\s+the)?\s+web\s+for|google|look\s+up|research)\s*[:\-]?\s*(.+)", re.I)
_RE_FETCH = re.compile(r"(?:fetch|open|read|visit)\s+(https?://\S+)", re.I)
_RE_BARE_URL = re.compile(r"^(?:what(?:'s| is)(?:\s+on|\s+at)?\s+)?(https?://\S+)\s*\??$", re.I)
_RE_LIST_FILES = re.compile(r"\b(list|show|what)\b.*\bfiles?\b", re.I)
_RE_READ_FILE = re.compile(r"(?:read|open|show|cat|display)(?:\s+the)?(?:\s+file)?\s+[\"']?([\w\-./\\ ]+?\.\w+)[\"']?", re.I)
_RE_WRITE_FILE = re.compile(r"(?:create|write|make|save)(?:\s+a)?(?:\s+new)?\s+(?:file\s+)?[\"']?([\w\-./\\]+\.\w+)[\"']?\s*(?:with|:|containing|that says)?\s*(.*)", re.I | re.S)
_RE_SEARCH_FILES = re.compile(r"(?:search|find|grep)(?:\s+files?)?\s+for\s+[\"']?(.+?)[\"']?$", re.I)
_RE_RUN = re.compile(r"(?:run|execute)(?:\s+command)?\s*[:\-]?\s*(.+)", re.I)
_RE_NOTE = re.compile(r"^(?:note|remember|jot down)\s*[:\-]?\s*(.+)", re.I | re.S)
_RE_TODO_ADD = re.compile(r"^(?:todo|task|add todo|add task)\s*[:\-]?\s*(.+)", re.I | re.S)
_RE_TODO_DONE = re.compile(r"^(?:done|complete|finish)(?:\s+todo|\s+task)?\s*#?\s*(\d+)", re.I)
_RE_SHOW_NOTES = re.compile(r"\bshow\b.*\bnotes?\b", re.I)
_RE_SHOW_TODOS = re.compile(r"\bshow\b.*\btodos?\b|\blist\b.*\btodos?\b|my\s+tasks?\b", re.I)
_RE_EQUATION = re.compile(r"solve\s+(-?\d+(?:\.\d+)?)\s*x\s*([+-])\s*(-?\d+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)", re.I)
_RE_AVERAGE = re.compile(r"average\s+of\s+([\d\s,.\-]+)", re.I)
_RE_TEMPLATE = re.compile(r"(?:starter|template|boilerplate|example).*?(python|html|javascript|js|discord)|(?:python|html|javascript|js|discord).*?(starter|template|boilerplate|example)", re.I)


def _try_utility(text: str) -> str | None:
    """Handle deterministic utility requests. Returns answer or None."""
    stripped = text.strip()

    m = _RE_CONVERT.search(stripped) or _RE_TEMP_SHORT.search(stripped)
    if m and "convert" in stripped.lower() or _RE_TEMP_SHORT.search(stripped):
        m = _RE_CONVERT.search(stripped) or _RE_TEMP_SHORT.search(stripped)
        try:
            amount = float(m.group(1))
            result = convert_units(amount, m.group(2), m.group(3))
            return f"{_fmt_num(amount)} {m.group(2)} = {_fmt_num(result)} {m.group(3)}"
        except (ValueError, AttributeError, IndexError):
            return "I couldn't convert that. Try something like 'convert 5 miles to km' or 'convert 72 f to c'."

    m = _RE_EQUATION.search(stripped)
    if m:
        a, op, b, c = float(m.group(1)), m.group(2), float(m.group(3)), float(m.group(4))
        if a == 0:
            return "That equation has no variable term (0x) — nothing to solve."
        rhs = c - b if op == "+" else c + b
        x = rhs / a
        return f"{m.group(0).strip()} → x = {_fmt_num(x)}"

    m = _RE_AVERAGE.search(stripped)
    if m:
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
        if nums:
            return f"The average of {', '.join(_fmt_num(n) for n in nums)} is {_fmt_num(sum(nums) / len(nums))}."

    m = _RE_CALC.search(stripped)
    if m:
        expr = m.group(1).strip().rstrip("?")
        if expr and len(expr) < 200:
            try:
                return f"{expr} = {_fmt_num(safe_calculate(expr))}"
            except Exception:
                pass
    if _RE_PURE_MATH.match(stripped) and any(ch in stripped for ch in "+-*/%^") and len(stripped) < 120:
        try:
            return f"{stripped} = {_fmt_num(safe_calculate(stripped))}"
        except Exception:
            pass

    low = stripped.lower()
    if "time" in low and any(w in low for w in ["what", "current", "now", "clock"]) and len(stripped) < 60:
        now = _dt.datetime.now()
        return f"It's {now.strftime('%H:%M')} on {now.strftime('%A, %B %d, %Y')}."
    if ("date" in low or "today" in low or "day is" in low) and any(w in low for w in ["what", "today", "current"]) and len(stripped) < 60:
        now = _dt.datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}."
    m = re.search(r"days?\s+(?:between|from)\s+(\d{4}-\d{2}-\d{2})\s+(?:and|to)\s+(\d{4}-\d{2}-\d{2})", low)
    if m:
        d1 = _dt.date.fromisoformat(m.group(1))
        d2 = _dt.date.fromisoformat(m.group(2))
        return f"There are {abs((d2 - d1).days)} days between {d1} and {d2}."

    if _RE_COIN.search(stripped):
        return f"The coin lands on **{secrets.choice(['heads', 'tails'])}**."
    if _RE_DICE.search(stripped):
        m2 = re.search(r"\bd(\d{1,3})\b", low)
        sides = int(m2.group(1)) if m2 else 6
        sides = max(2, min(sides, 1000))
        m3 = re.search(r"(\d+)\s*d\d+", low)
        count = int(m3.group(1)) if m3 else 1
        count = max(1, min(count, 20))
        rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
        total = f" (total {sum(rolls)})" if count > 1 else ""
        return f"Rolled {count}d{sides}: {', '.join(map(str, rolls))}{total}."
    m = _RE_RANDOM_NUM.search(stripped)
    if m:
        lo, hi = (int(m.group(1)), int(m.group(2))) if m.group(1) else (1, 100)
        lo, hi = min(lo, hi), max(lo, hi)
        return f"Random number between {lo} and {hi}: **{secrets.randbelow(hi - lo + 1) + lo}**."
    m = _RE_PICK.search(stripped)
    if m and any(sep in m.group(1) for sep in [",", " or "]):
        options = [o.strip() for o in re.split(r",|\bor\b", m.group(1)) if o.strip()]
        if len(options) >= 2:
            return f"I pick: **{secrets.choice(options)}**"

    if _RE_PASSWORD.search(stripped) and any(w in low for w in ["make", "generate", "create", "new", "give"]):
        if "memorable" in low or "phrase" in low:
            return f"Here's a memorable password: `{make_password(memorable=True)}`"
        mlen = re.search(r"(\d+)\s*(?:char|length)", low)
        length = int(mlen.group(1)) if mlen else 16
        return f"Here's a strong password: `{make_password(length)}`\n\nStore it in a password manager — don't reuse it."
    if _RE_UUID.search(stripped):
        return f"Here's a UUID: `{uuid.uuid4()}`"
    m = _RE_HASH.search(stripped)
    if m:
        try:
            return f"{m.group(1).upper()}({m.group(2)}) = `{hash_text(m.group(1), m.group(2))}`"
        except ValueError as e:
            return str(e)
    m = _RE_B64E.search(stripped)
    if m:
        return f"Base64: `{base64.b64encode(m.group(1).encode()).decode()}`"
    m = _RE_B64D.search(stripped)
    if m:
        try:
            return f"Decoded: `{base64.b64decode(m.group(1).strip()).decode('utf-8')}`"
        except (binascii.Error, UnicodeDecodeError):
            return "That doesn't look like valid base64."
    m = re.search(r"url\s+encode\s+[\"']?(.+?)[\"']?$", stripped, re.I)
    if m:
        return f"URL-encoded: `{_urlquote(m.group(1))}`"
    m = re.search(r"url\s+decode\s+[\"']?(.+?)[\"']?$", stripped, re.I)
    if m:
        return f"URL-decoded: `{_urlunquote(m.group(1))}`"
    m = _RE_JSON.search(stripped)
    if m:
        try:
            parsed = _json.loads(m.group(1))
            return "Valid JSON, formatted:\n```json\n" + _json.dumps(parsed, indent=2)[:3000] + "\n```"
        except _json.JSONDecodeError as e:
            return f"That JSON is invalid: {e}"
    m = _RE_COUNT.search(stripped)
    if m:
        kind, content = m.group(1).lower(), m.group(2)
        if kind.startswith("word"):
            return f"That text has {len(content.split())} words."
        if kind.startswith("char"):
            return f"That text has {len(content)} characters."
        return f"That text has {len(content.splitlines())} lines."
    m = _RE_UPPER.search(stripped)
    if m:
        op, content = m.group(1).lower(), m.group(2)
        if op == "uppercase":
            return content.upper()
        if op == "lowercase":
            return content.lower()
        if op == "titlecase":
            return content.title()
        return content[::-1]
    return None


def _template_for(text: str) -> tuple[str, str] | None:
    low = text.lower()
    if "discord" in low:
        return CODE_TEMPLATES["discord bot"]
    if "html" in low:
        return CODE_TEMPLATES["html page"]
    if "javascript" in low or re.search(r"\bjs\b", low):
        return CODE_TEMPLATES["js hello"]
    if "python" in low or "flask" not in low and ("web server" in low or "server" in low):
        if "server" in low or "web" in low:
            return CODE_TEMPLATES["python web"]
        return CODE_TEMPLATES["python hello"]
    return None


async def brain_agent_run(prompt: str, tool: ToolExecutor, web_available: bool = True) -> dict[str, Any]:
    """Run an agentic turn without an LLM: parse intents, call tools, summarize."""
    steps: list[dict[str, Any]] = []
    notes: list[str] = []
    text = prompt.strip()

    async def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await tool(name, args)
        shown_args = {k: (str(v)[:200] + "…" if isinstance(v, str) and len(v) > 200 else v)
                      for k, v in args.items() if k != "content"}
        if "content" in args and isinstance(args["content"], str):
            shown_args["content_chars"] = len(args["content"])
        steps.append({"tool": name, "arguments": shown_args, "result": result})
        return result

    # 1. Fast path: pure utilities need no tools.
    utility = _try_utility(text)
    if utility:
        return {"provider": "foe-brain", "response": utility, "steps": steps}

    low = text.lower()

    # 2. Notes & todos (stored as workspace files).
    m = _RE_NOTE.match(text)
    if m:
        entry = m.group(1).strip()
        current = await call("read_file", {"path": "notes.md"})
        body = current.get("content", "") if isinstance(current, dict) else ""
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        updated = (body.rstrip() + "\n" if body else "# Notes\n\n") + f"- [{stamp}] {entry}\n"
        await call("write_file", {"path": "notes.md", "content": updated})
        return {"provider": "foe-brain", "response": f"Noted. I've saved it to notes.md:\n\n> {entry}", "steps": steps}
    m = _RE_TODO_ADD.match(text)
    if m:
        entry = m.group(1).strip()
        current = await call("read_file", {"path": "todo.md"})
        body = current.get("content", "") if isinstance(current, dict) else ""
        existing = re.findall(r"^- \[[ x]\]", body, re.M)
        updated = (body.rstrip() + "\n" if body else "# Todo\n\n") + f"- [ ] {entry}\n"
        await call("write_file", {"path": "todo.md", "content": updated})
        return {"provider": "foe-brain", "response": f"Added todo #{len(existing) + 1}: {entry}", "steps": steps}
    m = _RE_TODO_DONE.match(text)
    if m:
        current = await call("read_file", {"path": "todo.md"})
        body = current.get("content", "") if isinstance(current, dict) else ""
        lines = body.splitlines()
        idx = int(m.group(1)) - 1
        unchecked = [i for i, line in enumerate(lines) if line.startswith("- [ ]")]
        if 0 <= idx < len(unchecked):
            lines[unchecked[idx]] = lines[unchecked[idx]].replace("- [ ]", "- [x]", 1)
            await call("write_file", {"path": "todo.md", "content": "\n".join(lines) + "\n"})
            return {"provider": "foe-brain", "response": f"Todo #{idx + 1} marked done. Nice work!", "steps": steps}
        return {"provider": "foe-brain", "response": "I couldn't find that todo number. Say 'show my todos' to see the list.", "steps": steps}
    if _RE_SHOW_NOTES.search(text):
        current = await call("read_file", {"path": "notes.md"})
        body = (current.get("content") or "").strip() if isinstance(current, dict) else ""
        response = body if body else "No notes yet. Say 'note ...' to save one."
        return {"provider": "foe-brain", "response": response, "steps": steps}
    if _RE_SHOW_TODOS.search(text):
        current = await call("read_file", {"path": "todo.md"})
        body = (current.get("content") or "").strip() if isinstance(current, dict) else ""
        response = body if body else "No todos yet. Say 'todo ...' to add one."
        return {"provider": "foe-brain", "response": response, "steps": steps}

    # 3. Web research.
    m = _RE_WEBSEARCH.search(text)
    if m and web_available:
        query = m.group(1).strip().rstrip("?")[:300]
        result = await call("web_search", {"query": query})
        if result.get("error"):
            notes.append(f"Web search failed ({result['error']}). I answered from built-in knowledge instead.")
        else:
            results = result.get("results", [])
            if not results:
                notes.append("The web search returned no results, so I answered from built-in knowledge.")
            else:
                lines = ["Here's what I found on the web:"]
                for r in results[:5]:
                    lines.append(f"• {r.get('title', 'Untitled')} — {r.get('url')}")
                first_url = results[0].get("url")
                fetched = await call("fetch_url", {"url": first_url}) if first_url else {}
                if fetched.get("content"):
                    snippet = fetched["content"][:1200]
                    lines.append(f"\nFrom {first_url}:\n{snippet}")
                lines.append("\nSources: " + ", ".join(r.get("url", "") for r in results[:5]))
                knowledge = knowledge_lookup(query)
                if knowledge:
                    lines.append("\nFrom my own knowledge:\n" + knowledge)
                return {"provider": "foe-brain", "response": "\n".join(lines), "steps": steps}
    m = _RE_FETCH.search(text) or _RE_BARE_URL.search(text)
    if m:
        fetched = await call("fetch_url", {"url": m.group(1)})
        if fetched.get("error"):
            return {"provider": "foe-brain", "response": f"I couldn't read that page: {fetched['error']}", "steps": steps}
        content = (fetched.get("content") or "")[:2500]
        return {"provider": "foe-brain", "response": f"Here's what I found at {m.group(1)}:\n\n{content}", "steps": steps}

    # 4. File operations.
    did_file_action = False
    if _RE_LIST_FILES.search(text):
        result = await call("list_files", {})
        files = (result.get("files") or []) if isinstance(result, dict) else []
        if not files:
            notes.append("The workspace is empty right now.")
        else:
            listing = "\n".join(f"• {f['path']} ({f.get('size', 0)} bytes)" for f in files[:60])
            notes.append(f"Files in the workspace:\n{listing}")
        did_file_action = True
    m = _RE_SEARCH_FILES.search(text)
    if m:
        result = await call("search_files", {"query": m.group(1).strip()})
        matches = (result.get("matches") or []) if isinstance(result, dict) else []
        if not matches:
            notes.append(f"No matches for '{m.group(1).strip()}'.")
        else:
            lines = [f"• {h['path']}:{h['line']}: {h['text']}" for h in matches[:20]]
            notes.append("Matches:\n" + "\n".join(lines))
        did_file_action = True
    m = _RE_READ_FILE.search(text)
    if m and not _RE_WRITE_FILE.search(text):
        result = await call("read_file", {"path": m.group(1).strip()})
        if result.get("error"):
            notes.append(f"Couldn't read {m.group(1).strip()}: {result['error']}")
        else:
            content = result.get("content", "")
            notes.append(f"Contents of {m.group(1).strip()}:\n```\n{content[:4000]}\n```")
        did_file_action = True
    m = _RE_WRITE_FILE.search(text)
    if m:
        path, content = m.group(1).strip(), (m.group(2) or "").strip()
        if not content:
            template = _template_for(text + " " + path)
            if template:
                _, content = template
            elif path.endswith(".py"):
                content = CODE_TEMPLATES["python hello"][1]
            elif path.endswith(".html"):
                content = CODE_TEMPLATES["html page"][1]
            elif path.endswith(".js"):
                content = CODE_TEMPLATES["js hello"][1]
            else:
                content = ""
        if not content:
            notes.append(f"What should go in {path}? Tell me like: create a file notes.txt with: hello world")
        else:
            # Strip code fences if the user pasted a block.
            fence = re.search(r"```(?:\w+)?\n(.*?)```", content, re.S)
            if fence:
                content = fence.group(1)
            result = await call("write_file", {"path": path, "content": content})
            if result.get("error"):
                notes.append(f"Couldn't write {path}: {result['error']}")
            else:
                notes.append(f"Created {path} ({result.get('bytes', 0)} bytes).")
        did_file_action = True
    if _TEMPLATE_SHORTCUT.search(text) if (_TEMPLATE_SHORTCUT := _RE_TEMPLATE) else False:
        template = _template_for(text)
        if template and not did_file_action:
            fname, content = template
            await call("write_file", {"path": fname, "content": content})
            notes.append(f"Created {fname} with a starter template. Want changes? Just describe them.")
            did_file_action = True

    # 5. Run a command.
    m = _RE_RUN.search(text)
    if m:
        command = m.group(1).strip().strip("`")[:500]
        if command:
            result = await call("run_command", {"command": command})
            if result.get("error"):
                notes.append(f"Couldn't run that: {result['error']}")
            else:
                out = (result.get("stdout") or "")[-2000:]
                err = (result.get("stderr") or "")[-2000:]
                notes.append(f"Ran `{command}` (exit {result.get('exit_code')}):\n```\n{(out + chr(10) + err).strip() or '(no output)'}\n```")
            did_file_action = True

    if did_file_action and notes:
        return {"provider": "foe-brain", "response": "\n\n".join(notes), "steps": steps}

    # 6. Knowledge answer.
    knowledge = knowledge_lookup(text)
    if knowledge:
        extra = ("\n\n" + "\n".join(notes)) if notes else ""
        return {"provider": "foe-brain", "response": knowledge + extra, "steps": steps}

    # 7. Helpful fallback with concrete suggestions.
    fallback = (
        "I want to give you a great answer. Right now I'm running on my built-in brain, "
        "which is best at practical tasks. Here's what I can do for you immediately:\n\n"
        "• Calculate or convert: 'calculate 15% of 240', 'convert 5 miles to km'\n"
        "• Utilities: 'make me a password', 'uuid', 'sha256 hash of hello'\n"
        "• Files: 'list files', 'create a file hello.py', 'read notes.md'\n"
        "• Notes: 'note ...', 'todo ...', 'show my todos'\n"
        "• Web: 'search the web for ...'\n"
        "• Run: 'run python --version'\n"
        "• Knowledge: science, capitals, coding basics, study tips — ask away\n\n"
        "For deeper open-ended reasoning, connect Ollama or an API key and I'll upgrade automatically. "
        "What would you like to try?"
    )
    if notes:
        fallback = "\n\n".join(notes) + "\n\n" + fallback
    return {"provider": "foe-brain", "response": fallback, "steps": steps}


async def brain_chat_reply(user_text: str, memory_notes: list[str] | None = None) -> str:
    """Single-turn chat reply without tools (used by /api/chat fallback)."""
    utility = _try_utility(user_text)
    if utility:
        return utility
    knowledge = knowledge_lookup(user_text)
    if knowledge:
        suffix = ""
        if memory_notes:
            suffix = "\n\n(P.S. I kept your saved memories in mind.)"
        return knowledge + suffix
    # Light conversational handling so chat feels alive.
    low = user_text.lower()
    if len(user_text.split()) <= 4 and any(w in low for w in ["how are you", "how's it going", "how do you feel"]):
        return "I'm doing well, thanks for asking! Ready to help — ask me anything, or type 'what can you do' to see my skills."
    if "?" in user_text and len(user_text) < 200:
        return (
            "Good question! My built-in brain doesn't have a detailed answer for that one yet, but I can still help:\n\n"
            "• 'search the web for " + user_text.strip().rstrip("?")[:80] + "' — I'll research it and cite sources\n"
            "• Ask about science, geography, coding basics, math, or study topics\n"
            "• Or connect Ollama / an API key for deeper open-ended answers\n\n"
            "Want me to search the web for it?"
        )
    return (
        "Got it. For the best result, try one of these:\n\n"
        "• Ask a specific question ('what is photosynthesis?', 'capital of Japan?')\n"
        "• Give me a task ('calculate 12*8', 'make me a password', 'search the web for ...')\n"
        "• Type 'what can you do' for the full tour\n\n"
        "What shall we do first?"
    )
