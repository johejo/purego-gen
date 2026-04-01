const std = @import("std");

const LinkMode = enum {
    static,
    shared,
};

const BuildOptions = struct {
    libclang_include_dir: []const u8,
    libclang_link_dir: []const u8,
    libclang_link_mode: LinkMode,
    llvm_link_dir: []const u8,
    zlib_link_dir: []const u8,
    libcxx_link_dir: []const u8,
};

fn getRequiredOption(
    b: *std.Build,
    comptime T: type,
    name: []const u8,
    description: []const u8,
) T {
    return b.option(T, name, description) orelse
        @panic(std.fmt.allocPrint(
            b.allocator,
            "missing required zig build option -D{s}",
            .{name},
        ) catch "missing required zig build option");
}

fn addAllStaticLibs(mod: *std.Build.Module, dir_path: []const u8) void {
    var dir = std.fs.openDirAbsolute(dir_path, .{ .iterate = true }) catch
        @panic("cannot open lib dir");
    defer dir.close();
    var iter = dir.iterate();
    while (iter.next() catch @panic("dir iteration failed")) |entry| {
        if (entry.kind == .file and std.mem.endsWith(u8, entry.name, ".a")) {
            addSingleStaticLib(mod, dir_path, entry.name);
        }
    }
}

fn addSingleStaticLib(mod: *std.Build.Module, dir_path: []const u8, name: []const u8) void {
    const path = std.fmt.allocPrint(mod.owner.allocator, "{s}/{s}", .{ dir_path, name }) catch @panic("OOM");
    mod.addObjectFile(.{ .cwd_relative = path });
}

fn configureLibclang(mod: *std.Build.Module, opts: BuildOptions) void {
    mod.addIncludePath(.{ .cwd_relative = opts.libclang_include_dir });

    switch (opts.libclang_link_mode) {
        .static => {
            // Link all clang static archives (includes libclang.a with C API + internal libs).
            addAllStaticLibs(mod, opts.libclang_link_dir);

            // Link all LLVM static archives.
            addAllStaticLibs(mod, opts.llvm_link_dir);

            // Link zlib static.
            addSingleStaticLib(mod, opts.zlib_link_dir, "libz.a");

            // Link libc++ static.
            addSingleStaticLib(mod, opts.libcxx_link_dir, "libc++.a");
        },
        .shared => @panic("libclang shared linking is not implemented yet"),
    }
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const opts = BuildOptions{
        .libclang_include_dir = getRequiredOption(
            b,
            []const u8,
            "libclang-include-dir",
            "Path to the libclang headers",
        ),
        .libclang_link_dir = getRequiredOption(
            b,
            []const u8,
            "libclang-link-dir",
            "Path to the libclang link-time libraries",
        ),
        .libclang_link_mode = b.option(
            LinkMode,
            "libclang-link-mode",
            "Link mode for libclang: static or shared",
        ) orelse .static,
        .llvm_link_dir = getRequiredOption(
            b,
            []const u8,
            "llvm-link-dir",
            "Path to the LLVM link-time libraries",
        ),
        .zlib_link_dir = getRequiredOption(
            b,
            []const u8,
            "zlib-link-dir",
            "Path to the zlib link-time libraries",
        ),
        .libcxx_link_dir = getRequiredOption(
            b,
            []const u8,
            "libcxx-link-dir",
            "Path to the libc++ link-time libraries",
        ),
    };

    const mod = b.createModule(.{
        .root_source_file = b.path("src/purego_gen_zig/main.zig"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
        .link_libcpp = true,
    });
    configureLibclang(mod, opts);

    const exe = b.addExecutable(.{
        .name = "purego-gen-zig",
        .root_module = mod,
    });
    b.installArtifact(exe);

    const test_mod = b.createModule(.{
        .root_source_file = b.path("src/purego_gen_zig/main.zig"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
        .link_libcpp = true,
    });
    configureLibclang(test_mod, opts);

    const unit_tests = b.addTest(.{
        .root_module = test_mod,
    });

    const run_tests = b.addRunArtifact(unit_tests);
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_tests.step);
}
