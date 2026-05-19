import re

with open("discography_webapp/main.py", "r") as f:
    content = f.read()

# Add dotenv import and loading
dotenv_code = """import os
import re
import json
import sys
import shutil
import time
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
"""

content = content.replace(
    "import os\nimport re\nimport json\nimport sys\nimport shutil\nimport time\nfrom typing import List, Optional\n",
    dotenv_code
)

with open("discography_webapp/main.py", "w") as f:
    f.write(content)

with open("discography_webapp/requirements.txt", "a") as f:
    f.write("\npython-dotenv\n")
