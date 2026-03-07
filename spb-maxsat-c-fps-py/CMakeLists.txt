cmake_minimum_required(VERSION 3.15)
project(hermax.core.spb_maxsat_c_fps LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(SPB_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../SPB-MaxSAT-c-FPS/code")

set(SPB_SOURCES
    "${SPB_ROOT}/Encoder.cc"
    "${SPB_ROOT}/MaxSAT.cc"
    "${SPB_ROOT}/MaxSATFormula.cc"
    "${SPB_ROOT}/MaxSATFormulaExtended.cc"
    "${SPB_ROOT}/MaxSAT_Partition.cc"
    "${SPB_ROOT}/ParserPB.cc"
    "${SPB_ROOT}/Torc.cc"
    "${SPB_ROOT}/algorithms/Alg_BLS.cc"
    "${SPB_ROOT}/algorithms/Alg_LinearSU.cc"
    "${SPB_ROOT}/algorithms/Alg_LinearSU_Clustering.cc"
    "${SPB_ROOT}/algorithms/Alg_LinearSU_Mod.cc"
    "${SPB_ROOT}/algorithms/Alg_MSU3.cc"
    "${SPB_ROOT}/algorithms/Alg_OBV.cc"
    "${SPB_ROOT}/algorithms/Alg_OLL.cc"
    "${SPB_ROOT}/algorithms/Alg_OLL_Mod.cc"
    "${SPB_ROOT}/algorithms/Alg_PartMSU3.cc"
    "${SPB_ROOT}/algorithms/Alg_WBO.cc"
    "${SPB_ROOT}/algorithms/global.cc"
    "${SPB_ROOT}/encodings/Enc_Adder.cc"
    "${SPB_ROOT}/encodings/Enc_CNetworks.cc"
    "${SPB_ROOT}/encodings/Enc_GTE.cc"
    "${SPB_ROOT}/encodings/Enc_GTECluster.cc"
    "${SPB_ROOT}/encodings/Enc_GTEIncremental.cc"
    "${SPB_ROOT}/encodings/Enc_Ladder.cc"
    "${SPB_ROOT}/encodings/Enc_MTotalizer.cc"
    "${SPB_ROOT}/encodings/Enc_SWC.cc"
    "${SPB_ROOT}/encodings/Enc_Totalizer.cc"
    "${SPB_ROOT}/encodings/Encodings.cc"
    "${SPB_ROOT}/graph/Graph.cc"
    "${SPB_ROOT}/graph/Graph_Algorithms.cc"
    "${SPB_ROOT}/graph/Graph_Communities.cc"
    "${SPB_ROOT}/clusterings/Cluster.cc"
    "${SPB_ROOT}/clusterings/Cluster_DivisiveMaxSeparate.cc"
    "${SPB_ROOT}/clusterings/SequenceStatistic.cc"
    "${SPB_ROOT}/solvers/glucose4.1/core/Solver.cc"
    "${SPB_ROOT}/solvers/glucose4.1/utils/System.cc"
)

pybind11_add_module(spb_maxsat_c_fps MODULE NO_EXTRAS
    python/spb_maxsat_c_fps_bindings.cpp
    ${SPB_SOURCES}
)

target_include_directories(spb_maxsat_c_fps PRIVATE
    "${SPB_ROOT}"
    "${SPB_ROOT}/solvers/glucose4.1"
)

target_link_libraries(spb_maxsat_c_fps PRIVATE Python3::Module pybind11::module)
if (NOT MSVC)
    target_compile_options(spb_maxsat_c_fps PRIVATE -fpermissive)
endif()

add_definitions(-D__STDC_LIMIT_MACROS -D__STDC_FORMAT_MACROS)
target_compile_definitions(spb_maxsat_c_fps PRIVATE
    NSPACE=Glucose
    SOLVERNAME="Glucose4.1"
    VERSION=core
)

find_library(GMP_LIBRARY gmp)
find_library(GMPXX_LIBRARY gmpxx)
if(GMP_LIBRARY)
    target_link_libraries(spb_maxsat_c_fps PRIVATE ${GMP_LIBRARY})
endif()
if(GMPXX_LIBRARY)
    target_link_libraries(spb_maxsat_c_fps PRIVATE ${GMPXX_LIBRARY})
endif()

set_target_properties(spb_maxsat_c_fps PROPERTIES
    OUTPUT_NAME "spb_maxsat_c_fps"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
)
