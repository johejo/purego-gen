const std = @import("std");

fn getEnvVar(allocator: std.mem.Allocator, comptime key: []const u8) []const u8 {
    return std.process.getEnvVarOwned(allocator, key) catch
        @panic(key ++ " not set");
}

fn addAllStaticLibs(mod: *std.Build.Module, dir_path: []const u8) void {
    var dir = std.fs.openDirAbsolute(dir_path, .{ .iterate = true }) catch
        @panic("cannot open lib dir");
    defer dir.close();
    var iter = dir.iterate();
    while (iter.next() catch @panic("dir iteration failed")) |entry| {
        if (entry.kind == .file and std.mem.endsWith(u8, entry.name, ".a")) {
            const path = std.fmt.allocPrint(mod.owner.allocator, "{s}/{s}", .{ dir_path, entry.name }) catch @panic("OOM");
            mod.addObjectFile(.{ .cwd_relative = path });
        }
    }
}

fn addSingleStaticLib(mod: *std.Build.Module, dir_path: []const u8, name: []const u8) void {
    const path = std.fmt.allocPrint(mod.owner.allocator, "{s}/{s}", .{ dir_path, name }) catch @panic("OOM");
    mod.addObjectFile(.{ .cwd_relative = path });
}

fn configureStaticClang(mod: *std.Build.Module, env: EnvPaths) void {
    mod.addIncludePath(.{ .cwd_relative = env.include_dir });

    // Link all clang static archives (includes libclang.a with C API + internal libs).
    addAllStaticLibs(mod, env.clang_static_dir);

    // Link all LLVM static archives.
    addAllStaticLibs(mod, env.llvm_lib_dir);

    // Link zlib static.
    addSingleStaticLib(mod, env.zlib_static_dir, "libz.a");
}

const EnvPaths = struct {
    include_dir: []const u8,
    clang_static_dir: []const u8,
    llvm_lib_dir: []const u8,
    zlib_static_dir: []const u8,
};

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const env = EnvPaths{
        .include_dir = getEnvVar(b.allocator, "LIBCLANG_INCLUDE_PATH"),
        .clang_static_dir = getEnvVar(b.allocator, "LIBCLANG_STATIC_PATH"),
        .llvm_lib_dir = getEnvVar(b.allocator, "LLVM_LIB_PATH"),
        .zlib_static_dir = getEnvVar(b.allocator, "ZLIB_STATIC_PATH"),
    };

    const mod = b.createModule(.{
        .root_source_file = b.path("src/purego_gen_zig/main.zig"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
        .link_libcpp = true,
    });
    configureStaticClang(mod, env);

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
    configureStaticClang(test_mod, env);

    const unit_tests = b.addTest(.{
        .root_module = test_mod,
    });

    const run_tests = b.addRunArtifact(unit_tests);
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_tests.step);
}
