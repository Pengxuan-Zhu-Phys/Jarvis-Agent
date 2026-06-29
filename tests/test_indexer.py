import tempfile
import unittest
from pathlib import Path

from jarvis_agent.config import IndexConfig
from jarvis_agent.project import ProjectIndexer


class ProjectIndexerTests(unittest.TestCase):
    def test_project_indexer_skips_ignored_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
            (tmp_path / "build").mkdir()
            (tmp_path / "build" / "generated.cpp").write_text("generated\n", encoding="utf-8")

            index = ProjectIndexer(IndexConfig()).build(tmp_path)

            self.assertEqual([record.relative_path for record in index.files], ["src/main.cpp"])
