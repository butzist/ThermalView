# TODO

Living progress log for the ThermalView RE effort.

## Environment

- [x] Create `flake.nix` with RE toolchain (Ghidra, JDK, Android tools, Frida, ...)
- [x] `nix flake lock` (nixpkgs-unstable, `1d060086d60c`)
- [ ] Verify `nix develop` builds and tools run
- [ ] Add `.gitignore` + `git init` + initial commit
- [ ] Optional: add `wireshark` GUI, `objection` (via venv) if needed

## Triage

- [ ] Extract `AndroidManifest.xml` (decoded) and note permissions, services,
      exported components, SDK levels
- [ ] Decompile `classes.dex` with jadx into `out/jadx/`
- [ ] Decode resources with apktool into `out/apktool/`
- [ ] List JNI entry points (`Java_*` symbols) in `libhongwai.so`
- [ ] Identify third-party SDKs / protocol libraries
- [ ] Locate network endpoints, ports, and protocols (strings + code)
- [ ] Locate thermal frame format / image decoding path

## Static analysis

- [ ] Map Kotlin/Java call graph around camera/thermal classes
- [ ] Ghidra project for `libhongwai.so` (ARM64), analyze JNI exports
- [ ] Cross-reference native functions with Java `native` declarations
- [ ] Document image/frame structure and any crypto/obfuscation

## Dynamic analysis (optional, needs device)

- [ ] `adb devices`, install APK on test device
- [ ] `frida-ps -U`, hook native + Java entry points
- [ ] Capture traffic (`tshark`/`mitmproxy`) while app runs
- [ ] Document protocol / command set

## Deliverables

- [ ] `notes/` write-up of findings (protocol, frame format, key functions)
- [ ] Reusable scripts in `scripts/`
