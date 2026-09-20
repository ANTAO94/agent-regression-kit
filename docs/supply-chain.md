# Release integrity / 发布完整性

Agent Regression Kit release artifacts are built on GitHub-hosted runners. A
tagged release contains the wheel, source archive, `SHA256SUMS`, and an SPDX
2.3 release SBOM. GitHub Actions creates signed SLSA provenance and SBOM
attestations using a short-lived OIDC identity; no long-lived signing key is
stored in the repository.

Agent Regression Kit 的正式版本由 GitHub 托管 Runner 构建。每个 tag 包含 wheel、
源码包、`SHA256SUMS` 和 SPDX 2.3 发布 SBOM。GitHub Actions 使用短期 OIDC
身份生成签名的 SLSA provenance 与 SBOM attestation，仓库不保存长期签名私钥。

## Verify a download / 验证下载文件

First verify its checksum from the release directory:

```bash
sha256sum --check SHA256SUMS
```

On macOS, verify one file with the digest shown in `SHA256SUMS`:

```bash
shasum -a 256 agent_regression_kit-4.5.0-py3-none-any.whl
```

Then use a current GitHub CLI to verify that the artifact was produced by this
repository's signed workflow:

```bash
gh attestation verify \
  agent_regression_kit-4.5.0-py3-none-any.whl \
  --repo ANTAO94/agent-regression-kit \
  --signer-workflow ANTAO94/agent-regression-kit/.github/workflows/release.yml
```

也可以验证整个 GitHub Release：

```bash
gh release verify v4.5.0 --repo ANTAO94/agent-regression-kit
```

Checksum verification detects accidental or malicious byte changes after the
checksum was obtained. Attestation additionally binds the artifact digest to
the GitHub repository and release workflow. Neither mechanism proves that the
source code is bug-free or that a baseline expresses the correct business
expectation.

校验和可以发现文件字节是否变化；attestation 进一步把文件摘要绑定到仓库和发布
工作流。两者都不能证明源码没有缺陷，也不能证明 baseline 的业务期望一定正确。

## SBOM boundary / SBOM 边界

The SPDX document inventories the wheel and source archive produced for this
release. The core package has no mandatory third-party runtime dependency.
Optional framework extras are installed by consumers and must be inventoried
in the consuming application's own environment SBOM.

SPDX 文档清点本次发布生成的 wheel 和源码包。核心包没有必需的第三方运行时依赖；
可选框架依赖由使用方安装，应进入使用方自己的环境 SBOM。
