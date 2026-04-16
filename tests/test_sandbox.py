"""Tests for the Sandbox subsystem (v0.4.1)."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from symbiont.sandbox import (
    LocalSandbox,
    MountConfig,
    SandboxConfig,
    SandboxProvider,
    _safe_thread_dirname,
    get_sandbox_provider,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cfg(tmp_path):
    return SandboxConfig(base_dir=str(tmp_path / "sandboxes"))


@pytest.fixture
def provider(tmp_cfg):
    p = SandboxProvider(config=tmp_cfg)
    yield p
    p.shutdown()


@pytest.fixture
def sandbox(provider):
    provider.acquire("t1")
    return provider.get_by_thread("t1")


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

class TestPathSafety:
    """Path traversal and confinement enforcement."""

    @pytest.mark.asyncio
    async def test_write_normal_path_succeeds(self, sandbox):
        await sandbox.write_file("/mnt/workspace/hello.txt", b"hello")
        content = await sandbox.read_file("/mnt/workspace/hello.txt")
        assert content == "hello"

    @pytest.mark.asyncio
    async def test_path_traversal_write_blocked(self, sandbox):
        with pytest.raises(PermissionError, match="traversal"):
            await sandbox.write_file("/mnt/workspace/../../../tmp/escape.txt", b"x")

    @pytest.mark.asyncio
    async def test_path_outside_mounts_raises(self, sandbox):
        with pytest.raises(ValueError, match="outside all sandbox mounts"):
            await sandbox.read_file("/etc/passwd")

    @pytest.mark.asyncio
    async def test_read_only_mount_blocks_write(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "skill.py").write_text("# skill")
        cfg = SandboxConfig(base_dir=str(tmp_path / "sb"))
        sb = LocalSandbox("sb:ro", "ro", cfg, skills_dir=str(skills))

        with pytest.raises(PermissionError):
            await sb.write_file("/mnt/skills/attack.py", b"evil")

        # Reading is allowed
        content = await sb.read_file("/mnt/skills/skill.py")
        assert "skill" in content


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class TestExecution:
    @pytest.mark.asyncio
    async def test_execute_simple_command(self, sandbox):
        out, code = await sandbox.execute("echo hello_symbiont")
        assert "hello_symbiont" in out
        assert code == 0

    @pytest.mark.asyncio
    async def test_execute_exit_code(self, sandbox):
        _, code = await sandbox.execute("exit 42")
        assert code == 42

    @pytest.mark.asyncio
    async def test_execute_uses_workspace_cwd(self, sandbox):
        await sandbox.write_file("/mnt/workspace/marker.txt", b"found")
        out, code = await sandbox.execute("ls")
        assert "marker.txt" in out
        assert code == 0

    @pytest.mark.asyncio
    async def test_execute_masks_host_paths(self, sandbox):
        """Host filesystem paths must not appear in output."""
        out, _ = await sandbox.execute("pwd")
        # Should see /mnt/workspace, not the real host path
        host_base = str(sandbox._workspace)
        assert host_base not in out

    @pytest.mark.asyncio
    async def test_execute_stream_yields_lines(self, sandbox):
        lines = []
        exit_code = None
        async for line in sandbox.execute_stream("echo A && echo B && echo C"):
            if line.startswith("\x00EXIT:"):
                exit_code = int(line[6:])
            else:
                lines.append(line.strip())
        assert lines == ["A", "B", "C"]
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_stream_timeout(self, sandbox):
        lines = []
        async for line in sandbox.execute_stream("sleep 10", timeout=1):
            lines.append(line)
        combined = "".join(lines)
        assert "timeout" in combined

    @pytest.mark.asyncio
    async def test_execute_truncates_long_output(self, sandbox):
        cfg = SandboxConfig(base_dir=str(sandbox._workspace.parent.parent), bash_output_max_chars=50)
        sb = LocalSandbox("sb:trunc", "trunc", cfg)
        await sb.write_file("/mnt/workspace/big.sh", b"python3 -c \"print('x' * 1000)\"")
        out, _ = await sb.execute("sh /mnt/workspace/big.sh")
        assert len(out) <= 50 + 60  # 60 for truncation suffix


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

class TestFileOperations:
    @pytest.mark.asyncio
    async def test_write_read_roundtrip(self, sandbox):
        await sandbox.write_file("/mnt/workspace/data.bin", b"\x00\x01\x02\xFF")
        content = await sandbox.read_file("/mnt/workspace/data.bin")
        assert "\x00\x01\x02" in content  # bytes decoded with errors=replace

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, sandbox):
        await sandbox.write_file("/mnt/workspace/deep/nested/file.txt", b"deep")
        content = await sandbox.read_file("/mnt/workspace/deep/nested/file.txt")
        assert content == "deep"

    @pytest.mark.asyncio
    async def test_list_dir(self, sandbox):
        await sandbox.write_file("/mnt/workspace/a.py", b"")
        await sandbox.write_file("/mnt/workspace/b.py", b"")
        entries, truncated = await sandbox.list_dir("/mnt/workspace")
        names = [e["name"] for e in entries]
        assert "a.py" in names
        assert "b.py" in names
        assert not truncated

    @pytest.mark.asyncio
    async def test_grep_finds_pattern(self, sandbox):
        await sandbox.write_file("/mnt/workspace/search.py", b"def hello_world():\n    return 42\n")
        results, _ = await sandbox.grep("hello_world", ["/mnt/workspace/search.py"])
        assert len(results) == 1
        assert results[0]["line"] == 1
        assert "hello_world" in results[0]["content"]


# ---------------------------------------------------------------------------
# Provider lifecycle
# ---------------------------------------------------------------------------

class TestProvider:
    def test_acquire_returns_stable_id(self, provider):
        id1 = provider.acquire("t1")
        id2 = provider.acquire("t1")
        assert id1 == id2

    def test_get_by_thread(self, provider):
        provider.acquire("t2")
        sb = provider.get_by_thread("t2")
        assert sb is not None
        assert sb.thread_id == "t2"

    def test_release_cleans_workspace(self, provider, tmp_cfg):
        provider.acquire("cleanup_test")
        sb = provider.get_by_thread("cleanup_test")
        assert sb._workspace.exists()
        provider.release("cleanup_test")
        assert not sb._workspace.exists()
        assert provider.get_by_thread("cleanup_test") is None

    def test_shutdown_releases_all(self, provider):
        for i in range(3):
            provider.acquire(f"thread_{i}")
        assert len(provider._sandboxes) == 3
        provider.shutdown()
        assert len(provider._sandboxes) == 0

    def test_safe_thread_dirname_sanitizes(self):
        assert "/" not in _safe_thread_dirname("worker:abc/123")
        assert ".." not in _safe_thread_dirname("../../escape")

    def test_docker_backend_instantiates(self, tmp_cfg):
        """DockerSandbox can be constructed without Docker being installed."""
        p = SandboxProvider(config=tmp_cfg, backend="docker")
        sid = p.acquire("docker_t1")
        sb = p.get_by_thread("docker_t1")
        assert sb is not None
        assert sb.id == sid
        p.shutdown()
