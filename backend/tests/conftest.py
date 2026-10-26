import os, sys, tempfile
from pathlib import Path
test_root=Path(__file__).resolve().parents[2]/'.test-runs'
test_root.mkdir(exist_ok=True)
tmp = tempfile.mkdtemp(dir=test_root)
os.environ["DG_DB"] = f"sqlite:///{tmp}/test.db"
os.environ["DG_STORAGE"] = f"{tmp}/storage"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
