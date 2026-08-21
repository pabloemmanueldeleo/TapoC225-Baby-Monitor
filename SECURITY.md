# Security Policy / Política de Seguridad

## Supported Versions / Versiones Soportadas

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0.0 | :x:                |

---

## 🔒 Security & Privacy Architecture / Arquitectura de Privacidad

This project is designed as an **Edge-First / Local-Only** application:
1. **Local Processing**: Video streaming (RTSP), audio telemetry, and AI neural inference (YOLOv8 / ONNX) run 100% locally on your machine. No telemetry or video frames are transmitted to external servers.
2. **Credentials Storage**: Camera IP, usernames, and passwords are exclusively stored locally in `.env` or `config.json`. These files are included in `.gitignore` to prevent accidental disclosure.
3. **Network Recommendations**: Never expose camera RTSP ports directly to the public internet via Port Forwarding. If remote access is needed, use a secure VPN (such as WireGuard or Tailscale).

---

## 🚨 Reporting a Vulnerability / Reportar una Vulnerabilidad

If you discover a security vulnerability or credential leak risk in this repository:

### 1. Do NOT open a public issue
Please do not disclose security vulnerabilities publicly in GitHub Issues or Discussions until a fix has been prepared and released.

### 2. How to report
- **GitHub Security Advisories (Recommended)**: Go to the repository's [Security Tab](https://github.com/pabloemmanueldeleo/TapoC225-Baby-Monitor/security) and click **"Report a vulnerability"** (Private Vulnerability Reporting).
- Alternatively, you can contact the maintainer directly via GitHub profile: [@pabloemmanueldeleo](https://github.com/pabloemmanueldeleo).

### 3. What to include in your report
- A clear description of the vulnerability.
- Step-by-step instructions to reproduce the issue (PoC / proof-of-concept if available).
- Potential impact on camera privacy or system security.
- Any suggested fixes or mitigations.

### 4. Response & Resolution Process
- **Acknowledgment**: You will receive an initial response within **48 to 72 hours**.
- **Investigation**: We will validate and reproduce the findings.
- **Remediation**: Once confirmed, a security patch will be developed and released in a subsequent minor/patch release (`1.0.x`).
