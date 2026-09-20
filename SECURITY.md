# Security Policy / 安全策略

## Supported versions / 支持版本

Security fixes are applied to the latest published minor release. Older tags
remain immutable evidence and may not receive backports.

安全修复默认进入最新发布的小版本；历史 tag 保持不可变，不承诺回移修复。

## Reporting a vulnerability / 报告漏洞

Please do not open a public issue for a suspected vulnerability, leaked secret
or unredacted customer Trace. Use GitHub's **Report a vulnerability** private
reporting form for this repository. Include the affected version, a minimal
reproduction, impact, and whether any credential or private Trace is involved.

请不要用公开 Issue 报告疑似漏洞、泄露的密钥或未脱敏 Trace。请使用仓库 Security
页面中的 **Report a vulnerability** 私密报告入口，并提供受影响版本、最小复现、
影响范围，以及是否涉及凭证或私有 Trace。

The maintainer aims to acknowledge a report within 7 days, confirm severity or
request more information within 14 days, and coordinate disclosure after a fix
is available. These are best-effort targets, not a commercial SLA.

维护者目标是在 7 天内确认收到、14 天内判断严重性或补充询问，并在修复可用后协商
公开时间；这是尽力目标，不是商业 SLA。

## Security boundary / 安全边界

- Never attach production credentials or raw customer data to an issue.
- Rotate any credential that was pasted into chat, logs or an artifact.
- Redaction reduces accidental disclosure; it is not a DLP guarantee.
- MCP subprocesses inherit the current user's permissions. Run only trusted
  commands and isolate side effects.
- Baselines are unsigned business expectations unless release provenance is
  explicitly verified. Review every baseline change in version control.

The complete runtime boundary is maintained in
[`docs/limitations.md`](docs/limitations.md).
