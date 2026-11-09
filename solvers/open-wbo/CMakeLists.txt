cmake_minimum_required(VERSION 3.15)
project(hermax.core.openwbo LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Define the library sources
set(SOURCES
    Encoder.cc
    MaxSAT.cc
    MaxSATFormula.cc
    MaxSAT_Partition.cc
    ParserPB.cc
    algorithms/Alg_LinearSU.cc
    algorithms/Alg_MSU3.cc
    algorithms/Alg_OLL.cc
    algorithms/Alg_PartMSU3.cc
    algorithms/Alg_WBO.cc
    encodings/Enc_Adder.cc
    encodings/Enc_CNetworks.cc
    encodings/Enc_GTE.cc
    encodings/Enc_Ladder.cc
    encodings/Enc_MTotalizer.cc
    encodings/Enc_SWC.cc
    encodings/Enc_Totalizer.cc
    encodings/Encodings.cc
    graph/Graph_Algorithms.cc
    graph/Graph_Communities.cc
    graph/Graph.cc
    solvers/glucose4.1/core/Solver.cc
    solvers/glucose4.1/utils/System.cc
    solvers/glucose4.1/simp/SimpSolver.cc
    openwbo_native.cpp
)

if(HERMAX_CORE_ARCHIVE)
    add_library(openwbo_core STATIC IMPORTED GLOBAL)
    set_target_properties(openwbo_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(openwbo_core STATIC ${SOURCES})
endif()

if(NOT HERMAX_CORE_ARCHIVE)
    target_include_directories(openwbo_core PUBLIC
        .
        solvers/glucose4.1
    )
    target_compile_definitions(openwbo_core PRIVATE
        __STDC_LIMIT_MACROS
        __STDC_FORMAT_MACROS
        SIMP
        NSPACE=Glucose
    )

    # Force-include a shim header
    target_compile_options(openwbo_core PRIVATE
        -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
    )
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

add_library(openwbo MODULE openwbo_bindings.cpp)
set_target_properties(openwbo PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_include_directories(openwbo PRIVATE .)
target_link_libraries(openwbo PRIVATE Python3::Module openwbo_core)
set_target_properties(openwbo PROPERTIES PREFIX "")

# Link against GMP library (and gmpxx for headers)
find_library(GMP_LIBRARY gmp)
find_library(GMPXX_LIBRARY gmpxx)

if(GMP_LIBRARY)
    target_link_libraries(openwbo PRIVATE ${GMP_LIBRARY})
    if(GMPXX_LIBRARY)
        target_link_libraries(openwbo PRIVATE ${GMPXX_LIBRARY})
    endif()
else()
    # Try Homebrew common paths as fallback for headers if find_library fails to find headers
    if(APPLE)
        if(EXISTS "/opt/homebrew/include")
            target_include_directories(openwbo PRIVATE "/opt/homebrew/include")
        elif(EXISTS "/usr/local/include")
            target_include_directories(openwbo PRIVATE "/usr/local/include")
        endif()
    endif()
    message(WARNING "GMP library not found via find_library, relying on system/Homebrew paths.")
endif()

# Ensure the .pyd lands where setuptools expects (Windows treats it as RUNTIME)
set_target_properties(openwbo PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
)
