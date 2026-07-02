import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jarvis_agent.config import (
    AGENT_STATE_NAME,
    JARVIS_HOME_ENV,
    discover_mlx_models,
    load_config,
    local_agent_state_path,
    local_available_models,
    save_local_model_state,
    save_local_model_state_with_models,
)


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.home_dir.cleanup)
        env_patch = patch.dict(os.environ, {JARVIS_HOME_ENV: self.home_dir.name})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_load_config_with_project_override(self) -> None:
        path = Path(self._testMethodName).resolve()
        config = load_config(path=None, project_override=path)
        self.assertEqual(config.project.root, path)
        self.assertEqual(config.model.backend, "mlx")
        self.assertTrue((Path(self.home_dir.name) / AGENT_STATE_NAME).exists())

    def test_local_agent_state_overrides_model_config(self) -> None:
        state_path = local_agent_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "model": {
                        "backend": "mlx",
                        "model": "mlx-community/Josiefied-Qwen2.5-Coder-7B-Instruct-abliterated-v1-4bit",
                        "max_tokens": 1024,
                        "temperature": 0.1,
                    },
                }
            ),
            encoding="utf-8",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(path=None, project_override=root)

            self.assertEqual(config.model.model, "mlx-community/Josiefied-Qwen2.5-Coder-7B-Instruct-abliterated-v1-4bit")
            self.assertEqual(config.model.max_tokens, 1024)
            self.assertEqual(config.model.temperature, 0.1)

    def test_save_local_model_state_writes_home_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(path=None, project_override=Path(directory))
            config = replace(config, model=replace(config.model, model="custom/model", max_tokens=4096, temperature=0.3))

            state_path = save_local_model_state(config)
            data = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(state_path.resolve(), local_agent_state_path().resolve())
            self.assertEqual(data["model"]["model"], "custom/model")
            self.assertEqual(data["model"]["max_tokens"], 4096)
            self.assertEqual(data["model"]["temperature"], 0.3)
            self.assertEqual(data["model"]["display"], "model")
            self.assertEqual(data["display"]["model_badge"], "model · mlx")
            self.assertIn("available_models", data)

    def test_save_local_model_state_preserves_discovered_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(path=None, project_override=Path(directory))
            state_path = save_local_model_state_with_models(config, ["mlx-community/New-Coder-4bit"])
            data = json.loads(state_path.read_text(encoding="utf-8"))

            models = [item["model"] for item in data["available_models"]]
            self.assertIn("mlx-community/New-Coder-4bit", models)
            self.assertIn("mlx-community/New-Coder-4bit", local_available_models())

    def test_discover_mlx_models_from_huggingface_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "models--mlx-community--New-Coder-4bit" / "snapshots" / "abc123"
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}", encoding="utf-8")

            self.assertEqual(discover_mlx_models([root]), ("mlx-community/New-Coder-4bit",))
