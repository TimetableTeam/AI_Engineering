from pathlib import Path
import json


ROOT = Path(__file__).resolve().parent.parent

OUTPUT_FILE = ROOT / "tanseek_solver_output.json"


def load_solver_output():
    if not OUTPUT_FILE.exists():
        raise FileNotFoundError(
            "tanseek_solver_output.json was not found. "
            "Run the Tanseek solver notebook first."
        )

    with open(
        OUTPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)