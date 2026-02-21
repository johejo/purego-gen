{ pkgs, ... }:
{
  projectRootFile = "flake.nix";

  settings.global.excludes = [
    ".direnv/**"
    ".git/**"
    ".venv/**"
    "build/**"
    "dist/**"
  ];

  settings.formatter.nix = {
    command = "${pkgs.nixfmt}/bin/nixfmt";
    includes = [ "*.nix" ];
  };

  settings.formatter.python = {
    command = "${pkgs.uv}/bin/uv";
    options = [
      "run"
      "ruff"
      "format"
    ];
    includes = [ "*.py" ];
  };

  settings.formatter.go = {
    command = "${pkgs.go}/bin/gofmt";
    options = [ "-w" ];
    includes = [ "*.go" ];
  };

  settings.formatter.shell = {
    command = "${pkgs.shfmt}/bin/shfmt";
    options = [ "-w" ];
    includes = [ "scripts/*.sh" ];
  };

  settings.formatter.c_header = {
    command = "${pkgs.clang-tools}/bin/clang-format";
    options = [
      "-i"
      "--style=file"
    ];
    includes = [ "tests/fixtures/*.h" ];
  };

  settings.formatter.jinja_template = {
    command = "${pkgs.zsh}/bin/zsh";
    options = [
      "-c"
      "PATH=${
        pkgs.lib.makeBinPath [
          pkgs.coreutils
          pkgs.diffutils
          pkgs.uv
        ]
      }:$PATH scripts/format-template-go.sh \"$@\""
      "--"
    ];
    includes = [ "templates/*.j2" ];
  };
}
