// Copyright(C) 2021 Intel Corporation
// SPDX - License - Identifier: MIT

#pragma once

#include <iomanip>
#include <iostream>

#ifdef _WIN32
#include <psapi.h>
#include <windows.h>

#else
#include <stdio.h>
#include <sys/resource.h>
#include <unistd.h>

#endif

namespace ApertureBasicMemUsage {
static size_t GetPeakRSS() {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS info;
  GetProcessMemoryInfo(GetCurrentProcess(), &info, sizeof(info));
  return (size_t)info.PeakWorkingSetSize;

#else
  struct rusage rusage;
  getrusage(RUSAGE_SELF, &rusage);
  return (size_t)(rusage.ru_maxrss * 1024L);
#endif
}

static size_t GetPeakRSSMb() { return GetPeakRSS() >> (size_t)20; }

static size_t GetCurrentRSS() {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS info;
  GetProcessMemoryInfo(GetCurrentProcess(), &info, sizeof(info));
  return (size_t)info.WorkingSetSize;

#else
  long rss = 0L;
  FILE* fp = NULL;
  if ((fp = fopen("/proc/self/statm", "r")) == NULL) {
    // Can't open
    return 0;
  }
  if (fscanf(fp, "%*s%ld", &rss) != 1) {
    fclose(fp);
    // Can't read
    return 0;
  }
  fclose(fp);
  return (size_t)rss * (size_t)sysconf(_SC_PAGESIZE);
#endif
}

static size_t GetCurrentRSSMb() { return GetCurrentRSS() >> (size_t)20; }
};  // namespace ApertureBasicMemUsage
