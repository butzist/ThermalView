# TODO

Living progress log for the ThermalView RE effort.

## Environment

- [x] Create `flake.nix` with RE toolchain (Ghidra, JDK, Android tools, Frida, ...)
- [x] `nix flake lock` (nixpkgs-unstable, `1d060086d60c`)
- [x] Verify `nix develop` builds and tools run
- [x] Add `.gitignore` + `git init` + initial commit
- [x] Pin Ghidra to 12.1.4 (`nixpkgs-ghidra` input, `ghidra-bin`) so the REA
      MCP Ghidra provider binds; JDK 21 is enough (12.1.4 declares
      `application.java.min=21`, 12.2 declares `min=25`)
- [x] `rea doctor`: all `ghidra*` checks healthy on 12.1.4 + JDK 21
- [ ] Restart the MCP client after the Ghidra pin so REA re-reads `GHIDRA_HOME`
- [ ] Optional: `wireshark` GUI, `objection` (via venv) if needed
- [ ] Optional: `REA_JADX_MCP_JAR` (jadx-headless-mcp 0.7.1) to decompile Java
      through REA instead of the `jadx` CLI

Notes:

- `cutter` is not installed and not needed: it is a Qt GUI over rizin, and
  REA's `cutter_command` only attaches to a user-started Cutter. rizin/radare2
  CLI + Ghidra cover the same ground.

## Triage

- [x] Extract `AndroidManifest.xml` (decoded) and note permissions, services,
      exported components, SDK levels
      -> `com.ruiqi.hongwai` 1.1 (code 1), minSdk 21, targetSdk 34,
      USB host required, CAMERA + INTERNET, `MainActivity` exported,
      app class `com.ruiqi.hongwai.MyApplication`
- [x] Decompile `classes.dex` with jadx into `out/jadx/` (2904 `.java`)
- [x] Decode resources with apktool (via REA `decode_android_resources`):
      92 locales, 202 default strings, 1103 decoded files
- [x] Extract APK contents to `out/apk/` (REA `extract_artifact`, 22 MB)
- [x] List JNI entry points (`Java_*`) in `libhongwai.so`
      -> 7 exports, all on `com.ruiqi.hongwai.JniPicData`: `initJNI`,
      `setGlobalObject`, `setColorType`, `setTempType`, `setAxisSwitch`,
      `signalData`, `stringFromJNI`
- [x] Decompile all 7 JNI functions (Ghidra 12.1.4,
      `scripts/ghidra/DecompileFunctions.java`)
- [ ] Identify third-party SDKs / protocol libraries
- [ ] Locate network endpoints, ports, and protocols (strings + code)
- [ ] Locate thermal frame format / image decoding path
- [ ] Map `JniResultCall` callbacks back into the Java layer

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
