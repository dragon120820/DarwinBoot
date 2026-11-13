// SPDX-License-Identifier: BSD-2-Clause-Patent
// Minimal host-only UEFI type shim for compiling the production boot_args header.
#ifndef DARWINBOOT_TEST_BASE_H
#define DARWINBOOT_TEST_BASE_H
#include <stdint.h>
#include <stddef.h>
typedef uint8_t UINT8;
typedef uint16_t UINT16;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef size_t UINTN;
typedef int BOOLEAN;
typedef char CHAR8;
#define STATIC static
#define CONST const
#define VOID void
#define TRUE 1
#define FALSE 0
#define STATIC_ASSERT _Static_assert
#define OFFSET_OF offsetof
#endif
