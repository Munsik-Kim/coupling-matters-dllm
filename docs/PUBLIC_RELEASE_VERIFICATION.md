# Public release verification

The canonical Zenodo archive was verified by SHA-256, ZIP CRC, its 349-entry internal manifest, two internal SHA lists, the nested paper-source ZIP, and PDF magic. The GitHub tree is independently covered by `manifests/GITHUB_FILE_MANIFEST.json` and `manifests/GITHUB_SHA256SUMS.txt`.

Run `make verify`, `make test`, and `make paper`. Publication additionally requires a staged-content scan, `git fsck --full`, and a clean-clone repetition of all three commands.
