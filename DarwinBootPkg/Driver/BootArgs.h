// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef DARWIN_BOOT_ARGS_H_
#define DARWIN_BOOT_ARGS_H_

#include <Base.h>
#include <Library/BaseMemoryLib.h>

// Explicit little-endian wire layouts. Revision and Version are 2 in both ABIs.
typedef struct {
  UINT16  Revision;
  UINT16  Version;
  UINT32  Padding;
  UINT64  VirtualBase;
  UINT64  PhysicalBase;
  UINT64  MemorySize;
  UINT64  TopOfKernelData;
  UINT64  Video[6];
  UINT32  MachineType;
  UINT32  TreePadding;
  UINT64  DeviceTree;
  UINT32  DeviceTreeLength;
  CHAR8   CommandLine[608];
  UINT32  FlagsPadding;
  UINT64  BootFlags;
  UINT64  MemorySizeActual;
} DARWIN22_BOOT_ARGS;

typedef struct {
  UINT16  Revision;
  UINT16  Version;
  UINT32  Padding;
  UINT64  VirtualBase;
  UINT64  PhysicalBase;
  UINT64  MemorySize;
  UINT64  TopOfKernelData;
  UINT64  Video[6];
  UINT32  MachineType;
  UINT32  TreePadding;
  UINT64  DeviceTree;
  UINT32  DeviceTreeLength;
  CHAR8   CommandLine[1024];
  UINT32  FlagsPadding;
  UINT64  BootFlags;
  UINT64  MemorySizeActual;
} DARWIN23_BOOT_ARGS;

// Keep the maximum allocation and shared-prefix access used by the loader.
// Never access its tail fields directly: their offsets depend on the selector.
typedef DARWIN23_BOOT_ARGS DARWIN_BOOT_ARGS;

STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, Video) == 0x28, "Darwin22 video ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, DeviceTree) == 0x60, "Darwin22 DT ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, DeviceTreeLength) == 0x68, "Darwin22 DT length ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, CommandLine) == 0x6c, "Darwin22 command line ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, BootFlags) == 0x2d0, "Darwin22 flags ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN22_BOOT_ARGS, MemorySizeActual) == 0x2d8, "Darwin22 memory ABI");
STATIC_ASSERT (sizeof (DARWIN22_BOOT_ARGS) == 0x2e0, "Darwin22 boot_args ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, Video) == 0x28, "Darwin23 video ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, DeviceTree) == 0x60, "Darwin23 DT ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, DeviceTreeLength) == 0x68, "Darwin23 DT length ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, CommandLine) == 0x6c, "Darwin23 command line ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, BootFlags) == 0x470, "Darwin23 flags ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN23_BOOT_ARGS, MemorySizeActual) == 0x478, "Darwin23 memory ABI");
STATIC_ASSERT (sizeof (DARWIN23_BOOT_ARGS) == 0x480, "Darwin23 boot_args ABI");

STATIC inline
BOOLEAN
DarwinCommandLineSizeValid (UINT32 Size)
{
  return (Size == 608) || (Size == 1024);
}

// Bounded check, including the NUL: never truncate a selected wire command line.
STATIC inline
BOOLEAN
DarwinCommandLineFits (CONST CHAR8 *CommandLine, UINT32 Size)
{
  UINTN Index;

  if (!DarwinCommandLineSizeValid (Size)) { return FALSE; }
  for (Index = 0; Index < Size; Index++) {
    if (CommandLine[Index] == 0) { return TRUE; }
    if ((UINT8)CommandLine[Index] > 0x7f) { return FALSE; }
  }
  return FALSE;
}

STATIC inline
UINTN
DarwinBootFlagsOffset (UINT32 CommandLineSize)
{
  return (CommandLineSize == 608) ? OFFSET_OF (DARWIN22_BOOT_ARGS, BootFlags) : OFFSET_OF (DARWIN23_BOOT_ARGS, BootFlags);
}

STATIC inline
VOID
DarwinBootArgsSetMemory (DARWIN_BOOT_ARGS *Args, UINT32 CommandLineSize, UINT64 Usable)
{
  UINT64 Flags;
  UINT64 Actual;
  UINTN  Offset;

  // 8796 subtracts memSize from a nonzero actual using unsigned arithmetic.
  // Preserve its native fallback (zero), not the possibly smaller usable count.
  Flags = 0;
  Actual = (CommandLineSize == 608) ? 0 : Usable;
  Offset = DarwinBootFlagsOffset (CommandLineSize);
  CopyMem ((UINT8 *)Args + Offset, &Flags, sizeof (Flags));
  CopyMem ((UINT8 *)Args + Offset + sizeof (Flags), &Actual, sizeof (Actual));
}

STATIC inline
UINT64
DarwinBootArgsGetFlags (CONST DARWIN_BOOT_ARGS *Args, UINT32 CommandLineSize)
{
  UINT64 Flags;

  CopyMem (&Flags, (CONST UINT8 *)Args + DarwinBootFlagsOffset (CommandLineSize), sizeof (Flags));
  return Flags;
}

STATIC inline
UINT64
DarwinBootArgsGetActual (CONST DARWIN_BOOT_ARGS *Args, UINT32 CommandLineSize)
{
  UINT64 Actual;

  CopyMem (&Actual, (CONST UINT8 *)Args + DarwinBootFlagsOffset (CommandLineSize) + sizeof (UINT64), sizeof (Actual));
  return Actual;
}

#endif
