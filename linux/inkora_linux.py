#!/usr/bin/env python3
"""Linux launcher; the application code is shared with future OS launchers."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"commun"))
from inkora.__main__ import main

if __name__=="__main__":
    main()
