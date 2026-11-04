import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_rebuild_workspace import CANONICAL_ROOT, ROOT, verify


def test_real_audited_worktree():
    result = verify(ROOT, ROOT / "infra/runtime/p00/new-test-file")
    assert result["status"] == "PASS"
    assert Path(result["git_common_dir"]) == CANONICAL_ROOT / ".git"


@pytest.mark.parametrize("candidate", [
    CANONICAL_ROOT,
    CANONICAL_ROOT.parent / "Silver-economy",
    CANONICAL_ROOT.parent / "Silver-economy/.work/intelligence-20261103",
])
def test_rejects_other_worktrees_and_old_repository(candidate):
    with pytest.raises(ValueError, match="UNAUDITED_OR_WRONG_REPOSITORY"):
        verify(candidate, candidate / "SIMULATED_DANGEROUS_WRITE")
    assert not (candidate / "SIMULATED_DANGEROUS_WRITE").exists()


@pytest.mark.parametrize("target", [
    CANONICAL_ROOT / "services/life-core/data/life-core.sqlite3",
    CANONICAL_ROOT.parent / "Silver-economy/DO_NOT_WRITE",
    ROOT / "../../../../../outside-workspace",
])
def test_rejects_write_escape(target):
    with pytest.raises(ValueError, match="WRITE_TARGET_OUTSIDE_WORKTREE"):
        verify(ROOT, target)
