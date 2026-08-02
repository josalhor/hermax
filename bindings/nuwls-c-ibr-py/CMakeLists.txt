cmake_minimum_required(VERSION 3.15)
project(hermax.core.nuwls_c_ibr LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(NUWLS_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/NuWLS-c-IBR/code")

set(NUWLS_SOURCES
    "${NUWLS_ROOT}/Encoder.cc"
    "${NUWLS_ROOT}/MaxSAT.cc"
    "${NUWLS_ROOT}/MaxSATFormula.cc"
    "${NUWLS_ROOT}/MaxSATFormulaExtended.cc"
    "${NUWLS_ROOT}/MaxSAT_Partition.cc"
    "${NUWLS_ROOT}/ParserPB.cc"
    "${NUWLS_ROOT}/Torc.cc"
    "${NUWLS_ROOT}/algorithms/Alg_BLS.cc"
    "${NUWLS_ROOT}/algorithms/Alg_LinearSU.cc"
    "${NUWLS_ROOT}/algorithms/Alg_LinearSU_Clustering.cc"
    "${NUWLS_ROOT}/algorithms/Alg_LinearSU_Mod.cc"
    "${NUWLS_ROOT}/algorithms/Alg_MSU3.cc"
    "${NUWLS_ROOT}/algorithms/Alg_OBV.cc"
    "${NUWLS_ROOT}/algorithms/Alg_OLL.cc"
    "${NUWLS_ROOT}/algorithms/Alg_OLL_Mod.cc"
    "${NUWLS_ROOT}/algorithms/Alg_PartMSU3.cc"
    "${NUWLS_ROOT}/algorithms/Alg_WBO.cc"
    "${NUWLS_ROOT}/encodings/Enc_Adder.cc"
    "${NUWLS_ROOT}/encodings/Enc_CNetworks.cc"
    "${NUWLS_ROOT}/encodings/Enc_GTE.cc"
    "${NUWLS_ROOT}/encodings/Enc_GTECluster.cc"
    "${NUWLS_ROOT}/encodings/Enc_GTEIncremental.cc"
    "${NUWLS_ROOT}/encodings/Enc_Ladder.cc"
    "${NUWLS_ROOT}/encodings/Enc_MTotalizer.cc"
    "${NUWLS_ROOT}/encodings/Enc_SWC.cc"
    "${NUWLS_ROOT}/encodings/Enc_Totalizer.cc"
    "${NUWLS_ROOT}/encodings/Encodings.cc"
    "${NUWLS_ROOT}/graph/Graph.cc"
    "${NUWLS_ROOT}/graph/Graph_Algorithms.cc"
    "${NUWLS_ROOT}/graph/Graph_Communities.cc"
    "${NUWLS_ROOT}/clusterings/Cluster.cc"
    "${NUWLS_ROOT}/clusterings/Cluster_DivisiveMaxSeparate.cc"
    "${NUWLS_ROOT}/clusterings/SequenceStatistic.cc"
    "${NUWLS_ROOT}/solvers/glucose4.1/core/Solver.cc"
    "${NUWLS_ROOT}/solvers/glucose4.1/utils/System.cc"
)

if(HERMAX_CORE_ARCHIVE)
    add_library(nuwls_c_ibr_core STATIC IMPORTED GLOBAL)
    set_target_properties(nuwls_c_ibr_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(nuwls_c_ibr_core STATIC ${NUWLS_SOURCES})
endif()

if(NOT HERMAX_CORE_ARCHIVE)
    target_include_directories(nuwls_c_ibr_core PUBLIC
        "${NUWLS_ROOT}"
        "${NUWLS_ROOT}/solvers/glucose4.1"
    )

    if (NOT MSVC)
        target_compile_options(nuwls_c_ibr_core PRIVATE -fpermissive)
    endif()

    target_compile_definitions(nuwls_c_ibr_core PRIVATE
        __STDC_LIMIT_MACROS
        __STDC_FORMAT_MACROS
        NSPACE=Glucose
        SOLVERNAME="Glucose4.1"
        VERSION=core
    )
endif()

if(HERMAX_CORE_ONLY)
    return()
endif()

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

pybind11_add_module(nuwls_c_ibr MODULE NO_EXTRAS python/nuwls_c_ibr_bindings.cpp)
target_include_directories(nuwls_c_ibr PRIVATE "${NUWLS_ROOT}" "${NUWLS_ROOT}/solvers/glucose4.1")
if (NOT MSVC)
    target_compile_options(nuwls_c_ibr PRIVATE -fpermissive)
endif()
target_compile_definitions(nuwls_c_ibr PRIVATE
    __STDC_LIMIT_MACROS
    __STDC_FORMAT_MACROS
    NSPACE=Glucose
    SOLVERNAME="Glucose4.1"
    VERSION=core
)
target_link_libraries(nuwls_c_ibr PRIVATE Python3::Module pybind11::module nuwls_c_ibr_core)

find_library(GMP_LIBRARY gmp)
find_library(GMPXX_LIBRARY gmpxx)
if(GMP_LIBRARY)
    target_link_libraries(nuwls_c_ibr PRIVATE ${GMP_LIBRARY})
endif()
if(GMPXX_LIBRARY)
    target_link_libraries(nuwls_c_ibr PRIVATE ${GMPXX_LIBRARY})
endif()

set_target_properties(nuwls_c_ibr PROPERTIES
    OUTPUT_NAME "nuwls_c_ibr"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
)
