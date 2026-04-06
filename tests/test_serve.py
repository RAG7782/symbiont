"""Tests for the HTTP bridge sanitize utility."""

from symbiont.serve import _sanitize


class TestSanitize:
    def test_primitives(self):
        assert _sanitize("hello") == "hello"
        assert _sanitize(42) == 42
        assert _sanitize(3.14) == 3.14
        assert _sanitize(True) is True
        assert _sanitize(None) is None

    def test_dict(self):
        result = _sanitize({"a": 1, "b": "c"})
        assert result == {"a": 1, "b": "c"}

    def test_list(self):
        result = _sanitize([1, "a", None])
        assert result == [1, "a", None]

    def test_set(self):
        result = _sanitize({1, 2, 3})
        assert isinstance(result, list)
        assert set(result) == {1, 2, 3}

    def test_nested(self):
        result = _sanitize({"agents": {"total": 9}, "castes": [1, 2]})
        assert result["agents"]["total"] == 9

    def test_non_serializable(self):
        class Foo:
            pass
        result = _sanitize(Foo())
        assert isinstance(result, str)

    def test_enum_keys(self):
        from symbiont.types import Caste
        result = _sanitize({Caste.QUEEN: 1})
        assert "Caste.QUEEN" in result or "QUEEN" in result
