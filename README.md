# MUSE Pixi Bootstrap

This repository bootstraps a local build environment for MUSE-related
development using a project-local Pixi install. It installs ROOT from
conda-forge and builds XQilla plus the source stack locally.

ROOT is provided by Pixi. XQilla, CLHEP, Geant4, and GenFit are built under
this checkout.

## Supported Platforms

`init.sh` detects the current host and creates a fresh `pixi.toml` for only
that platform:

- `linux-64`
- `linux-aarch64`
- `osx-64`
- `osx-arm64`

Generated environment and build state is intentionally not tracked:

- `pixi.toml`
- `pixi.lock`
- `.pixi/`
- `.local/`
- `.install/src/`
- `.install/build/`
- `.install/state/`

## Quick Start

From a fresh clone:

```bash
./init.sh
.bin/pixi run source-stack
.bin/pixi run verify-source-stack
```

On clusters or network filesystems, use a local Pixi cache before bootstrapping:

```bash
export PIXI_CACHE_DIR=/local/$USER/pixi-cache-$USER
mkdir -p "$PIXI_CACHE_DIR"

./init.sh
.bin/pixi run source-stack
.bin/pixi run verify-source-stack
```

`source-stack` builds CLHEP, Geant4, and GenFit. ROOT is not built from source;
it comes from the Pixi environment.

## Verification

Useful checks after bootstrap:

```bash
.bin/pixi run root-config --version
.bin/pixi run root-config --features
.bin/pixi run xqilla -h
.bin/pixi run source-stack --help
.bin/pixi run verify-source-stack
```

Expected ROOT version:

```text
6.36.10
```

Expected ROOT features include at least:

```text
cxx20 xml gdml
```

## Source Stack

The source-stack configuration lives in `.install/cfgs/source-stack.yml`.

Current source inputs:

- CLHEP `2.4.7.2`
- Geant4 `11.4.1`
- GenFit from `git@github.com:MUSE-EXP/Genfit.git`, pinned by commit SHA

Build and install locations:

- sources: `.install/src`
- builds: `.install/build`
- CLHEP prefix: `.local/clhep`
- Geant4 prefix: `.local/geant4`
- GenFit prefix: `.local/genfit`

After a source-stack build, `.install/state/source-stack.json` contains CMake
hints for downstream MUSE builds, including `CMAKE_PREFIX_PATH`,
`GENFIT_INCLUDE_DIR`, and `GENFIT_LIBRARY`.

## Build Controls

Build the full source stack:

```bash
.bin/pixi run source-stack
```

Build selected components:

```bash
.bin/pixi run source-stack clhep
.bin/pixi run source-stack geant4
.bin/pixi run source-stack genfit
```

Control parallelism explicitly:

```bash
.bin/pixi run source-stack --jobs 8
```

Or cap the automatic job count:

```bash
SOURCE_STACK_AUTO_JOBS_MAX=8 .bin/pixi run source-stack
```

Use a smaller job count on shared cluster nodes if Geant4 fails from memory or
filesystem pressure.

## GenFit Access

GenFit is fetched over SSH:

```text
git@github.com:MUSE-EXP/Genfit.git
```

You need GitHub SSH access to that repository. Check it with:

```bash
ssh -T git@github.com
```

If cloning GenFit fails in CI, configure a `GENFIT_SSH_KEY` secret with a deploy
key or machine-user key that can read the GenFit repository.

## Troubleshooting

If `source-stack` is not registered:

```bash
.bin/pixi run --manifest-path "$PWD/pixi.toml" python \
  "$PWD/.install/python/register_source_stack_pixi.py" --root "$PWD"
```

If Git or SSH reports an OpenSSL version mismatch, run Git/SSH commands without
Pixi dynamic library paths:

```bash
env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH git fetch
```

If Geant4 fails with `fatal error: expat.h: No such file or directory`:

```bash
.bin/pixi add expat
.bin/pixi run source-stack geant4 genfit --jobs 8
```

If CMake prints `CMAKE_HAVE_LIBC_PTHREAD - Failed`, that is not necessarily a
problem. It is harmless if the log later says:

```text
Found Threads: TRUE
```

To recover from stale generated state, remove ignored generated files and rerun
bootstrap:

```bash
rm -rf pixi.toml pixi.lock .pixi .local .install/src .install/build .install/state
./init.sh
```

## Continuous Integration

GitHub Actions should test the supported native platforms:

- `linux-64`
- `linux-aarch64`
- `osx-64`
- `osx-arm64`

Full CI should run `./init.sh`, the ROOT/XQilla checks, `source-stack`, and
`verify-source-stack`. Because GenFit is fetched from a private SSH URL, CI
requires a `GENFIT_SSH_KEY` repository secret when building the full stack.
