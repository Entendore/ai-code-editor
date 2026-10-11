import os
import json
import shutil
from datetime import datetime

class CustomVCS:
    def __init__(self, work_dir="."):
        self.work_dir = work_dir
        self.vcs_dir = os.path.join(work_dir, ".ai_vcs")
        os.makedirs(self.vcs_dir, exist_ok=True)

    def checkpoint(self, description="AI Checkpoint"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_id = f"cp_{ts}"
        snap_path = os.path.join(self.vcs_dir, snap_id)
        os.makedirs(snap_path)
        
        meta = {"id": snap_id, "desc": description, "time": ts}
        with open(os.path.join(snap_path, "meta.json"), "w") as f:
            json.dump(meta, f)

        ignore_dirs = ['.git', '.ai_vcs', 'node_modules', '__pycache__']
        for root, dirs, files in os.walk(self.work_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.work_dir)
                dest_path = os.path.join(snap_path, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(file_path, dest_path)
        return snap_id

    def revert(self, snap_id):
        snap_path = os.path.join(self.vcs_dir, snap_id)
        if not os.path.exists(snap_path): return "Error: Snapshot not found"
        
        for root, dirs, files in os.walk(self.work_dir, topdown=False):
            dirs[:] = [d for d in dirs if d != '.ai_vcs']
            for file in files: os.remove(os.path.join(root, file))
            for dir in dirs:
                try: os.rmdir(os.path.join(root, dir))
                except: pass
                
        for root, dirs, files in os.walk(snap_path):
            for file in files:
                if file == "meta.json": continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, snap_path)
                dest_path = os.path.join(self.work_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(file_path, dest_path)
        return f"Reverted to {snap_id}"

    def list_snapshots(self):
        snaps = []
        for d in os.listdir(self.vcs_dir):
            meta_path = os.path.join(self.vcs_dir, d, "meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f: snaps.append(json.load(f))
        return sorted(snaps, key=lambda x: x['time'], reverse=True)

vcs = CustomVCS()
