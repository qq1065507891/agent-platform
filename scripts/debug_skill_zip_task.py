from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from app.core.database import SessionLocal
from app.models.skill import Skill
from app.tasks.skill_tasks import load_external_skill_task


def main() -> None:
    db = SessionLocal()
    try:
        skill = Skill(
            skill_id="tmp_skill_debug_zip",
            name="tmp_skill_debug_zip",
            version="1.0.0",
            category="custom",
            source_type="local",
            status="disabled",
            yaml_definition={},
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

        d = Path(tempfile.mkdtemp(prefix="zip_dbg_"))
        py = d / "main.py"
        py.write_text("def run(params):\n    return {'ok': True}\n", encoding="utf-8")
        z = d / "pkg.zip"
        with zipfile.ZipFile(z, "w") as zp:
            zp.write(py, "main.py")

        result = load_external_skill_task.run(
            skill_id=skill.id,
            source_type="local",
            source_url="upload://pkg.zip",
            package_path=str(z),
        )
        print("TASK_RESULT:", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
