cmake_minimum_required(VERSION 3.15)
project(hermax_integer_sum LANGUAGES CXX)
include(../common/CompilerOptions.cmake)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(INTEGER_SUM_CORE_ONLY "${HERMAX_CORE_ONLY}")
set(HERMAX_CORE_ONLY ON)
add_subdirectory(../pblib pblib)
if(INTEGER_SUM_CORE_ONLY)
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

add_library(_integer_sum_native MODULE bindings.cpp)
set_target_properties(_integer_sum_native PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
hermax_encoder_options(_integer_sum_native)
target_include_directories(_integer_sum_native PRIVATE ../pblib/pblib/pblib ../../hermax/internal)
target_link_libraries(_integer_sum_native PRIVATE Python3::Module pblib_core)
set_target_properties(_integer_sum_native PROPERTIES PREFIX "" OUTPUT_NAME "_integer_sum_native")
