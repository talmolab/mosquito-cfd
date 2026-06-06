---
description: Test-driven development workflow for scientific software
---

# Test-Driven Development (TDD)

Structured TDD workflow for implementing features with tests first, ensuring scientific correctness and code quality.

## Purpose

TDD is critical for scientific software where correctness matters. This workflow ensures:

1. Requirements are captured as executable tests before implementation
2. Edge cases are considered upfront (NaN, empty data, boundary conditions)
3. Numerical/geometric calculations have known-answer test fixtures
4. Regressions are caught immediately

## TDD Cycle

### Phase 1: Red (Write Failing Tests)

Write tests that define the expected behavior of the new feature:

```python
# tests/test_<module>.py

import pytest
import numpy as np


class TestNewFeature:
    """Tests for <feature description>."""

    def test_basic_functionality(self, sample_data):
        """Test that the feature works with normal input."""
        result = new_function(sample_data)
        assert result is not None
        # Assert specific expected values

    def test_edge_case_empty_data(self):
        """Test behavior with empty input."""
        result = new_function(np.empty((0, 2)))
        assert result is empty or raises appropriate error

    def test_edge_case_nan_values(self, sample_data_with_nans):
        """Test NaN handling."""
        result = new_function(sample_data_with_nans)
        # Assert NaN values are handled correctly

    def test_known_answer(self):
        """Test with known-answer fixture for numerical correctness."""
        # Use hand-calculated or reference values
        data = create_known_answer_fixture()
        result = new_function(data)
        np.testing.assert_allclose(result.value, expected_value, rtol=1e-6)
```

### Phase 2: Confirm Red

Run the tests to confirm they fail as expected:

```bash
uv run pytest tests/test_<module>.py -v
```

All new tests should fail with `ImportError`, `AttributeError`, or `AssertionError` - not with unexpected errors. If tests fail for wrong reasons, fix the test setup first.

### Phase 3: Green (Implement the Feature)

Write the minimum code to make all tests pass:

```python
# src/mosquito_cfd/<module>.py

def new_function(data):
    """Implement the feature."""
    # Write implementation that satisfies the tests
    ...
```

Run tests again:

```bash
uv run pytest tests/test_<module>.py -v
```

All tests should pass. If not, fix the implementation (not the tests, unless the test itself was wrong).

### Phase 4: Refactor

Improve the implementation while keeping tests green:

1. Clean up code structure
2. Add type hints
3. Improve variable names
4. Extract helper functions if needed

Run tests after each refactor step:

```bash
uv run pytest tests/test_<module>.py -v
```

### Phase 5: Verify Quality

Run the full quality check suite:

```bash
# Lint + formatting check (matches CI)
uv run ruff check src/ && uv run ruff format --check src/

# Full test suite (not just new tests)
uv run pytest tests/

# Coverage for the new module
uv run pytest --cov=src/mosquito_cfd --cov-report=term-missing tests/
```

### Phase 6: Commit

Commit with a descriptive message linking the test and implementation:

```bash
git add src/mosquito_cfd/<module>.py tests/test_<module>.py
git commit -m "feat: Add <feature description>

- Tests define expected behavior including edge cases
- Implementation satisfies all test cases
- Known-answer fixtures verify numerical correctness"
```

## Scientific Testing Patterns

### Known-Answer Tests

For numerical/geometric functions, use hand-calculated or reference values:

```python
def test_planform_area_known_answer(self):
    """Verify planform area with hand-calculated value."""
    # A unit square has area 1.0
    vertices = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    result = compute_area(vertices)
    np.testing.assert_allclose(result, 1.0, atol=1e-10)
```

### Boundary Condition Tests

Test at the edges of valid input:

```python
def test_minimum_vertex_count(self):
    """Test with minimum valid polygon (triangle)."""
    vertices = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])  # n=3
    result = compute_area(vertices)
    assert result is not None

def test_below_minimum_vertex_count(self):
    """Test with too few vertices."""
    vertices = np.array([[0.0, 0.0], [1.0, 0.0]])  # n=2, degenerate
    result = compute_area(vertices)
    assert result is None or np.isnan(result)
```

### Numerical Stability Tests

Verify calculations are stable with extreme values:

```python
def test_large_values(self):
    """Test numerical stability with large values."""
    vertices = np.array([[0.0, 0.0], [1e10, 0.0], [1e10, 1e10], [0.0, 1e10]])
    result = compute_area(vertices)
    np.testing.assert_allclose(result, 1e20, rtol=1e-6)

def test_near_degenerate(self):
    """Test behavior with near-collinear vertices."""
    vertices = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 1e-9]])
    result = compute_area(vertices)
    # Should handle gracefully, not produce NaN or crash
```

## Fixture Patterns

### Parametrized Tests

```python
@pytest.mark.parametrize("n_panels,expected_min", [
    (4, 4),
    (8, 8),
    (16, 16),
])
def test_panel_counts(self, n_panels, expected_min):
    """Test all panel counts produce valid output."""
    result = discretize_wing(n_panels=n_panels)
    assert len(result) >= expected_min
```

### Shared Fixtures

```python
@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    rng = np.random.default_rng(42)
    return rng.standard_normal((100, 2))
```

## Integration

- Run `/lint` during Phase 5 to check code style
- Run `/coverage` to verify test coverage meets threshold
- Run `/run-ci-locally` before committing to ensure full CI passes
