include_guard(GLOBAL)

# Direct single-configuration builds should match package builds by default.
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build configuration" FORCE)
endif()

# Other platforms retain an opt-in until their native wheel jobs validate IPO.
set(_hermax_lto_default OFF)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(_hermax_lto_default ON)
endif()
option(HERMAX_ENCODER_LTO "Use supported Release-mode encoder LTO" ${_hermax_lto_default})

# Keep extension IPO flags under the same option and configuration.
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)
set(HERMAX_ENCODER_IPO_SUPPORTED OFF)
if(HERMAX_ENCODER_LTO AND (CMAKE_CONFIGURATION_TYPES OR CMAKE_BUILD_TYPE STREQUAL "Release"))
    include(CheckIPOSupported)
    check_ipo_supported(RESULT HERMAX_ENCODER_IPO_SUPPORTED OUTPUT _hermax_ipo_error LANGUAGES CXX)
    if(NOT HERMAX_ENCODER_IPO_SUPPORTED)
        message(STATUS "Encoder LTO unavailable; using normal compilation: ${_hermax_ipo_error}")
    endif()
endif()

function(hermax_encoder_options target)
    get_target_property(_imported ${target} IMPORTED)
    if(NOT _imported)
        set_target_properties(${target} PROPERTIES
            CXX_VISIBILITY_PRESET hidden
            VISIBILITY_INLINES_HIDDEN ON
            INTERPROCEDURAL_OPTIMIZATION OFF
            INTERPROCEDURAL_OPTIMIZATION_DEBUG OFF
            INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO OFF
            INTERPROCEDURAL_OPTIMIZATION_MINSIZEREL OFF
            INTERPROCEDURAL_OPTIMIZATION_RELEASE ${HERMAX_ENCODER_IPO_SUPPORTED})
    endif()
endfunction()
