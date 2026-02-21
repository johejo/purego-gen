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
}
