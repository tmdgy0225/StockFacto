import pytest

from harness.patch import PatchError, apply_patches, make_patches

CODE = "a\nb\nc\nd\ne\n"


def test_replace_insert_delete():
    patches = [
        {"op": "replace", "start": 2, "end": 2, "code": "B"},
        {"op": "insert", "after": 0, "code": "top"},
        {"op": "delete", "start": 4, "end": 5},
    ]
    assert apply_patches(CODE, patches) == "top\na\nB\nc\n"


def test_multiline_replace():
    assert apply_patches(CODE, [{"op": "replace", "start": 3, "end": 3, "code": "c1\nc2"}]) == "a\nb\nc1\nc2\nd\ne\n"


@pytest.mark.parametrize("patches", [
    [],
    [{"op": "rewrite", "start": 1, "end": 1}],
    [{"op": "replace", "start": 0, "end": 1, "code": "x"}],
    [{"op": "replace", "start": 2, "end": 9, "code": "x"}],
    [{"op": "replace", "start": "2", "end": 2, "code": "x"}],
    [{"op": "replace", "start": 2, "end": 2}],
    [{"op": "replace", "start": 1, "end": 3, "code": "x"}, {"op": "delete", "start": 3, "end": 4}],
    [{"op": "delete", "start": 2, "end": 4}, {"op": "insert", "after": 3, "code": "x"}],
])
def test_invalid_patches_are_rejected(patches):
    with pytest.raises(PatchError):
        apply_patches(CODE, patches)


def test_make_patches_roundtrip():
    old = "class S:\n    def f(self):\n        return 1\n"
    new = "import math\n\nclass S:\n    def f(self):\n        return 2\n"
    patches = make_patches(old, new)
    assert apply_patches(old, patches) == new
    assert len(patches) == 2
