"""Moving a checkout must not select an old account, root or model identity."""

import importlib.util
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location('portable_' + Path(relative).stem.replace('-', '_'), ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableConfigurationTests(unittest.TestCase):
    def test_both_entrypoints_default_to_their_checkout(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load('tools/kingdom-agent.py').LOVE_DIR, ROOT)
            self.assertEqual(load('adaptive/config.py').LOVE_DIR, ROOT)

    def test_explicit_root_and_ollama_command_preserve_spaces(self):
        with tempfile.TemporaryDirectory(prefix='Love space ') as folder, patch.dict(os.environ, {'LOVE_DIR': folder}, clear=True):
            agent = load('tools/kingdom-agent.py')
            config = load('adaptive/config.py')
            root = Path(folder).resolve()
            self.assertEqual(agent.LOVE_DIR, root)
            self.assertEqual(config.LOVE_DIR, root)
            directive = agent.OllamaBackend.__new__(agent.OllamaBackend)._tool_directive()
            command = json.loads(directive.split('command=', 1)[1].splitlines()[0])
            self.assertEqual(shlex.split(command), ['python3', str(root / 'script.py')])
            self.assertNotIn('/Users/yu/Love', directive)

    def test_executable_override_is_authoritative_and_must_be_executable(self):
        agent = load('tools/kingdom-agent.py')
        with tempfile.TemporaryDirectory(prefix='Claude space ') as folder:
            executable = Path(folder) / 'chosen-cli'
            executable.write_text('#!/bin/sh\nexit 0\n')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'LOVE_CLAUDE_BIN': str(executable)}, clear=True):
                self.assertEqual(agent.ClaudeBackend().claude_bin, str(executable))
                executable.chmod(0o600)
                with self.assertRaises(FileNotFoundError):
                    agent.ClaudeBackend()

    def test_path_precedes_current_user_fallback_without_old_home_lookup(self):
        agent = load('tools/kingdom-agent.py')
        with patch.dict(os.environ, {}, clear=True), patch.object(agent.shutil, 'which', return_value='/chosen/claude') as which:
            self.assertEqual(agent.ClaudeBackend().claude_bin, '/chosen/claude')
            which.assert_called_once_with('claude')
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path('/current user')), patch.object(agent.shutil, 'which', side_effect=[None, '/current user/.local/bin/claude']) as which:
            self.assertEqual(agent.ClaudeBackend().claude_bin, '/current user/.local/bin/claude')
            self.assertEqual(which.call_args_list[-1].args, ('/current user/.local/bin/claude',))

    def test_relative_executable_remains_bound_when_run_changes_directory(self):
        agent = load('tools/kingdom-agent.py')
        root = Path.cwd()
        instance_dir = root / 'instances' / 'delta'
        with patch.dict(os.environ, {'LOVE_CLAUDE_BIN': './bin/claude'}, clear=True), patch.object(agent.shutil, 'which', return_value='./bin/claude'):
            backend = agent.ClaudeBackend()
        with patch.object(agent.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(backend.run('test', instance_dir), 0)
            self.assertEqual(run.call_args.args[0][0], str(root / 'bin' / 'claude'))
            self.assertEqual(run.call_args.kwargs['cwd'], str(instance_dir))

    def test_instance_selection_is_explicit_or_scoped_to_configured_tree(self):
        config = load('adaptive/config.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            path = root / 'love.json'
            path.write_text(json.dumps({'instances': {'delta': {'ollama': {'standard': 'delta-model'}}}}))
            with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'cwd', return_value=root / 'instances' / 'delta' / 'work'):
                self.assertEqual(config.AdaptiveConfig(path).instance, 'delta')
                self.assertEqual(config.AdaptiveConfig(path, instance='').instance, '')
            with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'cwd', return_value=root / 'elsewhere' / 'instances' / 'delta'):
                self.assertEqual(config.AdaptiveConfig(path).instance, '')
            with patch.dict(os.environ, {'LOVE_INSTANCE': 'delta', 'HIVE_INSTANCE': 'alpha'}, clear=True):
                self.assertEqual(config.AdaptiveConfig(path).instance, 'delta')
                self.assertEqual(config.AdaptiveConfig(path, instance='').instance, '')
            with patch.dict(os.environ, {'LOVE_INSTANCE': '', 'HIVE_INSTANCE': 'alpha'}, clear=True):
                self.assertEqual(config.AdaptiveConfig(path).instance, '')

    def test_instance_overrides_do_not_leak_into_later_configs_or_defaults(self):
        config = load('adaptive/config.py')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'love.json'
            path.write_text(json.dumps({'instances': {'delta': {'ollama': {'standard': 'delta-model'}}}}))
            original = config.DEFAULTS['providers']['ollama']['models']['standard']
            selected = config.AdaptiveConfig(path, instance='delta')
            plain = config.AdaptiveConfig(path, instance='')
            self.assertEqual(selected.model_for('ollama', 'standard'), 'delta-model')
            self.assertEqual(plain.model_for('ollama', 'standard'), original)
            self.assertEqual(config.DEFAULTS['providers']['ollama']['models']['standard'], original)
            path.write_text('{}')
            selected.reload()
            self.assertEqual(selected.model_for('ollama', 'standard'), original)


if __name__ == '__main__':
    unittest.main()
