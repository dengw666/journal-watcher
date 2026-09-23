import yaml
from pathlib import Path
_DIR = Path(__file__).parent.parent / "config"

def load_journals() -> dict:
    with open(_DIR / "journals.yaml", encoding='utf-8') as f: return yaml.safe_load(f)

def load_topics() -> dict:
    with open(_DIR / "topics.yaml", encoding='utf-8') as f: return yaml.safe_load(f)
