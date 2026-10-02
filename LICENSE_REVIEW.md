# License review — 2026-10-02


## Owner-approved recipe license

On October 2, 2026, the code owner explicitly approved MIT for newly authored recipe, wrapper, application and test code. `LICENSE` records that narrow scope. Upstream components are not relicensed: all original notices, corresponding-source/network-use obligations, enterprise exceptions and artwork/trademark terms remain applicable. This approval resolves the authored-code license hold only; it does not close the artifact or behavioral publication gates.

- Pinned [OpenBao v2.7.1 license](https://github.com/openbao/openbao/blob/v2.7.1/LICENSE): Mozilla Public License 2.0; redistribution of unchanged upstream binaries is distinct from HashiCorp Vault's BSL. The Dockerfile copies the shipped `/licenses/mozilla.txt` into `/licenses/openbao-MPL-2.0.txt` and leaves the upstream binary unchanged. Preserve notices and source availability for MPL-covered files; modifications to those files require appropriate source disclosure.
- Source/tag: [OpenBao 2.7.1](https://github.com/openbao/openbao/tree/v2.7.1), [upstream Dockerfile](https://github.com/openbao/openbao/blob/v2.7.1/Dockerfile). Latest release lookup on this date returned `v2.7.1` published October 1, 2026. Registry digest was observed by local `docker pull`, not guessed.
- [CPython license](https://docs.python.org/3/license.html), [official Python container source](https://github.com/docker-library/python) and Alpine packages have their own notices. The recipe does not claim the entire image is uniformly MPL. No pip dependencies are introduced; OS/SBOM/transitive notice and vulnerability audits remain release gates.
- Main-product [OpenBao artwork](https://github.com/openbao/artwork) is [CC BY 4.0](https://github.com/openbao/artwork/blob/main/LICENSE). Metadata uses the OpenBao single-color-square mark, not a supporting product/vendor icon. Attribute OpenBao artwork when publishing; an icon URL is not an endorsement or a grant of broader trademark rights.

This is an engineering license inventory, not legal advice or a completed artifact/transitive compliance audit. Hosting rights and notices must be rechecked for any changed artifact or distribution.
