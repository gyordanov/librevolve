cmake_minimum_required(VERSION 3.16)
project(librevolve VERSION 0.1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

option(LIBREVOLVE_BUILD_CLI "Build revolve C CLI" ON)
option(LIBREVOLVE_FETCH_SIMPLEBLE "Fetch SimpleBLE via FetchContent" ON)

include(FetchContent)
if(LIBREVOLVE_FETCH_SIMPLEBLE)
  FetchContent_Declare(
    SimpleBLE
    GIT_REPOSITORY https://github.com/OpenBluetoothToolbox/SimpleBLE.git
    GIT_TAG v0.9.1
  )
  FetchContent_GetProperties(SimpleBLE)
  if(NOT simpleble_POPULATED)
    FetchContent_Populate(SimpleBLE)
  endif()
  add_subdirectory(${simpleble_SOURCE_DIR}/simplecble ${CMAKE_BINARY_DIR}/simplecble)
endif()

add_library(librevolve SHARED
  src/protocol.c
  src/client.c
)
target_include_directories(librevolve
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(librevolve PRIVATE simplecble::simplecble stdc++)
target_include_directories(librevolve PRIVATE
  ${CMAKE_BINARY_DIR}/simpleble/export
  ${CMAKE_BINARY_DIR}/simplecble/export
  ${simpleble_SOURCE_DIR}/simpleble/include
  ${simpleble_SOURCE_DIR}/simplecble/include
)

if(LIBREVOLVE_BUILD_CLI)
  add_executable(revolve tools/revolve.c)
  target_link_libraries(revolve PRIVATE librevolve)
endif()

enable_testing()
add_executable(test_protocol_c tests/test_protocol_c.c)
target_link_libraries(test_protocol_c PRIVATE librevolve)
add_test(NAME protocol_c COMMAND test_protocol_c)
