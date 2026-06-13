"""Example unit tests for the gait analysis module.

This file demonstrates proper test structure and can be expanded with real tests.
"""

import pytest


@pytest.mark.unit
class TestBasicSetup:
    """Test that basic imports and setup work."""

    def test_module_imports(self):
        """Test that the main gait module can be imported."""
        try:
            import src.gait
            assert hasattr(src.gait, '__version__')
        except ImportError:
            pytest.fail("Failed to import src.gait module")

    def test_version_exists(self):
        """Test that version is defined."""
        import src.gait
        assert src.gait.__version__ == "0.1.0"

    def test_example_assertion(self):
        """Basic test to verify pytest is working."""
        assert 1 + 1 == 2

    @pytest.mark.parametrize("a,b,expected", [
        (1, 1, 2),
        (2, 3, 5),
        (10, 20, 30),
    ])
    def test_addition(self, a, b, expected):
        """Parametrized test for addition."""
        assert a + b == expected


@pytest.mark.unit
def test_simple_function():
    """Simple standalone test."""
    def add(a, b):
        return a + b

    assert add(1, 2) == 3
    assert add(10, 20) == 30
