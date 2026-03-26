const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const include_dir = std.process.getEnvVarOwned(b.allocator, "LIBCLANG_INCLUDE_PATH") catch
        @panic("LIBCLANG_INCLUDE_PATH not set");
    const lib_dir = std.process.getEnvVarOwned(b.allocator, "LIBCLANG_PATH") catch
        @panic("LIBCLANG_PATH not set");

    const mod = b.createModule(.{
        .root_source_file = b.path("src/purego_gen_zig/main.zig"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
    });
    mod.addIncludePath(.{ .cwd_relative = include_dir });
    mod.addLibraryPath(.{ .cwd_relative = lib_dir });
    mod.linkSystemLibrary("clang", .{});

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
    });
    test_mod.addIncludePath(.{ .cwd_relative = include_dir });
    test_mod.addLibraryPath(.{ .cwd_relative = lib_dir });
    test_mod.linkSystemLibrary("clang", .{});

    const unit_tests = b.addTest(.{
        .root_module = test_mod,
    });

    const run_tests = b.addRunArtifact(unit_tests);
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_tests.step);
}
