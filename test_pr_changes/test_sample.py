# Test file for PR validation
# This file is used for testing pull request changes

def sample_function():
    """Sample function for testing."""
    return "Hello from test PR"

def test_sample():
    """Simple test for validation."""
    result = sample_function()
    assert result == "Hello from test PR"
    print("✓ Test passed")

if __name__ == "__main__":
    test_sample()
