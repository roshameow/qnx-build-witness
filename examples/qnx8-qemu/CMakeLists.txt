cmake_minimum_required(VERSION 3.16)
project(qbw_qnx_pulse_test LANGUAGES C)

add_executable(qnx_pulse_test qnx_pulse_test.c)

if(NOT CMAKE_CROSSCOMPILING OR NOT CMAKE_SYSTEM_NAME STREQUAL "QNX")
  message(FATAL_ERROR
    "This example must be configured with the QNX 8.0 toolchain file, e.g. "
    "-DCMAKE_TOOLCHAIN_FILE=../../cmake/qnx8-x86_64.toolchain.cmake")
endif()

set_target_properties(qnx_pulse_test PROPERTIES
  OUTPUT_NAME "qnx_pulse_test"
)
