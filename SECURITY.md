# Security Policy

## Reporting a vulnerability

If you believe you’ve found a security issue, **do not** open a public issue with secrets or exploit details.

Instead, contact the repository owner privately with:

- What you found
- Steps to reproduce
- Impact assessment
- Any suggested fix

## Secrets

Never commit API keys or tokens (for example: NVIDIA `nvapi-...`, OpenAI keys, GitHub tokens).

Use:

- `.env` for local secrets (ignored by git)
- `.env.example` as a template (no real secrets)

