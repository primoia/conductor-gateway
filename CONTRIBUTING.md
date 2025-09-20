# Contributing to Conductor Gateway

Thank you for your interest in contributing to Conductor Gateway! This document provides guidelines and information for contributors.

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Poetry** for dependency management
- **Git** for version control
- **Docker** (optional, for testing containerization)

### Development Setup

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/conductor-gateway.git
cd conductor-gateway

# 3. Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# 4. Install dependencies
poetry install

# 5. Install pre-commit hooks
poetry run pre-commit install

# 6. Copy configuration template
cp config.yaml.example config.yaml

# 7. Verify setup
poetry run pytest tests/unit/test_config.py::TestConfigurationLoading::test_server_config_constants
```

## 🏗 Development Workflow

### 1. Create a Feature Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b bugfix/issue-number-description
```

### 2. Development Guidelines

#### Code Style

We use **Ruff** for formatting and linting (replaces Black, isort, flake8):

```bash
# Format code
poetry run ruff format src/ tests/

# Check linting
poetry run ruff check src/ tests/

# Fix auto-fixable issues
poetry run ruff check src/ tests/ --fix
```

#### Type Checking

We use **MyPy** for static type checking:

```bash
# Type check
poetry run mypy src/

# Type check with verbose output
poetry run mypy src/ --verbose
```

#### Security

We use **Bandit** for security scanning:

```bash
# Security scan
poetry run bandit -r src/
```

### 3. Testing Requirements

#### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m api

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Quick validation
python run_tests.py
```

#### Test Requirements

- **Unit tests** are required for all new functionality
- **Integration tests** for API endpoints and major features
- **Test coverage** should not decrease
- Tests must pass in all supported Python versions (3.11, 3.12, 3.13)

#### Writing Tests

```python
# Example unit test
@pytest.mark.unit
def test_function_name():
    """Test description following docstring conventions."""
    # Given
    input_data = "test_input"

    # When
    result = function_under_test(input_data)

    # Then
    assert result == expected_output

# Example integration test
@pytest.mark.integration
@patch('src.api.app.start_mcp_server')
def test_api_endpoint(mock_start_mcp):
    """Test API endpoint behavior."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
```

### 4. Documentation

#### Code Documentation

- **Docstrings**: All public functions, classes, and modules must have docstrings
- **Type hints**: Use type hints for all function parameters and return values
- **Comments**: Explain complex logic and business decisions

```python
def process_agent_command(agent_id: str, command: str, timeout: int = 120) -> dict[str, Any]:
    """
    Process an agent command with timeout handling.

    Args:
        agent_id: The unique identifier for the agent
        command: The command string to execute
        timeout: Execution timeout in seconds

    Returns:
        Dictionary containing execution results and metadata

    Raises:
        ValueError: If agent_id or command is empty
        TimeoutError: If execution exceeds timeout
    """
```

#### README Updates

- Update README.md if you add new features or change APIs
- Include code examples for new functionality
- Update configuration documentation if applicable

### 5. Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) specification:

```bash
# Format: type(scope): description
feat(api): add SSE streaming endpoint for real-time execution
fix(config): handle missing environment variables gracefully
docs(readme): update installation instructions
test(api): add integration tests for health endpoint
ci(github): update action versions to fix deprecation warnings
```

#### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding/updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `ci`: CI/CD changes
- `chore`: Maintenance tasks

## 📋 Pull Request Process

### 1. Before Submitting

- [ ] Code follows style guidelines (Ruff formatting)
- [ ] All tests pass locally
- [ ] Type checking passes (MyPy)
- [ ] Security scan passes (Bandit)
- [ ] Documentation is updated
- [ ] Commit messages follow conventional format

### 2. Pull Request Template

When creating a PR, use our template:

- **Description**: Clear description of changes
- **Type of Change**: Bug fix, new feature, breaking change, etc.
- **Testing**: How the changes were tested
- **Checklist**: Ensure all requirements are met

### 3. Review Process

1. **Automated Checks**: All GitHub Actions must pass
2. **Code Review**: At least one maintainer review required
3. **Testing**: Verify tests cover new functionality
4. **Documentation**: Ensure docs are updated if needed

### 4. After Approval

- **Squash and Merge**: We use squash commits for a clean history
- **Delete Branch**: Remove feature branch after merge

## 🏗 Architecture Guidelines

### Project Structure

```
src/
├── api/           # FastAPI application and endpoints
├── config/        # Configuration management
├── server/        # MCP server implementation
├── tools/         # Conductor CLI integration tools
└── utils/         # Shared utility functions

tests/
├── unit/          # Unit tests (fast, isolated)
├── integration/   # Integration tests (slower, real components)
└── conftest.py    # Shared test configuration
```

### Design Principles

1. **Separation of Concerns**: Keep API, business logic, and infrastructure separate
2. **Async by Default**: Use async/await for I/O operations
3. **Type Safety**: Comprehensive type hints and MyPy validation
4. **Error Handling**: Proper exception handling with informative messages
5. **Configuration**: Environment-based configuration with sensible defaults
6. **Testability**: Design for easy unit and integration testing

### Adding New Features

#### API Endpoints

```python
@app.post("/api/v1/new-feature")
async def new_feature_endpoint(request: FeatureRequest) -> FeatureResponse:
    """
    New feature endpoint with proper typing and documentation.
    """
    try:
        result = await process_feature(request)
        return FeatureResponse(status="success", data=result)
    except Exception as e:
        logger.error(f"Feature processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

#### MCP Tools

```python
@self.mcp.tool(
    name="new_tool",
    description="""Description of what the tool does.
    Parameters:
    - param1: Description of parameter

    Returns description of what is returned."""
)
def new_mcp_tool(self, param1: str) -> str:
    """Implementation of new MCP tool."""
    return self._execute_conductor_command(["--new-command", param1])
```

## 🧪 Testing Guidelines

### Test Categories

- **Unit Tests** (`@pytest.mark.unit`): Fast, isolated, no external dependencies
- **Integration Tests** (`@pytest.mark.integration`): Test component interaction
- **API Tests** (`@pytest.mark.api`): Test HTTP endpoints
- **Slow Tests** (`@pytest.mark.slow`): Long-running tests

### Test Structure

```python
class TestFeatureName:
    """Test class for specific feature."""

    def test_happy_path(self):
        """Test the main success scenario."""

    def test_edge_cases(self):
        """Test boundary conditions."""

    def test_error_handling(self):
        """Test error scenarios."""

    @pytest.mark.parametrize("input,expected", [
        ("input1", "output1"),
        ("input2", "output2"),
    ])
    def test_multiple_scenarios(self, input, expected):
        """Test multiple input/output combinations."""
```

### Mocking Guidelines

```python
# Mock external dependencies
@patch('src.utils.mcp_utils.init_agent')
def test_with_mocked_agent(mock_init_agent):
    mock_agent = AsyncMock()
    mock_agent.run.return_value = "expected_result"
    mock_init_agent.return_value = mock_agent

    # Test code here
```

## 🔒 Security Guidelines

### Security Best Practices

1. **Input Validation**: Validate all user inputs
2. **No Secrets in Code**: Use environment variables for secrets
3. **Secure Dependencies**: Keep dependencies updated
4. **Error Messages**: Don't expose sensitive information in errors
5. **Logging**: Don't log sensitive information

### Security Testing

```bash
# Run security scan
poetry run bandit -r src/

# Check for known vulnerabilities in dependencies
poetry audit
```

## 📚 Documentation Guidelines

### Code Documentation

- Use **Google-style docstrings**
- Include **type hints** for all functions
- Document **complex algorithms** with inline comments
- Add **examples** for public APIs

### External Documentation

- Update **README.md** for user-facing changes
- Add **architecture docs** for major design decisions
- Include **API examples** for new endpoints

## 🏷 Release Process

### Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Workflow

1. **Create Release PR**: Update version and changelog
2. **Tag Release**: Create Git tag with version number
3. **Automated Release**: GitHub Actions handles the rest
4. **Docker Images**: Automatically built and published

## 🤝 Community Guidelines

### Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please see our [Code of Conduct](CODE_OF_CONDUCT.md).

### Communication

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and general discussion
- **Pull Requests**: Code review and collaboration

### Getting Help

- **Documentation**: Check existing docs first
- **Search Issues**: Look for similar problems
- **Create Issue**: Use appropriate issue template
- **Be Specific**: Provide minimal reproduction examples

## 🎯 First-Time Contributors

### Good First Issues

Look for issues labeled:
- `good first issue`: Perfect for newcomers
- `help wanted`: Community help needed
- `documentation`: Documentation improvements

### Learning Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Poetry User Guide](https://python-poetry.org/docs/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Ruff User Guide](https://docs.astral.sh/ruff/)

## 📞 Questions?

If you have questions about contributing:

1. Check the [documentation](docs/)
2. Search [existing issues](https://github.com/primoia/conductor-gateway/issues)
3. Create a [new discussion](https://github.com/primoia/conductor-gateway/discussions)

Thank you for contributing to Conductor Gateway! 🚀