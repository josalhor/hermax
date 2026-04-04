cmake_minimum_required(VERSION 3.5 FATAL_ERROR)

project(uwrmaxsat)

#--------------------------------------------------------------------------------------------------
# Configurable options:

option(STATIC_BINARIES "Link binaries statically." ON)
option(USE_SORELEASE   "Use SORELEASE in shared library filename." ON)

#--------------------------------------------------------------------------------------------------
# Library version:

set(MINISATP_SOMAJOR   1)
set(MINISATP_SOMINOR   1)
set(MINISATP_SORELEASE 0)

# Compute VERSION and SOVERSION:
if(USE_SORELEASE)
  set(MINISATP_VERSION ${MINISATP_SOMAJOR}.${MINISATP_SOMINOR}.${MINISATP_SORELEASE})
else()
  set(MINISATP_VERSION ${MINISATP_SOMAJOR}.${MINISATP_SOMINOR})
endif()
set(MINISATP_SOVERSION ${MINISATP_SOMAJOR})

#--------------------------------------------------------------------------------------------------
# Compile flags:

add_definitions(-include Global.h -include Main.h -D_FILE_OFFSET_BITS=64)

# We require C++11 or higher.

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

#--------------------------------------------------------------------------------------------------
# Dependencies:

find_library(GMP_LIBRARY gmp)
#include_directories(${GMP_INCLUDE_DIR})
# find_library(MINISAT_LIB_STATIC _release PATH ${minisat_SOURCE_DIR}/simp)

include_directories(${minisat_SOURCE_DIR})
include_directories(${minisatp_SOURCE_DIR})
include_directories(${minisatp_SOURCE_DIR}/ADTs)

#--------------------------------------------------------------------------------------------------
# Build Targets:
# --- sources ---
set(MINISATP_LIB_SOURCES
    ADTs/FEnv.cc
    ADTs/File.cc
    ADTs/Global.cc
    Debug.cc
    Hardware_adders.cc
    Hardware_clausify.cc
    Hardware_sorters.cc
    Main.cc
    PbParser.cc
    PbSolver.cc
    PbSolver_convert.cc
    PbSolver_convertAdd.cc
    PbSolver_convertBdd.cc
    PbSolver_convertSort.cc
    MsSolver.cc
    SatSolver.cc
    System.cc
)

get_property(all_targets DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY BUILDSYSTEM_TARGETS)
message(STATUS "DEBUG1: Targets so far: ${all_targets}")


# --- define libraries ---
add_library(minisatp-lib-static STATIC ${MINISATP_LIB_SOURCES})
add_library(minisatp-lib-shared SHARED ${MINISATP_LIB_SOURCES})

# --- set properties ---
set_target_properties(minisatp-lib-static PROPERTIES OUTPUT_NAME "uwrmaxsat")
set_target_properties(minisatp-lib-shared PROPERTIES
    OUTPUT_NAME "uwrmaxsat"
    VERSION ${MINISATP_VERSION}
    SOVERSION ${MINISATP_SOVERSION}
)

get_property(all_targets DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY BUILDSYSTEM_TARGETS)
message(STATUS "DEBUG2: Targets so far: ${all_targets}")

# --- safe linking (must be after the add_library!) ---
# if(TARGET minisat-lib-shared)
#     target_link_libraries(minisatp-lib-shared PRIVATE minisat-lib-shared ${GMP_LIBRARY})
# elseif(EXISTS "${minisat_SOURCE_DIR}/simp/libminisat.a")
#     target_link_libraries(minisatp-lib-shared PRIVATE "${minisat_SOURCE_DIR}/simp/libminisat.a" ${GMP_LIBRARY})
# else()
#     message(WARNING "Minisat static/shared library not found — linking only against GMP.")
#     target_link_libraries(minisatp-lib-shared PRIVATE ${GMP_LIBRARY})
# endif()

# --- safe linking (must be after the add_library!) ---
if (USE_CADICAL)
    # CaDiCaL path: uwrmaxsat code will include CadicalWrap.
    # Do NOT link minisat here.
    target_link_libraries(minisatp-lib-shared PRIVATE ${GMP_LIBRARY})
else()
    if (TARGET minisat-lib-shared)
        target_link_libraries(minisatp-lib-shared PRIVATE minisat-lib-shared ${GMP_LIBRARY})
    elseif(EXISTS "${minisat_SOURCE_DIR}/simp/libminisat.a")
        target_link_libraries(minisatp-lib-shared PRIVATE "${minisat_SOURCE_DIR}/simp/libminisat.a" ${GMP_LIBRARY})
    else()
        message(WARNING "Minisat static/shared library not found — linking only against GMP.")
        target_link_libraries(minisatp-lib-shared PRIVATE ${GMP_LIBRARY})
    endif()
endif()

target_link_libraries(minisatp-lib-static PRIVATE ${GMP_LIBRARY})


# --- executable ---
add_executable(uwrmaxsat Main.cc)
target_link_libraries(uwrmaxsat PRIVATE minisatp-lib-static)

if(NOT STATIC_BINARIES)
    target_link_libraries(uwrmaxsat PRIVATE minisatp-lib-shared)
endif()


#--------------------------------------------------------------------------------------------------
# Installation targets:
