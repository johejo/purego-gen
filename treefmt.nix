{ pkgs, ... }:
let
  lib = pkgs.lib;
in
{
  projectRootFile = "flake.nix";

  programs = {
    zig = {
      enable = true;
    };
  };

  settings.global.excludes = [
    ".direnv/**"
    ".git/**"
    ".venv/**"
    "build/**"
    "dist/**"
  ];

  settings.formatter.nix = {
    command = lib.getExe pkgs.nixfmt;
    includes = [ "*.nix" ];
  };

  settings.formatter.python = {
    command = lib.getExe pkgs.ruff;
    options = [ "format" ];
    includes = [ "*.py" ];
  };

  settings.formatter.go = {
    command = "${pkgs.go}/bin/gofmt";
    options = [ "-w" ];
    includes = [ "*.go" ];
  };

  settings.formatter.shell = {
    command = lib.getExe pkgs.shfmt;
    options = [ "-w" ];
    includes = [ "scripts/*.sh" ];
  };

  settings.formatter.c = {
    command = "${pkgs.clang-tools}/bin/clang-format";
    options = [
      "-i"
      "--style=file"
    ];
    includes = [
      "tests/fixtures/*.h"
      "tests/fixtures/*.c"
      "tests/cases/**/*.h"
      "tests/cases/**/*.c"
    ];
  };

  settings.formatter.jinja_template = {
    command = lib.getExe pkgs.bash;
    options = [
      "-c"
      "PATH=${
        lib.makeBinPath [
          pkgs.coreutils
          pkgs.diffutils
          pkgs.djlint
        ]
      }:$PATH ${lib.getExe pkgs.bash} scripts/format-template-go.sh \"$@\""
      "--"
    ];
    includes = [ "templates/*.j2" ];
  };
}
