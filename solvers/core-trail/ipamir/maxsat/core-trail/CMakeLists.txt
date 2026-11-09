cmake_minimum_required(VERSION 3.15)
project(coretrail_native LANGUAGES CXX)

set(CORETRAIL_CORE_SOURCES
  src/core/coretrail_solver.cc
  src/core/glucose_backend.cc
  third_party/glucose-syrup-4.1/core/Solver.cc
  third_party/glucose-syrup-4.1/utils/Options.cc
  third_party/glucose-syrup-4.1/utils/System.cc)

if(HERMAX_CORE_ARCHIVE)
  add_library(coretrail_core STATIC IMPORTED GLOBAL)
  set_target_properties(coretrail_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
  add_library(coretrail_core STATIC ${CORETRAIL_CORE_SOURCES})
endif()

if(NOT HERMAX_CORE_ARCHIVE)
  target_compile_features(coretrail_core PUBLIC cxx_std_17)
  target_compile_definitions(coretrail_core PRIVATE Glucose=RC2Glucose)
  target_include_directories(coretrail_core PUBLIC
    include
    third_party/glucose-syrup-4.1
    third_party/cardenc)
endif()

# Keep the Unix build flags used by the former setuptools extension path.
if(UNIX AND NOT HERMAX_CORE_ARCHIVE)
  target_compile_options(coretrail_core PRIVATE
    -O3
    -Wall
    -DNDEBUG
    -fvisibility=hidden
    -ffunction-sections
    -fdata-sections
    -fno-semantic-interposition
    -fomit-frame-pointer)
endif()

if(HERMAX_CORE_ONLY)
  return()
endif()

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(coretrail_native MODULE src/python/module.cc)
set_target_properties(coretrail_native PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_compile_features(coretrail_native PRIVATE cxx_std_17)
target_compile_definitions(coretrail_native PRIVATE Glucose=RC2Glucose)
target_include_directories(coretrail_native PRIVATE include third_party/glucose-syrup-4.1 third_party/cardenc
  "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../hermax/internal/native")
target_link_libraries(coretrail_native PRIVATE Python3::Module coretrail_core)

if(UNIX)
  target_compile_options(coretrail_native PRIVATE
    -O3
    -Wall
    -DNDEBUG
    -fvisibility=hidden
    -ffunction-sections
    -fdata-sections
    -fno-semantic-interposition
    -fomit-frame-pointer)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  target_link_options(coretrail_native PRIVATE
    -Wl,--gc-sections
    -static-libstdc++
    -static-libgcc)
endif()

set_target_properties(coretrail_native PROPERTIES
  PREFIX ""
  OUTPUT_NAME "coretrail_native"
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
