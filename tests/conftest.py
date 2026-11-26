import os
import sys
from pathlib import Path

os.environ["FORGEAI_LLM_CACHE"] = "0"   # tests never read or write the LLM cache
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
