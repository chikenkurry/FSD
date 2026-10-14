"""Algorithm tests."""
"""Include the original function-style regressions in standard unittest discovery."""
import importlib
import unittest


def load_tests(loader, tests, pattern):
    for name in ("test_end_to_end_fixtures", "test_feasibility", "test_ranking_and_pareto", "test_validation_and_readiness"):
        module = importlib.import_module(f"{__name__}.{name}")
        for key, value in vars(module).items():
            if key.startswith("test_") and callable(value):
                tests.addTest(unittest.FunctionTestCase(value))
    return tests
