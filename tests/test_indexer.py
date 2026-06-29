import tempfile
import unittest
import json
from pathlib import Path

from jarvis_agent.config import IndexConfig
from jarvis_agent.project import CodebaseIndex, ProjectIndexer
from jarvis_agent.project.extractor import SymbolExtractor
from jarvis_agent.project.parser import TreeSitterParser


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

    def test_project_indexer_writes_json_index_and_extracts_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "worker.py").write_text(
                "class Worker:\n"
                "    def run(self):\n"
                "        initialize_worker()\n"
                "\n"
                "def initialize_worker():\n"
                "    return Worker()\n",
                encoding="utf-8",
            )
            (tmp_path / "include").mkdir()
            (tmp_path / "include" / "Event.h").write_text(
                "class Event {\n"
                "public:\n"
                "  void fill();\n"
                "};\n",
                encoding="utf-8",
            )
            (tmp_path / ".jarvis" / "index").mkdir(parents=True)
            (tmp_path / ".jarvis" / "index" / "ignored.py").write_text("def ignored(): pass\n", encoding="utf-8")

            index = ProjectIndexer(IndexConfig()).build(tmp_path)
            cache_path = tmp_path / ".jarvis" / "index" / "codebase_index.json"

            self.assertTrue(cache_path.exists())
            self.assertIn("2 scanned files", index.summary())
            self.assertIn("2 updated", index.summary())
            self.assertIn("symbols", index.summary())
            self.assertIn("Cache:", index.summary())
            self.assertGreaterEqual(index.stats.elapsed_seconds, 0.0)
            self.assertNotIn(".jarvis/index/ignored.py", [record.relative_path for record in index.files])

            data = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "1.0")
            self.assertIn("src/worker.py", data["files"])
            self.assertIn("initialize_worker", data["symbols"])
            self.assertEqual(data["symbols"]["initialize_worker"]["kind"], "function")
            self.assertIn("Event", data["symbols"])
            self.assertIn("initialize_worker", data["references"])

            loaded = CodebaseIndex.load(cache_path, tmp_path)
            self.assertEqual(loaded.find_definition("Worker")["kind"], "class")
            self.assertTrue(loaded.find_references("initialize_worker"))
            self.assertEqual(len(loaded.get_file_symbols("src/worker.py")), 3)
            self.assertTrue(loaded.search_symbols("worker"))
            self.assertEqual(loaded.get_index_stats()["files"], 2)

    def test_project_indexer_uses_hash_incremental_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "worker.py"
            source.write_text("def first():\n    return 1\n", encoding="utf-8")

            first = ProjectIndexer(IndexConfig()).build(tmp_path)
            self.assertEqual(first.stats.updated_files, 1)
            self.assertEqual(first.stats.skipped_files, 0)

            second = ProjectIndexer(IndexConfig()).build(tmp_path)
            self.assertEqual(second.stats.updated_files, 0)
            self.assertEqual(second.stats.skipped_files, 1)

            source.write_text("def second():\n    return 2\n", encoding="utf-8")
            third = ProjectIndexer(IndexConfig()).build(tmp_path)
            self.assertEqual(third.stats.updated_files, 1)
            self.assertIsNone(third.codebase.find_definition("first"))
            self.assertIsNotNone(third.codebase.find_definition("second"))

            source.unlink()
            fourth = ProjectIndexer(IndexConfig()).build(tmp_path)
            self.assertEqual(fourth.stats.removed_files, 1)
            self.assertEqual(fourth.codebase.get_index_stats()["files"], 0)

    def test_symbol_extraction_is_tree_sitter_backed(self) -> None:
        self.assertIsInstance(SymbolExtractor().parser, TreeSitterParser)

        project_files = [
            Path("src/jarvis_agent/project/indexer.py"),
            Path("src/jarvis_agent/project/extractor.py"),
            Path("src/jarvis_agent/project/extractors/python_extractor.py"),
            Path("src/jarvis_agent/project/extractors/cpp_extractor.py"),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in project_files)

        self.assertIn("tree_sitter", Path("src/jarvis_agent/project/parser.py").read_text(encoding="utf-8"))
        self.assertNotIn("import ast", combined)
        self.assertNotIn("import re", combined)
        self.assertNotIn("re.", combined)
        self.assertNotIn("ast.", combined)
