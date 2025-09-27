# shellcheck shell=bats

setup() {
    bats_load_library 'bats-support'
    bats_load_library 'bats-assert'
}

@test "dummy" {
    run true
    assert_success
}
