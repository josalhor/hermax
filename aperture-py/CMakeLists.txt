cmake_minimum_required(VERSION 3.15)
project(hermax_aperture_py LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)
find_package(ZLIB REQUIRED)
find_package(Threads REQUIRED)
if(WIN32)
  find_program(MAKE_EXECUTABLE NAMES mingw32-make make gmake REQUIRED)
else()
  find_program(MAKE_EXECUTABLE NAMES make gmake REQUIRED)
endif()

set(APERTURE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../Aperture")
set(APERTURE_LIB "${APERTURE_ROOT}/build/libaperture_pic.a")

if(NOT EXISTS "${APERTURE_ROOT}/Makefile")
  message(FATAL_ERROR "Vendored Aperture source is missing: ${APERTURE_ROOT}")
endif()

file(GLOB_RECURSE APERTURE_SOURCES
  "${APERTURE_ROOT}/src/*.cc"
  "${APERTURE_ROOT}/src/*.h")

set(APERTURE_MAKE_ARGS lib-pic "RES_FLAGS=-O3 -DNDEBUG")
if(WIN32)
  list(APPEND APERTURE_MAKE_ARGS "CADICAL_BUILD_TARGET=libcadical.a")
endif()

add_custom_command(
  OUTPUT "${APERTURE_LIB}"
  COMMAND "${MAKE_EXECUTABLE}" -C "${APERTURE_ROOT}" ${APERTURE_MAKE_ARGS}
  DEPENDS "${APERTURE_ROOT}/Makefile" ${APERTURE_SOURCES}
  VERBATIM)
add_custom_target(aperture_static DEPENDS "${APERTURE_LIB}")

pybind11_add_module(_aperture_native MODULE NO_EXTRAS python/aperture_bindings.cpp)
add_dependencies(_aperture_native aperture_static)
target_compile_features(_aperture_native PRIVATE cxx_std_20)
# Aperture's logging headers include <fmt/...>; fmt is vendored directly under
# external/fmt, so the parent external directory must be on the include path.
target_include_directories(_aperture_native PRIVATE
  "${APERTURE_ROOT}"
  "${APERTURE_ROOT}/external")
target_link_libraries(_aperture_native PRIVATE
  Python3::Module
  pybind11::module
  "${APERTURE_LIB}"
  ZLIB::ZLIB
  Threads::Threads)
if(UNIX AND NOT APPLE)
  # Keep manylinux wheels independent of the container's libstdc++ version.
  target_link_options(_aperture_native PRIVATE -static-libstdc++ -static-libgcc)
endif()
set_target_properties(_aperture_native PROPERTIES PREFIX "" OUTPUT_NAME "_aperture_native")
