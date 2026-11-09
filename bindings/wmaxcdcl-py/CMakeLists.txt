cmake_minimum_required(VERSION 3.15)
project(hermax_wmaxcdcl LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(WMAXCDCL_CODE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/WMaxCDCL_Paper/WMaxCDCL/code")

set(WMAXCDCL_SOURCES
    "${WMAXCDCL_CODE_DIR}/mtl/MDD.cc"
    "${WMAXCDCL_CODE_DIR}/utils/Options.cc"
    "${WMAXCDCL_CODE_DIR}/utils/System.cc"
    "${WMAXCDCL_CODE_DIR}/core/Solver.cc"
    "${WMAXCDCL_CODE_DIR}/core/sattime.cc"
    "${WMAXCDCL_CODE_DIR}/simp/SimpSolver.cc"
    "${CMAKE_CURRENT_SOURCE_DIR}/wmaxcdcl_native.cpp"
)

if(HERMAX_CORE_ARCHIVE)
    add_library(wmaxcdcl_core STATIC IMPORTED GLOBAL)
    set_target_properties(wmaxcdcl_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(wmaxcdcl_core STATIC ${WMAXCDCL_SOURCES})
endif()

if(NOT HERMAX_CORE_ARCHIVE)
    target_include_directories(wmaxcdcl_core PUBLIC "${WMAXCDCL_CODE_DIR}")
    target_compile_definitions(wmaxcdcl_core PRIVATE __STDC_LIMIT_MACROS __STDC_FORMAT_MACROS)
endif()

if(HERMAX_CORE_ONLY)
    return()
endif()

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(ZLIB REQUIRED)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(wmaxcdcl MODULE python/wmaxcdcl_bindings.cpp)
set_target_properties(wmaxcdcl PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_link_libraries(wmaxcdcl PRIVATE Python3::Module wmaxcdcl_core ZLIB::ZLIB)

set_target_properties(wmaxcdcl PROPERTIES
  PREFIX ""
  OUTPUT_NAME "wmaxcdcl"
)
set_target_properties(wmaxcdcl PROPERTIES CXX_STANDARD 14 CXX_STANDARD_REQUIRED ON)
