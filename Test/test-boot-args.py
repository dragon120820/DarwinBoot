#!/usr/bin/env python3
"""Compile real wire layouts, accessors, initialization and DescribeWindow; replay changing EBS maps."""
from pathlib import Path
import subprocess
import tempfile

here = Path(__file__).resolve().parent
driver = here.parent / 'DarwinBootPkg/Driver'
source = (driver / 'DarwinBoot.c').read_text()
describe = source[source.index('STATIC\nBOOLEAN\nDescribeWindow ('):source.index('// The entry argument')]
initialization = source[source.index('  Args->MemorySize = WindowSize;'):source.index('  Args->TopOfKernelData =')]
command_copy = '  CopyMem (Args->CommandLine, CommandLine, CommandLineSize);'
assert command_copy in source
# Supplemental call-site audit, not a substitute for the compiled runtime tests below.
assert 'Args->MemorySizeActual' not in source and 'Args->BootFlags' not in source
assert source.count('!DescribeWindow (') == 2
assert source.count('ExcludedCapacity, Args, CommandLineSize, &Usable, &ExcludedCount)') == 2
retry = source[source.rindex('  for (Attempt = 0; Attempt < 3; Attempt++)'):source.index('    Status = gBS->ExitBootServices')]
assert retry.index('gBS->GetMemoryMap') < retry.index('!DescribeWindow (')
# Compile the production retry loop's GetMemoryMap, DescribeWindow and EBS call.
# Unrelated outside-window/input-record blocks are separately covered by their tests.
retry_core = (retry[:retry.index('    // No boot service')]
              + retry[retry.index('    if ((Excluded != NULL) &&'):]
              + '    Status = gBS->ExitBootServices (mImage, Key);\n'
              + '    if (!EFI_ERROR (Status)) { break; }\n  }\n')

preamble = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "BootArgs.h"
#define MAX_UINT64 UINT64_MAX
#define EFI_PAGE_SIZE 4096
#define SIZE_2MB 0x200000
#define ALIGN_VALUE(a,b) (((a)+(b)-1)&~((b)-1))
enum { EfiReservedMemoryType, EfiLoaderCode, EfiLoaderData, EfiBootServicesCode, EfiBootServicesData,
       EfiRuntimeServicesCode, EfiRuntimeServicesData, EfiConventionalMemory };
typedef struct { UINT32 Type; UINT64 PhysicalStart; UINT64 VirtualStart; UINT64 NumberOfPages; UINT64 Attribute; } EFI_MEMORY_DESCRIPTOR;
static UINT64 ReadUnaligned64(const UINT64 *p) { UINT64 v; memcpy(&v, p, 8); return v; }
static void WriteUnaligned64(UINT64 *p, UINT64 v) { memcpy(p, &v, 8); }
#include "MemoryWindow.h"
'''
main = r'''
static UINT64 raw(const DARWIN_BOOT_ARGS *args, size_t at) {
  UINT64 value; memcpy(&value, (const UINT8 *)args + at, 8); return value;
}
static void check_tail(const DARWIN_BOOT_ARGS *args, UINT32 size, UINT64 usable, UINT64 window) {
  UINT64 actual = DarwinBootArgsGetActual(args, size);
  assert(args->MemorySize == window);
  assert(DarwinBootArgsGetFlags(args, size) == 0);
  assert(actual == (size == 608 ? 0 : usable));
  if (size == 608) {
    assert(raw(args, 0x2d0) == 0 && raw(args, 0x2d8) == 0);
    // A sentinel proves even repeated setters never write the old 23 tail.
    assert(raw(args, 0x470) == UINT64_C(0xa5a5a5a5a5a5a5a5));
    assert(raw(args, 0x478) == UINT64_C(0xa5a5a5a5a5a5a5a5));
    // Model 8796 ml_get_booter_memory_size: zero selects its native fallback;
    // no unsigned (usable - memSize) is evaluated when usable is smaller.
    UINT64 extra = actual ? actual - args->MemorySize : 0;
    assert(extra == 0);
  } else {
    assert(raw(args, 0x478) == usable && raw(args, 0x470) == 0);
  }
}
#define EFI_ERROR(status) ((status) != 0)
#define EFI_LOAD_ERROR 1
static void CpuDeadLoop(void) { assert(0 && "unexpected dead loop"); }
static unsigned map_calls, ebs_calls;
static DARWIN_BOOT_ARGS *observed_args;
static UINT32 observed_size;
static UINT64 *observed_usable;
static int get_map(UINTN *size, EFI_MEMORY_DESCRIPTOR *map, UINTN *key, UINTN *stride, UINT32 *version) {
  assert(*size >= 3 * sizeof(*map));
  ++map_calls;
  assert(map_calls <= 3);
  map[0] = (EFI_MEMORY_DESCRIPTOR){ EfiLoaderData, 0x100000, 0, 0x100, 0 };
  map[1] = (EFI_MEMORY_DESCRIPTOR){ EfiConventionalMemory, 0x200000, 0, 0x100 * (map_calls + 1), 0 };
  map[2] = (EFI_MEMORY_DESCRIPTOR){ EfiReservedMemoryType, 0x200000 + 0x100000 * (map_calls + 1), 0, 0x100 * (14 - map_calls), 0 };
  *size = 3 * sizeof(*map); *key = map_calls; *stride = sizeof(*map); *version = 1;
  return 0;
}
static int exit_services(void *image, UINTN key) {
  (void)image;
  ++ebs_calls;
  assert(key == map_calls && key == ebs_calls);
  assert(*observed_usable == UINT64_C(0x100000) * (map_calls + 2));
  check_tail(observed_args, observed_size, *observed_usable, 0x1000000);
  return ebs_calls < 3 ? 1 : 0;
}
static struct { int (*GetMemoryMap)(UINTN *, EFI_MEMORY_DESCRIPTOR *, UINTN *, UINTN *, UINT32 *);
                int (*ExitBootServices)(void *, UINTN); } services = {get_map, exit_services}, *gBS = &services;
static void *mImage;
int main(void) {
  assert(sizeof(DARWIN22_BOOT_ARGS) == 0x2e0 && sizeof(DARWIN23_BOOT_ARGS) == 0x480);
  char command[1025];
  for (unsigned size = 608; size <= 1024; size += 416) {
    memset(command, 'a', sizeof(command)); command[size - 1] = 0;
    assert(DarwinCommandLineFits(command, size));
    command[size - 1] = 'a'; command[size] = 0;
    assert(!DarwinCommandLineFits(command, size));
    command[0] = (char)0x80; command[1] = 0;
    assert(!DarwinCommandLineFits(command, size));
  }
  assert(!DarwinCommandLineFits("", 607));
  assert(!DarwinCommandLineFits("", 1025));
  for (UINT32 CommandLineSize = 608; CommandLineSize <= 1024; CommandLineSize += 416) {
    DARWIN_BOOT_ARGS buffer;
    DARWIN_BOOT_ARGS *Args = &buffer;
    UINT64 WindowSize = 0x1000000, Usable = 0;
    UINT8 table[16 * 4]; UINTN count;
    CHAR8 CommandLine[1024];
    memset(CommandLine, 0, sizeof(CommandLine));
    memset(CommandLine, 'b', CommandLineSize - 1);
    memset(Args, 0xa5, sizeof(*Args));
    // This is the production initialization and selected-size command copy.
    INITIALIZATION
    COMMAND_COPY
    check_tail(Args, CommandLineSize, WindowSize, WindowSize);
    assert(Args->CommandLine[CommandLineSize - 1] == 0);
    // Initial DescribeWindow plus three retry-like map replays. This unit test
    // executes the real statistics/setter path, not firmware ExitBootServices.
    for (unsigned pass = 0; pass < 4; ++pass) {
      EFI_MEMORY_DESCRIPTOR map[] = {
        { EfiLoaderData, 0x100000, 0, 0x100, 0 },
        { EfiConventionalMemory, 0x200000, 0, 0x100 * (pass + 1), 0 },
        { EfiReservedMemoryType, 0x200000 + 0x100000 * (pass + 1), 0, 0x100 * (14 - pass), 0 }
      };
      assert(DescribeWindow(map, sizeof(map), sizeof(map[0]), 0x100000,
                            WindowSize, 0x100000, table, 4, Args, CommandLineSize, &Usable, &count));
      assert(Usable == UINT64_C(0x100000) * (pass + 2));
      assert(count == 1);
      assert(DarwinRangeBase(table, 0) == 0x100000 + Usable);
      assert(DarwinRangeSize(table, 0) == WindowSize - Usable);
      check_tail(Args, CommandLineSize, Usable, WindowSize);
    }
    // Replay the actual production retry core: two stale keys then success.
    // Every mocked EBS call validates the newly encoded tail and independent usable count.
    EFI_MEMORY_DESCRIPTOR Map[3];
    UINTN Capacity = sizeof(Map), MapSize, Key, Stride, Attempt, ExcludedCount = count;
    UINT32 Version;
    UINT64 Address = 0x100000, HeadSize = 0x100000;
    UINT8 *Excluded = table;
    UINTN ExcludedCapacity = 4;
    int Status = 0;
    map_calls = ebs_calls = 0;
    observed_args = Args; observed_size = CommandLineSize; observed_usable = &Usable;
    RETRY_CORE
    assert(Status == 0 && Attempt == 2 && map_calls == 3 && ebs_calls == 3);
    assert(ExcludedCount == 1);
    assert(DarwinRangeSize(table, 0) == WindowSize - Usable);
    goto RetryDone;
  Fail:
    assert(0 && "unexpected retry failure");
  RetryDone:
    ;
    // A lost head is rejected without pretending it has a new usable count.
    EFI_MEMORY_DESCRIPTOR broken = { EfiReservedMemoryType, 0x100000, 0, 0x1000, 0 };
    assert(!DescribeWindow(&broken, sizeof(broken), sizeof(broken), 0x100000,
                           WindowSize, 0x100000, table, 4, Args, CommandLineSize, &Usable, &count));
    check_tail(Args, CommandLineSize, Usable, WindowSize);
  }
  puts("PASS: real C ABI offsets/sizes; 607/608 and 1023/1024 boundaries; initialization + changing-map DescribeWindow + production EBS retry core (2 stale keys, then success); zero 22 fallback, untouched 23 tail, updated 23 actual, unchanged memSize");
}
'''.replace('INITIALIZATION', initialization).replace('COMMAND_COPY', command_copy).replace('RETRY_CORE', retry_core)
with tempfile.TemporaryDirectory(prefix='darwinboot-args-') as temporary:
    work = Path(temporary)
    (work / 'test.c').write_text(preamble + describe + main)
    subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                    '-fsanitize=undefined,address', '-fno-sanitize-recover=all',
                    '-I', str(here / 'Host'), '-I', str(driver), str(work / 'test.c'), '-o', str(work / 'test')], check=True)
    subprocess.run([str(work / 'test')], check=True)
print('PASS: source audit: initialization helper, both DescribeWindow sites, GetMemoryMap before retry update; no direct tail accesses')
