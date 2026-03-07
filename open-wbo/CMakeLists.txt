cmake_minimum_required(VERSION 3.15)
project(hermax.core.openwbo LANGUAGES CXX)

# --- Find Python correctly ---
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

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
)

# Create the Python module
pybind11_add_module(openwbo MODULE NO_EXTRAS openwbo_bindings.cpp ${SOURCES})

target_include_directories(openwbo PRIVATE
    .
    solvers/glucose4.1
)

# Use the modern link targets
target_link_libraries(openwbo PRIVATE Python3::Module pybind11::module)

add_definitions(-D __STDC_LIMIT_MACROS -D __STDC_FORMAT_MACROS -D SIMP)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DNSPACE=Glucose")

# Force-include a shim header
target_compile_options(openwbo PRIVATE
    -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
)

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
