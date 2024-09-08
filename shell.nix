# shell.nix
let
  pkgs = import <nixpkgs> {};
in pkgs.mkShell {
  packages = [
    (pkgs.python3.withPackages (python-pkgs: [
      (pkgs.callPackage ./pycvc.nix {})
      (pkgs.callPackage ./pypicohsm.nix {})
    ]))
  ];
}
