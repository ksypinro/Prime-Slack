# Security Policy

## Supported Versions

We provide security updates for the latest release on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

---

## Reporting a Vulnerability

Security of Slack workspace integrations is a critical priority. If you believe you have found a security vulnerability in this project, please follow the guidelines below:

### 1. Do NOT Report Publicly
Please do **not** report security vulnerabilities through public GitHub issues, discussions, or pull requests.

### 2. How to Report
Please disclose the issue responsibly by emailing the project maintainer directly or using GitHub's **Private Security Advisory** feature.

In your report, please include:
- A description of the vulnerability.
- Steps to reproduce the issue.
- Potential impact and affected components.
- A proposed fix or mitigation (if available).

---

## Best Practices for Slack Token Security

When using or developing this project:
1. **Never Commit Secrets:** Ensure that your `.env` file containing `SLACK_BOT_TOKEN` (`xoxb-...`) and `SLACK_APP_TOKEN` (`xapp-...`) is never committed to Git.
2. **Rotate Leaked Tokens Immediately:** If you suspect a token has been exposed, revoke it immediately at [api.slack.com/apps](https://api.slack.com/apps) under **OAuth & Permissions** and **Basic Information**.
3. **Use Scopes Sparingly:** Only grant the minimal bot scopes required for your application to function.
