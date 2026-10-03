"""The operating layout: placed once, checked every time."""
import json

import pytest

from technoproj import lockstep as L


DISPATCH_BLOCK = ("dispatch:\n  name: example\n"
                  "  outbox: doc/lockstep/dispatch.md\n  inbox: issues\n")

ITEM = """
## D-001 To: other. Refund page and price
Why: the owner answered Q-010.
Ask: add a refund page.
Approval: https://example.com/pull/22
Re: none
"""


def quiet(_):
    pass


def filled(root, owner="aloecraft"):
    """A repository after `init` and after the owner fills in the scaffold."""
    L.init(root, owner=owner, out=quiet)
    claude = root / ".claude/CLAUDE.md"
    claude.write_text("# Example operator\n\nThe owner is Example.\n")
    a = root / "doc/lockstep/authority.yaml"
    a.write_text(a.read_text().replace(
        "owner: null   # technoproj: fill in", "owner: Example"))
    s = root / "doc/lockstep/sources.yaml"
    s.write_text("product: Example\nfacts:\n  repo: o/r\n  path: FACTS.yaml\n"
                 "docs: []\n" + DISPATCH_BLOCK)
    (root / "doc/lockstep/goal.md").write_text("# Goal\n\nThe number: 1\n")
    return root


def test_init_then_fill_in_passes(tmp_path):
    assert L.gaps(filled(tmp_path)) == []


def test_unfilled_scaffold_is_a_gap(tmp_path):
    L.init(tmp_path, out=quiet)
    found = L.gaps(tmp_path)
    for f in (".claude/CLAUDE.md", "doc/lockstep/authority.yaml",
              "doc/lockstep/sources.yaml", "doc/lockstep/goal.md",
              ".github/CODEOWNERS"):
        assert "%s is not filled in yet" % f in found


def test_init_never_overwrites(tmp_path):
    (tmp_path / "doc/lockstep").mkdir(parents=True)
    (tmp_path / "doc/lockstep/goal.md").write_text("ours\n")
    L.init(tmp_path, out=quiet)
    assert (tmp_path / "doc/lockstep/goal.md").read_text() == "ours\n"


def test_a_local_edit_to_a_shared_rule_is_drift(tmp_path):
    filled(tmp_path)
    rule = tmp_path / ".claude/rules/lockstep.md"
    rule.write_text(rule.read_text() + "\nA local exception.\n")
    assert any("lockstep.md has drifted" in g for g in L.gaps(tmp_path))
    L.sync(tmp_path, out=quiet)
    assert L.gaps(tmp_path) == []


def test_a_repo_rule_of_its_own_is_not_drift(tmp_path):
    filled(tmp_path)
    (tmp_path / ".claude/rules/ui-copy.md").write_text("# UI copy\n")
    assert L.gaps(tmp_path) == []


def test_surfaces_are_rendered_from_the_declaration(tmp_path):
    (tmp_path / ".technoproj").write_text(json.dumps(
        {"TECHNO_LOCKSTEP": {"surfaces": ["README.md", "doc/guides/"]}}))
    filled(tmp_path)
    text = (tmp_path / ".claude/rules/human-surfaces.md").read_text()
    assert "- `README.md`\n- `doc/guides/`\n" in text
    assert "@@SURFACES@@" not in text
    assert L.gaps(tmp_path) == []
    # Changing the declaration without syncing is drift.
    (tmp_path / ".technoproj").write_text(json.dumps(
        {"TECHNO_LOCKSTEP": {"surfaces": ["README.md"]}}))
    assert any("human-surfaces.md has drifted" in g
               for g in L.gaps(tmp_path))


def test_an_unknown_declaration_key_is_refused(tmp_path):
    (tmp_path / ".technoproj").write_text(json.dumps(
        {"TECHNO_LOCKSTEP": {"surface": ["README.md"]}}))
    with pytest.raises(L.LockstepError):
        L.init(tmp_path, out=quiet)


@pytest.mark.parametrize("pattern,target", [
    ("doc/lockstep/**", "doc/lockstep/authority.yaml"),
    ("doc/**", "doc/lockstep/goal.md"),
    ("'**'", "doc/lockstep/roadmap.md"),  # quoted: a bare * is a YAML alias
])
def test_self_merge_cannot_widen_authority(tmp_path, pattern, target):
    filled(tmp_path)
    a = tmp_path / "doc/lockstep/authority.yaml"
    a.write_text(a.read_text().replace(
        "    - .claude/**\n", "    - .claude/**\n    - %s\n" % pattern))
    assert ("doc/lockstep/authority.yaml self_merge reaches %s -- the "
            "operator cannot widen its own authority" % target
            ) in L.gaps(tmp_path)


def test_self_merge_must_except_the_rules(tmp_path):
    filled(tmp_path)
    a = tmp_path / "doc/lockstep/authority.yaml"
    a.write_text(a.read_text().replace("    - .claude/rules/**\n", ""))
    assert any("reaches .claude/rules/operating.md" in g
               for g in L.gaps(tmp_path))


def test_authority_shape(tmp_path):
    filled(tmp_path)
    (tmp_path / "doc/lockstep/authority.yaml").write_text(
        "version: 1\nowner: Example\ntiers:\n  autonomous: []\n")
    found = L.gaps(tmp_path)
    assert "doc/lockstep/authority.yaml tiers.never is not a list" in found
    assert "doc/lockstep/authority.yaml has no self_merge lane" in found
    assert "doc/lockstep/authority.yaml has no limits" in found


def test_roadmap_status_is_one_of_four(tmp_path):
    filled(tmp_path)
    r = tmp_path / "doc/lockstep/roadmap.md"
    r.write_text(r.read_text().replace("[active]", "[started]"))
    assert ("doc/lockstep/roadmap.md has unknown status: started"
            in L.gaps(tmp_path))


def test_codeowners_must_cover_lockstep_and_rules(tmp_path):
    filled(tmp_path)
    (tmp_path / ".github/CODEOWNERS").write_text(
        "/doc/lockstep/ @aloecraft\n")
    found = L.gaps(tmp_path)
    assert ".github/CODEOWNERS does not name an owner for /.claude/rules/" \
        in found
    assert ".github/CODEOWNERS does not name an owner for /doc/lockstep/" \
        not in found


def test_the_cli_round_trip(tmp_path, monkeypatch, capsys):
    from technoproj import cli
    monkeypatch.setenv("TECHNO_ROOT", str(tmp_path))
    assert cli.main(["lockstep", "init", "--owner", "aloecraft"]) == 0
    assert cli.main(["lockstep", "check"]) == 1
    assert "not filled in yet" in capsys.readouterr().err
    assert cli.main(["lockstep", "sync"]) == 0


def test_a_well_formed_dispatch_passes(tmp_path):
    filled(tmp_path)
    d = tmp_path / "doc/lockstep/dispatch.md"
    d.write_text(d.read_text() + ITEM + ITEM.replace("D-001", "D-002"))
    assert L.gaps(tmp_path) == []


def test_a_routed_inbox_passes(tmp_path):
    filled(tmp_path)
    s = tmp_path / "doc/lockstep/sources.yaml"
    s.write_text(s.read_text().replace(
        "inbox: issues", "inbox: {repo: o/router, path: dispatch/example.md}"))
    assert L.gaps(tmp_path) == []


def test_an_escalate_name_passes(tmp_path):
    filled(tmp_path)
    s = tmp_path / "doc/lockstep/sources.yaml"
    s.write_text(s.read_text().replace(
        "inbox: issues", "inbox: issues\n  escalate: answerer"))
    assert L.gaps(tmp_path) == []


def test_an_empty_escalate_is_a_gap(tmp_path):
    filled(tmp_path)
    s = tmp_path / "doc/lockstep/sources.yaml"
    s.write_text(s.read_text().replace(
        "inbox: issues", "inbox: issues\n  escalate: ''"))
    assert any("dispatch.escalate" in g for g in L.gaps(tmp_path))


def test_sources_without_dispatch_is_a_gap(tmp_path):
    filled(tmp_path)
    s = tmp_path / "doc/lockstep/sources.yaml"
    s.write_text(s.read_text().replace(DISPATCH_BLOCK, ""))
    assert any("has no dispatch block" in g for g in L.gaps(tmp_path))


def test_a_bad_inbox_is_a_gap(tmp_path):
    filled(tmp_path)
    s = tmp_path / "doc/lockstep/sources.yaml"
    s.write_text(s.read_text().replace("inbox: issues", "inbox: {repo: o/r}"))
    assert any("dispatch.inbox must be" in g for g in L.gaps(tmp_path))


def test_a_missing_outbox_is_a_gap(tmp_path):
    filled(tmp_path)
    (tmp_path / "doc/lockstep/dispatch.md").unlink()
    found = L.gaps(tmp_path)
    assert "doc/lockstep/dispatch.md is missing -- run 'technoproj lockstep init'" in found
    assert any("which does not exist" in g for g in found)


def test_a_malformed_dispatch_item_is_a_gap(tmp_path):
    filled(tmp_path)
    d = tmp_path / "doc/lockstep/dispatch.md"
    d.write_text(d.read_text() + ITEM.replace("To: other.", "for other:")
                 + ITEM.replace("Approval: https://example.com/pull/22\n", ""))
    found = L.gaps(tmp_path)
    assert any("malformed item header" in g for g in found)
    assert any("D-001 is missing Approval" in g for g in found)


def test_dispatch_numbers_only_go_up(tmp_path):
    filled(tmp_path)
    d = tmp_path / "doc/lockstep/dispatch.md"
    d.write_text(d.read_text() + ITEM.replace("D-001", "D-002") + ITEM)
    assert any("D-001 is out of order" in g for g in L.gaps(tmp_path))
