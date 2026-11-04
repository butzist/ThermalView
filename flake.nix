{
  description = "ThermalView APK reverse-engineering environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    systems = ["x86_64-linux"];
    forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
  in {
    devShells = forAllSystems (
      pkgs: let
        python = pkgs.python3.withPackages (
          ps:
            with ps; [
              androguard
              capstone
              keystone-engine
              lief
              pycryptodome
              pyelftools
              pwntools
              requests
              rich
              unicorn
            ]
        );
      in {
        default = pkgs.mkShell {
          packages = with pkgs; [
            # --- Java / decompilers -------------------------------------------------
            jdk21
            ghidra # includes Ghidra's own JDK, `ghidra` + `ghidra-analyzeHeadless`
            jadx # dex -> java
            apktool # resources + smali
            dex2jar
            procyon
            cfr
            bytecode-viewer

            # --- native / disassembly ----------------------------------------------
            radare2
            rizin
            gdb
            gef # GDB plugin, `gef` in gdb
            lldb
            binutils # objdump, readelf, strings, nm, ...
            patchelf
            rr

            # --- Android tooling ----------------------------------------------------
            android-tools # adb, fastboot, etc.
            aapt
            apksigner
            bundletool
            apkid
            scrcpy

            # --- dynamic instrumentation -------------------------------------------
            frida-tools # frida, frida-ps, frida-trace, ...
            jnitrace
            python
            strace
            ltrace
            lsof
            socat
            netcat-gnu

            # --- traffic / protocol analysis ---------------------------------------
            mitmproxy
            tshark
            tcpdump
            nmap
            openssl

            # --- misc utilities -----------------------------------------------------
            binwalk
            ghex
            diffoscope
            file
            xxd
            unzip
            zip
            jq
            ripgrep
            fd
            tree
            less
            git
            curl
            wget
          ];

          shellHook = ''
            export JAVA_HOME="${pkgs.jdk21.home}"
            export GHIDRA_HOME="${pkgs.ghidra}/lib/ghidra"

            echo "ThermalView RE shell"
            echo "  java:    $JAVA_HOME/bin/java"
            echo "  ghidra:  $GHIDRA_HOME (ghidra, ghidra-analyzeHeadless)"
            echo "  apk:     jadx, apktool, apkid, dex2jar"
            echo "  android: adb, fastboot, aapt, apksigner, bundletool"
            echo "  dynamic: frida, objection, jnitrace, gdb/gef, lldb"
            echo "  net:     mitmproxy, tshark, nmap"
          '';
        };
      }
    );

    formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
  };
}
