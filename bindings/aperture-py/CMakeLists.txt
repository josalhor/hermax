cmake_minimum_required(VERSION 3.15)
project(hermax_aperture_py LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(ZLIB REQUIRED)
find_package(Threads REQUIRED)
if(WIN32)
  find_program(MAKE_EXECUTABLE NAMES mingw32-make make gmake REQUIRED)
else()
  find_program(MAKE_EXECUTABLE NAMES make gmake REQUIRED)
endif()

set(APERTURE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/Aperture")
set(APERTURE_LIB "${APERTURE_ROOT}/build/libaperture_pic.a")

if(NOT EXISTS "${APERTURE_ROOT}/Makefile")
  message(FATAL_ERROR "Vendored Aperture source is missing: ${APERTURE_ROOT}")
endif()

if(HERMAX_CORE_ARCHIVE)
  set(APERTURE_LIB "${HERMAX_CORE_ARCHIVE}")
else()
file(GLOB_RECURSE APERTURE_SOURCES
  "${APERTURE_ROOT}/src/*.cc"
  "${APERTURE_ROOT}/src/*.h")

set(APERTURE_ADAPTER_OBJ "${APERTURE_ROOT}/build/aperture_native_adapter.o")
separate_arguments(APERTURE_CXX_FLAGS NATIVE_COMMAND "${CMAKE_CXX_FLAGS}")

set(APERTURE_MAKE_ARGS lib-pic "RES_FLAGS=-O3 -DNDEBUG")
if(WIN32)
  list(APPEND APERTURE_MAKE_ARGS "CADICAL_BUILD_TARGET=libcadical.a")
endif()

add_custom_command(
  OUTPUT "${APERTURE_LIB}" "${APERTURE_ADAPTER_OBJ}"
  COMMAND "${MAKE_EXECUTABLE}" -C "${APERTURE_ROOT}" ${APERTURE_MAKE_ARGS}
  COMMAND "${CMAKE_CXX_COMPILER}" ${APERTURE_CXX_FLAGS} -std=c++20 -fPIC
    -I${APERTURE_ROOT} -I${APERTURE_ROOT}/external -I${APERTURE_ROOT}/src
    -c "${CMAKE_CURRENT_SOURCE_DIR}/aperture_native.cpp" -o "${APERTURE_ADAPTER_OBJ}"
  COMMAND "${CMAKE_AR}" rcs "${APERTURE_LIB}" "${APERTURE_ADAPTER_OBJ}"
  COMMAND "${CMAKE_RANLIB}" "${APERTURE_LIB}"
  DEPENDS "${APERTURE_ROOT}/Makefile" ${APERTURE_SOURCES}
    "${CMAKE_CURRENT_SOURCE_DIR}/aperture_native.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/aperture_native.h"
  VERBATIM)
add_custom_target(aperture_static DEPENDS "${APERTURE_LIB}")

endif()

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(_aperture_native MODULE python/aperture_bindings.cpp)
set_target_properties(_aperture_native PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
if(NOT HERMAX_CORE_ARCHIVE)
  add_dependencies(_aperture_native aperture_static)
endif()
target_compile_features(_aperture_native PRIVATE cxx_std_20)
# Aperture's logging headers include <fmt/...>; fmt is vendored directly under
# external/fmt, so the parent external directory must be on the include path.
target_include_directories(_aperture_native PRIVATE
  "${APERTURE_ROOT}"
  "${APERTURE_ROOT}/external")
target_link_libraries(_aperture_native PRIVATE
  Python3::Module
  "${APERTURE_LIB}"
  ZLIB::ZLIB
  Threads::Threads)
if(UNIX AND NOT APPLE)
  # Keep manylinux wheels independent of the container's libstdc++ version.
  target_link_options(_aperture_native PRIVATE -static-libstdc++ -static-libgcc)
endif()
set_target_properties(_aperture_native PROPERTIES PREFIX "" OUTPUT_NAME "_aperture_native")
