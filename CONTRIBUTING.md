# Contributing to Slack Socket Mode Bot

Thank you for your interest in contributing to this project! We welcome contributions from the community.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## How Can I Contribute?

### 1. Reporting Bugs
- Search existing GitHub Issues before opening a new one.
- Provide a clear and descriptive title.
- Describe the steps to reproduce the issue, the expected behavior, and the actual behavior.
- **Never include real Slack tokens (`xoxb-`, `xapp-`) in issue logs or screenshots!**

### 2. Suggesting Enhancements
- Open a GitHub Issue with the tag `enhancement`.
- Explain why this enhancement would be useful to other users.
- Provide examples or architectural mockups if applicable.

### 3. Pull Requests
1. **Fork** the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Set up your local environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Make your changes:**
   - Keep code clean and well-documented.
   - Follow PEP 8 guidelines for Python code formatting.
4. **Test your changes:**
   - Run syntax verification:
     ```bash
     python3 -m py_compile app.py processor.py test_connection.py
     ```
   - Verify connection test:
     ```bash
     python test_connection.py
     ```
5. **Commit your changes:**
   - Use clear commit messages following Conventional Commits (e.g., `feat: ...`, `fix: ...`, `docs: ...`).
   - Ensure no `.env` or sensitive tokens are staged (`git status`).
6. **Push to your fork and submit a Pull Request:**
   - Reference any relevant issues in the PR description.

---

## Development Guidelines

- **Zero Webhook Ingress:** Keep the design focused on Socket Mode and firewall-friendly WebSocket streaming. Do not introduce requirements for open ports or public HTTP endpoints.
- **Modularity:** Keep LLM / reasoning integrations encapsulated inside [`processor.py`](processor.py) to ensure the core listener remains lightweight and extensible.
